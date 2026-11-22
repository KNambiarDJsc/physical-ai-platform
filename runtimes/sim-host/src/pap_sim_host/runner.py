"""Run one scenario of the catalog and report exactly what it left behind.

The host never invents a value. A run is `completed` only if the command exited 0 and wrote a result file whose
measurements and artifacts match what the catalog declared; anything else is a failed run and says why. The command is
the operator's argument list; parameters are validated against the scenario's JSON Schema first, and a parameter
substituted into an argument may not look like an option.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import subprocess
import sys
import threading
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from .catalog import PLACEHOLDER, Catalog, Scenario

LOG_TAIL = 4000


class HostError(Exception):
    """A refusal or a failed run, written for the person reading the step's error."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while block := f.read(1 << 20):
            h.update(block)
    return h.hexdigest()


def _tail(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")[-LOG_TAIL:]
    except OSError:
        return ""


class Host:
    def __init__(self, catalog: Catalog, catalog_dir: Path, work_dir: Path) -> None:
        self.catalog = catalog
        self.catalog_dir = catalog_dir.resolve()
        self.work = work_dir.resolve()
        (self.work / "runs").mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()  # one scenario at a time: a simulator is one shared machine
        self._guard = threading.Lock()
        self._by_request: dict[str, dict[str, Any]] = {}
        self._by_run: dict[str, dict[str, Any]] = {}
        self._load_previous()

    # ---- persistence ---------------------------------------------------------------------------------------------

    def _load_previous(self) -> None:
        for rec in sorted((self.work / "runs").glob("*/record.json")):
            try:
                r = json.loads(rec.read_text(encoding="utf-8"))
                self._by_run[r["run_id"]] = r
                self._by_request[r["request_id"]] = r
            except (OSError, ValueError, KeyError):
                continue

    def _save(self, r: dict[str, Any]) -> None:
        d = self.work / "runs" / r["run_id"]
        tmp = d / "record.json.tmp"
        tmp.write_text(json.dumps(r, indent=1, sort_keys=True), encoding="utf-8")
        tmp.replace(d / "record.json")

    # ---- public views --------------------------------------------------------------------------------------------

    def runs(self, limit: int = 20) -> list[dict[str, Any]]:
        with self._guard:
            rs = sorted(self._by_run.values(), key=lambda r: r["started_at"], reverse=True)[:limit]
        return [
            {k: r[k] for k in ("run_id", "scenario", "scenario_version", "state", "started_at", "finished_at", "error")}
            for r in rs
        ]

    def artifact(self, run_id: str, name: str) -> tuple[Path, dict[str, Any]]:
        """The file of a LISTED artifact of a recorded run, re-hashed before it is handed out."""
        with self._guard:
            r = self._by_run.get(run_id)
        a = next((x for x in (r or {}).get("artifacts", []) if x["name"] == name), None)
        if r is None or a is None:
            raise HostError("not_found", "no such artifact")
        path = self.work / "runs" / run_id / "run" / a["path"]
        if not path.is_file() or _sha256(path) != a["sha256"]:
            raise HostError("artifact_changed", "the artifact no longer matches the digest recorded for it")
        return path, a

    # ---- validation ----------------------------------------------------------------------------------------------

    def _scenario(self, scenario: str, version: str | None) -> Scenario:
        s = self.catalog.find(scenario, version)
        if s is None:
            raise HostError("unknown_scenario", f"the catalog has no scenario {scenario!r} version {version!r}")
        return s

    @staticmethod
    def _check_params(s: Scenario, params: dict[str, Any]) -> None:
        errors = sorted(Draft202012Validator(s.parameters).iter_errors(params), key=lambda e: list(e.path))
        if errors:
            raise HostError(
                "invalid_parameters",
                "; ".join(f"{'.'.join(map(str, e.path)) or 'parameters'}: {e.message}" for e in errors[:5]),
            )

    def _argv(self, s: Scenario, run_dir: Path, params: dict[str, Any]) -> list[str]:
        fixed = {
            "run_dir": str(run_dir),
            "params_file": str(run_dir / "params.json"),
            "catalog_dir": str(self.catalog_dir),
            "python": sys.executable,
        }

        def sub(m: re.Match[str]) -> str:
            key = m.group(1)
            if key in fixed:
                return fixed[key]
            value = params[key.partition(".")[2]]
            text = json.dumps(value) if isinstance(value, bool) else str(value)
            if text.startswith("-") and not isinstance(value, int | float):
                raise HostError("invalid_parameters", f"parameter {key!r} may not start with '-'")
            return text

        return [PLACEHOLDER.sub(sub, a) for a in s.command]

    # ---- the run -------------------------------------------------------------------------------------------------

    def run(self, scenario: str, version: str, parameters: dict[str, Any], request_id: str) -> dict[str, Any]:
        s = self._scenario(scenario, version)
        self._check_params(s, parameters)
        with self._guard:
            prior = self._by_request.get(request_id)
        if prior is not None:
            return self._answer(prior, scenario, version, parameters, repeated=True)
        with self._lock:
            with self._guard:  # another caller with the same id may have finished while this one waited
                prior = self._by_request.get(request_id)
            if prior is not None:
                return self._answer(prior, scenario, version, parameters, repeated=True)
            rec = self._execute(s, parameters, request_id)
            with self._guard:
                self._by_request[request_id] = rec
                self._by_run[rec["run_id"]] = rec
        return self._answer(rec, scenario, version, parameters, repeated=False)

    @staticmethod
    def _answer(
        rec: dict[str, Any], scenario: str, version: str, parameters: dict[str, Any], repeated: bool
    ) -> dict[str, Any]:
        if (rec["scenario"], rec["scenario_version"], rec["parameters"]) != (scenario, version, parameters):
            raise HostError("request_id_reused", "this request_id was used for a different request")
        if rec["state"] != "completed":
            raise HostError(rec["error_code"], rec["error"])
        return {k: v for k, v in rec.items() if k not in ("error", "error_code", "request_id")} | {"repeated": repeated}

    def _execute(self, s: Scenario, params: dict[str, Any], request_id: str) -> dict[str, Any]:
        run_id = uuid.uuid4().hex
        base = self.work / "runs" / run_id
        run_dir = base / "run"
        run_dir.mkdir(parents=True)
        (run_dir / "params.json").write_text(json.dumps(params, sort_keys=True), encoding="utf-8")
        rec: dict[str, Any] = {
            "run_id": run_id,
            "request_id": request_id,
            "scenario": s.id,
            "scenario_version": s.version,
            "parameters": params,
            "state": "failed",
            "error_code": "run_failed",
            "error": "",
            "measurements": {},
            "artifacts": [],
            "identity": None,
            "started_at": _now(),
            "finished_at": None,
            "duration_s": None,
            "exit_code": None,
            "simulator": {"kind": self.catalog.simulator.kind, "name": self.catalog.simulator.name},
        }
        self._save(rec)
        t0 = time.monotonic()
        try:
            argv = self._argv(s, run_dir, params)
            with (base / "stdout.log").open("wb") as out, (base / "stderr.log").open("wb") as err:
                proc = subprocess.Popen(argv, cwd=run_dir, stdin=subprocess.DEVNULL, stdout=out, stderr=err)
                try:
                    rec["exit_code"] = proc.wait(timeout=s.max_duration_s)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait()
                    raise HostError(
                        "timeout", f"the scenario did not finish within its {s.max_duration_s:g} s limit"
                    ) from None
            if rec["exit_code"] != 0:
                raise HostError(
                    "command_failed", f"the scenario command exited {rec['exit_code']}: {_tail(base / 'stderr.log')}"
                )
            self._collect(s, run_dir, rec)
            rec["state"], rec["error"], rec["error_code"] = "completed", "", ""
        except HostError as e:
            rec["error"], rec["error_code"] = e.message, e.code
        except OSError as e:
            rec["error"], rec["error_code"] = f"the command could not be started: {e}", "command_failed"
        rec["finished_at"] = _now()
        rec["duration_s"] = round(time.monotonic() - t0, 3)
        self._save(rec)
        return rec

    def _collect(self, s: Scenario, run_dir: Path, rec: dict[str, Any]) -> None:
        rf = run_dir / s.result_file
        if not rf.is_file():
            raise HostError("no_result", f"the scenario left no {s.result_file}: there is nothing to report")
        try:
            result = json.loads(rf.read_text(encoding="utf-8"))
            measurements = result["measurements"]
            files = result.get("artifacts", {})
        except (ValueError, KeyError, TypeError):
            raise HostError("bad_result", f"{s.result_file} is not a JSON object with a measurements member") from None
        if not isinstance(measurements, dict) or not isinstance(files, dict):
            raise HostError("bad_result", "measurements and artifacts must be objects")
        declared = {o.name for o in s.outputs}
        missing = sorted(declared - set(measurements))
        extra = sorted(set(measurements) - declared)
        if missing or extra:
            raise HostError(
                "bad_result", f"measurements differ from the catalog: missing {missing}, undeclared {extra}"
            )
        for k, v in measurements.items():
            if isinstance(v, bool | str):
                continue
            if not isinstance(v, int | float) or not math.isfinite(v):
                raise HostError("bad_result", f"measurement {k!r} is not a finite number, boolean or string")
        arts: list[dict[str, Any]] = []
        root = run_dir.resolve()
        for a in s.artifacts:
            rel = files.get(a.name)
            if rel is None:
                if a.optional:
                    continue
                raise HostError("bad_result", f"the scenario did not leave the declared artifact {a.name!r}")
            path = (run_dir / str(rel)).resolve()
            if root not in path.parents or not path.is_file():
                raise HostError("bad_result", f"artifact {a.name!r} is not a file inside the run directory")
            arts.append(
                {
                    "name": a.name,
                    "path": path.relative_to(root).as_posix(),
                    "sha256": _sha256(path),
                    "size_bytes": path.stat().st_size,
                    "media_type": a.media_type,
                }
            )
        unknown = sorted(set(files) - {a.name for a in s.artifacts})
        if unknown:
            raise HostError("bad_result", f"artifacts not declared in the catalog: {unknown}")
        rec["measurements"] = measurements
        rec["artifacts"] = arts
        rec["identity"] = result.get("identity")
