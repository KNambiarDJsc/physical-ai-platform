"""SIM-001: the simulation host contract, tested through the platform's own adapter against a real host process.

The scenarios are the host's self-test ones (a deterministic computation, not a simulator): what is being tested is the
plumbing: discovery, validation, execution of the operator's fixed commands, honest failure, idempotency, serialisation
and artifact serving. The Gazebo scenario is exercised in test_experiments_gazebo.py.
"""

from __future__ import annotations

import hashlib
import itertools
import threading
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import httpx
import pytest
from pap_device_sdk import AdapterError, WotHttpAdapter
from pap_device_sdk.testing import run_sim_host

ROOT = Path(__file__).resolve().parents[3]
CATALOG = ROOT / "runtimes" / "sim-host" / "catalogs" / "selftest.json"
DEV = "simulation-host"


@pytest.fixture(scope="module")
def host(tmp_path_factory: pytest.TempPathFactory) -> Iterator[str]:
    with run_sim_host(ROOT, CATALOG, work=tmp_path_factory.mktemp("simhost")) as url:
        yield url


@pytest.fixture
def adapter(host: str) -> WotHttpAdapter:
    return WotHttpAdapter(host)


def rid(tag: str) -> str:
    return f"{tag}-{time.monotonic_ns()}"[:64]


def run(
    adapter: WotHttpAdapter, scenario: str, params: dict[str, Any], request_id: str | None = None, timeout: float = 60
):
    return adapter.invoke_action(
        DEV,
        "run_scenario",
        {"scenario": scenario, "scenario_version": "1", "parameters": params, "request_id": request_id or rid("req")},
        timeout_s=timeout,
    )


def test_the_host_is_discovered_as_a_simulated_thing_with_its_catalog_and_an_idempotent_action(
    adapter: WotHttpAdapter,
) -> None:
    devices = {d.key: d for d in adapter.discover()}
    d = devices[DEV]
    caps = {c.name: c for c in d.affordances}
    assert d.declares_simulated is True
    assert adapter.read_property(DEV, "simulated") is True
    assert adapter.read_property(DEV, "contract") == "pap.simulation-host/1"
    sim = adapter.read_property(DEV, "simulator")
    assert sim["kind"] == "selftest" and "Not a simulator" in sim["description"]
    scenarios = {s["id"]: s for s in adapter.read_property(DEV, "scenarios")}
    assert {"selftest-sum", "selftest-sleep"} <= set(scenarios)
    s = scenarios["selftest-sum"]
    assert s["parameters_schema"]["additionalProperties"] is False and s["max_duration_s"] == 60
    assert [o["name"] for o in s["outputs"]] == ["sum", "rows"] and s["artifacts"][0]["media_type"] == "text/csv"
    assert "command" not in s  # the operator's command is never shown to callers
    act = caps["run_scenario"]
    assert act.kind == "action" and act.idempotency_key == "request_id"  # the executor may safely re-send it
    assert isinstance(adapter.read_property(DEV, "runs"), list)


def test_a_run_returns_exactly_what_the_scenario_measured_and_left_with_verifiable_artifacts(
    adapter: WotHttpAdapter,
) -> None:
    inv = run(adapter, "selftest-sum", {"a": 2.5, "b": 4, "rows": 5})
    assert inv.status == "completed", inv
    out = inv.output
    assert out["state"] == "completed" and out["measurements"] == {"sum": 6.5, "rows": 5}
    assert out["identity"]["kind"] == "selftest" and out["simulator"]["kind"] == "selftest"
    assert out["duration_s"] >= 0 and out["started_at"] < out["finished_at"] and out["repeated"] is False
    (art,) = out["artifacts"]
    body, headers = adapter.fetch_bytes(DEV, f"runs/{out['run_id']}/artifacts/telemetry", 1 << 20)
    assert hashlib.sha256(body).hexdigest() == art["sha256"] == headers["x-artifact-sha256"]
    assert art["size_bytes"] == len(body)
    rows = body.decode().strip().splitlines()
    assert rows[0] == "i,value" and rows[1:] == [
        "0,2.5",
        "1,6.5",
        "2,10.5",
        "3,14.5",
        "4,18.5",
    ]  # the parameters, computed
    assert out["run_id"] in {r["run_id"] for r in adapter.read_property(DEV, "runs")}


def test_a_repeated_request_id_returns_the_stored_result_and_runs_nothing(adapter: WotHttpAdapter) -> None:
    key = rid("idem")
    first = run(adapter, "selftest-sum", {"a": 1, "b": 2}, key).output
    again = run(adapter, "selftest-sum", {"a": 1, "b": 2}, key).output
    assert again["run_id"] == first["run_id"] and again["repeated"] is True and first["repeated"] is False
    assert again["measurements"] == first["measurements"]
    other = run(adapter, "selftest-sum", {"a": 1, "b": 2}, rid("idem2")).output
    assert other["run_id"] != first["run_id"]
    reused = run(adapter, "selftest-sum", {"a": 9, "b": 9}, key)  # the same id for a different request
    assert reused.status == "error" and "request_id_reused" in (reused.error or "")


def test_unknown_scenarios_and_parameters_outside_the_schema_are_refused_before_anything_starts(
    adapter: WotHttpAdapter,
) -> None:
    before = len(adapter.read_property(DEV, "runs"))
    bad = [
        ("selftest-nope", {}),
        ("selftest-sum", {"a": 1}),  # b is required
        ("selftest-sum", {"a": 1, "b": 2000}),  # out of range
        ("selftest-sum", {"a": 1, "b": 2, "command": "rm -rf /"}),  # additionalProperties: false
        ("selftest-sum", {"a": "one", "b": 2}),
        ("selftest-sleep", {"seconds": -1}),
    ]
    for scenario, params in bad:
        inv = run(adapter, scenario, params)
        assert inv.status == "error", (scenario, params, inv)
    assert len(adapter.read_property(DEV, "runs")) == before  # nothing was started
    wrong_version = adapter.invoke_action(
        DEV,
        "run_scenario",
        {"scenario": "selftest-sum", "scenario_version": "9", "parameters": {"a": 1, "b": 1}, "request_id": rid("v")},
        timeout_s=30,
    )
    assert wrong_version.status == "error" and "unknown_scenario" in (wrong_version.error or "")


def test_failures_are_failures_never_a_made_up_success(adapter: WotHttpAdapter) -> None:
    failed = run(adapter, "selftest-fail", {})
    assert (
        failed.status == "error"
        and "command_failed" in (failed.error or "")
        and "asked to fail" in (failed.error or "")
    )
    missing = run(adapter, "selftest-no-measurement", {})
    assert (
        missing.status == "error"
        and "bad_result" in (missing.error or "")
        and "missing ['sum']" in (missing.error or "")
    )
    escaped = run(adapter, "selftest-escape", {})
    assert escaped.status == "error" and "inside the run directory" in (escaped.error or "")
    slow = run(adapter, "selftest-sleep", {"seconds": 8})  # the catalog limit is 5 s
    assert slow.status == "error" and "timeout" in (slow.error or "") and "5 s" in (slow.error or "")
    states = {r["scenario"]: r for r in adapter.read_property(DEV, "runs")}
    assert states["selftest-fail"]["state"] == "failed" and states["selftest-sleep"]["state"] == "failed"
    assert all(r["error"] for r in adapter.read_property(DEV, "runs") if r["state"] == "failed")
    # a failed run's repeat is the same failure, not a retry
    key = rid("again")
    one, two = run(adapter, "selftest-fail", {}, key), run(adapter, "selftest-fail", {}, key)
    assert one.status == two.status == "error"


def test_only_listed_artifacts_of_recorded_runs_are_served(adapter: WotHttpAdapter, host: str) -> None:
    out = run(adapter, "selftest-sum", {"a": 1, "b": 1}).output
    base = f"{host}/{DEV}/runs/{out['run_id']}/artifacts"
    assert httpx.get(f"{base}/telemetry", timeout=10).status_code == 200
    for bad in ("params.json", "result.json", "..%2Frecord.json", "nope", "telemetry/../params.json"):
        assert httpx.get(f"{base}/{bad}", timeout=10).status_code in (404, 405, 422), bad
    assert httpx.get(f"{host}/{DEV}/runs/{'0' * 32}/artifacts/telemetry", timeout=10).status_code == 404
    with pytest.raises(AdapterError, match="HTTP 404"):
        adapter.fetch_bytes(DEV, f"runs/{out['run_id']}/artifacts/params.json", 1 << 20)
    with pytest.raises(AdapterError, match="larger than 10 bytes"):
        adapter.fetch_bytes(DEV, f"runs/{out['run_id']}/artifacts/telemetry", 10)


def test_runs_are_serialised_one_scenario_at_a_time(host: str) -> None:
    """Two simultaneous requests: the second waits for the first instead of sharing the simulator. Checked on the host's
    own start and finish times of each run, not on the callers' clocks: which caller reaches the host first is a race
    (on CI the second thread sometimes did), but the two runs must never overlap."""
    from datetime import datetime

    runs: dict[str, dict[str, Any]] = {}

    def go(tag: str) -> None:
        inv = run(WotHttpAdapter(host), "selftest-sleep", {"seconds": 1.5}, rid(tag), timeout=60)
        assert inv.status == "completed", inv
        runs[tag] = inv.output

    threads = [threading.Thread(target=go, args=(t,)) for t in ("one", "two")]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=90)
    assert set(runs) == {"one", "two"}
    spans = sorted(
        (datetime.fromisoformat(r["started_at"]), datetime.fromisoformat(r["finished_at"])) for r in runs.values()
    )
    (a0, a1), (b0, b1) = spans
    assert all(r["repeated"] is False for r in runs.values()) and runs["one"]["run_id"] != runs["two"]["run_id"]
    assert b0 >= a1  # the second run started only after the first had finished
    assert (a1 - a0).total_seconds() >= 1.4 and (b1 - b0).total_seconds() >= 1.4  # each really waited its 1.5 s


def test_on_wait_is_called_repeatedly_while_a_long_action_runs(adapter: WotHttpAdapter) -> None:
    beats: list[float] = []
    inv = adapter.invoke_action(
        DEV,
        "run_scenario",
        {
            "scenario": "selftest-sleep",
            "scenario_version": "1",
            "parameters": {"seconds": 3},
            "request_id": rid("beat"),
        },
        timeout_s=60,
        on_wait=lambda: beats.append(time.monotonic()),
        on_wait_every_s=0.5,
    )
    assert inv.status == "completed"
    assert len(beats) >= 3  # about every half second for a 3 s run: this is how the worker keeps its lease
    assert all(b - a >= 0.4 for a, b in itertools.pairwise(beats))


def test_a_catalog_whose_command_names_an_undeclared_parameter_is_refused_at_start(tmp_path: Path) -> None:
    import json
    import shutil
    import subprocess

    base = json.loads(CATALOG.read_text(encoding="utf-8"))
    base["scenarios"][0]["command"] = ["{python}", "x.py", "{param.nope}"]
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps(base), encoding="utf-8")
    uv = shutil.which("uv")
    assert uv
    p = subprocess.run(
        [uv, "run", "--quiet", "--project", str(ROOT / "runtimes" / "sim-host"), "python", "-m", "pap_sim_host.server",
         "--catalog", str(bad), "--port", "1"],
        capture_output=True, text=True, check=False, timeout=120,
    )  # fmt: skip
    assert p.returncode != 0 and "command placeholder {param.nope}" in p.stderr
