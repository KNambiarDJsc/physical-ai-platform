"""The one place the platform runs the OpenMHS engine.

Every call: the binary's SHA-256 is checked against the configured digest (once per instance, and again when the
file's size or mtime changes), the process is started with an argument list (never a shell), stdout and stderr go
to temporary files whose size is capped, a deadline and an optional cancel event are enforced by killing the
process, and the JSON output is parsed into typed models. Input files are written by the bridge into a working
directory it controls; untrusted strings only ever appear inside those files or as single argv elements.
"""

from __future__ import annotations

import dataclasses
import json
import os
import subprocess
import tempfile
import threading
import time
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

from .canonical import sha256_file
from .errors import EngineError
from .models import (
    Comparison,
    EngineProvenance,
    IncidentDetail,
    IncidentSummary,
    IngestResult,
    VerifierReport,
)

M = TypeVar("M", bound=BaseModel)

VERDICT_EXIT = {0: "SATISFIED", 3: "VIOLATED", 4: "UNKNOWN"}


@dataclass(frozen=True)
class EngineConfig:
    binary: str
    expected_sha256: str
    commit: str
    interfaces: dict[str, str]
    timeout_s: float = 300.0
    max_output_bytes: int = 64 * 1024 * 1024

    @classmethod
    def from_lock(cls, lock_path: str | Path, binary: str, expected_sha256: str, **kw: Any) -> EngineConfig:
        lock = json.loads(Path(lock_path).read_text(encoding="utf-8"))
        return cls(
            binary=binary,
            expected_sha256=expected_sha256,
            commit=lock["commit"],
            interfaces=dict(lock["interfaces"]),
            **kw,
        )


@dataclass(frozen=True)
class RawRun:
    argv: list[str]
    returncode: int
    stdout: str
    stderr: str
    seconds: float


@dataclass(frozen=True)
class Result[T]:
    """An engine answer: the typed value, the engine's output verbatim, and what produced it."""

    value: T
    raw: str
    provenance: EngineProvenance
    seconds: float
    args: list[str]


class Engine:
    def __init__(self, config: EngineConfig) -> None:
        # Absolute path: Windows process creation does not resolve relative paths written with forward slashes.
        self.config = dataclasses.replace(config, binary=str(Path(config.binary).resolve()))
        self._checked: tuple[int, int] | None = None
        self._version: str | None = None
        self._lock = threading.Lock()

    # -------------------------------------------------------------------------------------------- integrity

    def check_binary(self) -> None:
        """Refuse a missing binary or one whose SHA-256 differs from the configured digest."""
        path = self.config.binary
        try:
            st = os.stat(path)
        except OSError as e:
            raise EngineError("engine.binary_missing", f"{path}: {e.strerror}", {"binary": path}) from e
        key = (st.st_size, st.st_mtime_ns)
        with self._lock:
            if self._checked == key:
                return
            actual = sha256_file(path)
            if actual != self.config.expected_sha256:
                raise EngineError(
                    "engine.digest_mismatch",
                    "the engine binary is not the pinned build",
                    {"binary": path, "expected": self.config.expected_sha256, "actual": actual},
                )
            self._checked = key

    def provenance(self) -> EngineProvenance:
        if self._version is None:
            run = self._run(["--version"], timeout_s=30)
            if run.returncode != 0:
                raise EngineError("engine.exit", "--version failed", {"stderr": run.stderr[-2000:]})
            self._version = run.stdout.strip()
        return EngineProvenance(
            version=self._version,
            binary_sha256=self.config.expected_sha256,
            commit=self.config.commit,
            interfaces=self.config.interfaces,
        )

    # -------------------------------------------------------------------------------------------- process

    def _run(
        self,
        args: Sequence[str],
        *,
        timeout_s: float | None = None,
        cancel: threading.Event | None = None,
        cwd: str | None = None,
    ) -> RawRun:
        self.check_binary()
        for a in args:
            if not isinstance(a, str) or "\x00" in a:
                raise EngineError("engine.input_invalid", "engine arguments must be strings without NUL bytes")
        argv = [self.config.binary, *args]
        deadline = time.monotonic() + (timeout_s if timeout_s is not None else self.config.timeout_s)
        limit = self.config.max_output_bytes
        start = time.monotonic()
        with tempfile.TemporaryFile() as out, tempfile.TemporaryFile() as err:
            try:
                proc = subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=out, stderr=err, cwd=cwd, shell=False)
            except OSError as e:
                raise EngineError("engine.start_failed", str(e), {"argv0": argv[0]}) from e
            reason: str | None = None
            while True:
                try:
                    proc.wait(timeout=0.1)
                    break
                except subprocess.TimeoutExpired:
                    pass
                if cancel is not None and cancel.is_set():
                    reason = "engine.cancelled"
                elif time.monotonic() > deadline:
                    reason = "engine.timeout"
                elif os.fstat(out.fileno()).st_size > limit or os.fstat(err.fileno()).st_size > limit:
                    reason = "engine.output_too_large"
                if reason:
                    proc.kill()
                    proc.wait()
                    break
            seconds = time.monotonic() - start
            if reason:
                raise EngineError(
                    reason,
                    f"{args[0] if args else ''} stopped after {seconds:.1f} s",
                    {"args": list(args[:4]), "seconds": round(seconds, 3)},
                )
            out.seek(0)
            err.seek(0)
            if os.fstat(out.fileno()).st_size > limit:
                raise EngineError("engine.output_too_large", "output exceeds the configured limit")
            stdout = out.read().decode("utf-8", errors="replace")
            stderr = err.read().decode("utf-8", errors="replace")
        return RawRun(argv=argv, returncode=proc.returncode, stdout=stdout, stderr=stderr, seconds=seconds)

    @staticmethod
    def _parse(model: type[M], run: RawRun) -> M:
        try:
            return model.model_validate_json(run.stdout)
        except ValidationError as e:
            raise EngineError(
                "engine.output_invalid",
                f"engine output does not match {model.__name__}",
                {"errors": e.errors(include_url=False)[:10], "stdout_head": run.stdout[:500]},
            ) from e

    @staticmethod
    def _parse_list(model: type[M], run: RawRun) -> list[M]:
        try:
            data = json.loads(run.stdout)
            if not isinstance(data, list):
                raise TypeError("expected a JSON array")
            return [model.model_validate(x) for x in data]
        except (ValueError, TypeError) as e:  # ValidationError is a ValueError
            raise EngineError(
                "engine.output_invalid",
                f"engine output is not a list of {model.__name__}",
                {"error": str(e)[:500], "stdout_head": run.stdout[:500]},
            ) from e

    def _result[T](self, value: T, run: RawRun) -> Result[T]:
        return Result(value=value, raw=run.stdout, provenance=self.provenance(), seconds=run.seconds, args=run.argv[1:])

    @staticmethod
    def _value(name: str, v: str) -> str:
        """A user-supplied value bound to its option as ``--name=value``, so it can never be read as a flag."""
        if not isinstance(v, str) or not v or chr(0) in v:
            raise EngineError("engine.input_invalid", f"{name} must be a non-empty string")
        return f"--{name}={v}"

    # -------------------------------------------------------------------------------------------- commands

    def verify_outcome(
        self,
        contract: dict[str, Any],
        evidence: Iterable[dict[str, Any]],
        *,
        workdir: Path,
        name: str = "episode",
        cancel: threading.Event | None = None,
    ) -> Result[VerifierReport]:
        """``outcome verify`` on one contract and its evidence."""
        workdir.mkdir(parents=True, exist_ok=True)
        cpath = workdir / f"{name}.contract.json"
        epath = workdir / f"{name}.evidence.jsonl"
        cpath.write_text(json.dumps(contract, sort_keys=True), encoding="utf-8")
        epath.write_text("".join(json.dumps(r, sort_keys=True) + "\n" for r in evidence), encoding="utf-8")
        run = self._run(["--json", "outcome", "verify", f"--contract={cpath}", f"--evidence={epath}"], cancel=cancel)
        if run.returncode not in VERDICT_EXIT:
            raise EngineError(
                "engine.input_rejected" if run.returncode == 1 else "engine.exit",
                f"outcome verify exited {run.returncode}",
                {"stderr": run.stderr.strip()[-2000:], "name": name},
            )
        report = self._parse(VerifierReport, run)
        if VERDICT_EXIT[run.returncode] != report.verdict:
            raise EngineError(
                "engine.output_invalid",
                "exit code and reported verdict disagree",
                {"exit": run.returncode, "verdict": report.verdict},
            )
        return self._result(report, run)

    def ingest(
        self,
        store: Path,
        files: Sequence[Path],
        *,
        cancel: threading.Event | None = None,
        allow_rejections: bool = False,
    ) -> Result[IngestResult]:
        paths = [str(Path(f).resolve()) for f in files]
        run = self._run(["--json", "ops", "ingest", f"--store={store}", "--", *paths], cancel=cancel)
        if run.returncode not in (0, 3):
            raise EngineError(
                "engine.exit", f"ops ingest exited {run.returncode}", {"stderr": run.stderr.strip()[-2000:]}
            )
        result = self._parse(IngestResult, run)
        if result.rejected and not allow_rejections:
            raise EngineError(
                "engine.input_rejected",
                f"the engine rejected {len(result.rejected)} record(s)",
                {"rejected": result.rejected[:50], "count": len(result.rejected)},
            )
        expected = self.config.interfaces.get("ops_rules_version")
        if expected and result.rebuild.rules_version != expected:
            raise EngineError(
                "engine.interface_mismatch",
                "correlation rules version differs from the lock",
                {"expected": expected, "actual": result.rebuild.rules_version},
            )
        return self._result(result, run)

    def compare(
        self,
        store: Path,
        *,
        task_type: str,
        a: str,
        b: str,
        verified: bool,
        paired: bool = False,
        per_attempt: bool = False,
        no_strata: bool = False,
        min_known: int | None = None,
        margin: float | None = None,
        expect_a: set[str] | None = None,
        expect_b: set[str] | None = None,
        cancel: threading.Event | None = None,
    ) -> Result[Comparison]:
        """``ops compare``. The engine answers an unknown release label with an empty arm and a warning, not an
        error; ``expect_a`` / ``expect_b`` (manifest digests) turn any other resolution into an error."""
        args = [
            "--json",
            "ops",
            "compare",
            f"--store={store}",
            self._value("task-type", task_type),
            self._value("a", a),
            self._value("b", b),
        ]
        if verified:
            args.append("--verified")
        if paired:
            args.append("--paired")
        if per_attempt:
            args.append("--per-attempt")
        if no_strata:
            args.append("--no-strata")
        if min_known is not None:
            args.append(f"--min-known={int(min_known)}")
        if margin is not None:
            args.append(f"--margin={float(margin)!r}")
        run = self._run(args, cancel=cancel)
        if run.returncode != 0:
            raise EngineError(
                "engine.exit", f"ops compare exited {run.returncode}", {"stderr": run.stderr.strip()[-2000:]}
            )
        comparison = self._parse(Comparison, run)
        for arm, expected in ((comparison.a, expect_a), (comparison.b, expect_b)):
            if expected is not None and set(arm.manifests) != expected:
                raise EngineError(
                    "engine.input_rejected",
                    f"release {arm.selector!r} resolves to other manifests than the ones evaluated",
                    {"selector": arm.selector, "expected": sorted(expected), "resolved": arm.manifests},
                )
        return self._result(comparison, run)

    def incidents(self, store: Path, *, cancel: threading.Event | None = None) -> Result[list[IncidentSummary]]:
        run = self._run(["--json", "ops", "incidents", f"--store={store}"], cancel=cancel)
        if run.returncode != 0:
            raise EngineError(
                "engine.exit", f"ops incidents exited {run.returncode}", {"stderr": run.stderr.strip()[-2000:]}
            )
        return self._result(self._parse_list(IncidentSummary, run), run)

    def show(self, store: Path, incident_id: str, *, cancel: threading.Event | None = None) -> Result[IncidentDetail]:
        run = self._run(["--json", "ops", "show", f"--store={store}", "--", incident_id], cancel=cancel)
        if run.returncode != 0:
            raise EngineError(
                "engine.exit", f"ops show exited {run.returncode}", {"stderr": run.stderr.strip()[-2000:]}
            )
        return self._result(self._parse(IncidentDetail, run), run)
