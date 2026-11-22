"""The harness's own guarantees, with a scripted model (a labelled test stand-in that decides nothing) and an in-memory
double of the platform API that records what was asked. The platform's own behaviour is tested in services/api; an
end-to-end run against a real stack is recorded in harness/features.json (HAR-001)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx
import pytest
from pap_agent_harness.agent import SYSTEM, run_session
from pap_agent_harness.budget import Budget, BudgetExceeded
from pap_agent_harness.config import LLMSettings, NotConfigured
from pap_agent_harness.models import ScriptedModel
from pap_agent_tools.client import PlatformClient

RUN = "5f1f2b9e-0000-4000-8000-000000000001"


class Platform:
    """Answers a few API paths and records every request (method, path, body)."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str, Any]] = []

    def handler(self, req: httpx.Request) -> httpx.Response:
        body = json.loads(req.content) if req.content else None
        self.calls.append((req.method, req.url.path, body))
        p = req.url.path
        if p.endswith("/experiments") and req.method == "GET":
            return httpx.Response(
                200, json=[{"slug": "stop", "name": "Stop", "description": "", "versions": [], "requests": []}]
            )
        if p.endswith(f"/experiment-requests/{RUN}"):
            return httpx.Response(
                200,
                json={
                    "id": RUN,
                    "trial_results": [
                        {"arm": "pre-fix", "verdict": "VIOLATED", "measurements": {"travel_after_kill_m": 1.0}}
                    ],
                },
            )
        if p.endswith("/versions/1/requests") and req.method == "POST":
            return httpx.Response(201, json={"id": "req-1", "state": "awaiting_approval"})
        return httpx.Response(404, json={"detail": {"code": "not_found", "message": "not found"}})

    def client(self) -> PlatformClient:
        return PlatformClient(
            "http://platform.test",
            "dev:ada",
            http=httpx.Client(transport=httpx.MockTransport(self.handler), base_url="http://platform.test"),
        )


def session(turns: list[dict[str, Any]], platform: Platform, tmp_path: Path, **kw: Any):  # type: ignore[no-untyped-def]
    budget = kw.pop("budget", Budget(max_tokens=100_000, max_usd=1.0))
    return run_session(
        question="Why did the pre-fix arm fail?",
        org="lab",
        model=ScriptedModel(turns),
        model_label=ScriptedModel.label,
        client=platform.client(),
        budget=budget,
        trace_dir=tmp_path,
        **kw,
    )


def test_a_session_reads_through_the_tools_and_answers_with_a_full_trace(tmp_path: Path) -> None:
    p = Platform()
    s = session(
        [
            {"tools": [("get_experiment_run", {"org": "lab", "request_id": RUN})]},
            {"text": f"The pre-fix trial violated its contract (run {RUN}). This is not a release regression."},
        ],
        p,
        tmp_path,
    )
    assert s.trace.stop == "answered" and "not a release regression" in (s.trace.answer or "")
    assert [c[:2] for c in p.calls] == [("GET", f"/api/v1/orgs/lab/experiment-requests/{RUN}")]
    doc = json.loads(s.trace_path.read_text(encoding="utf-8"))  # type: ignore[union-attr]
    assert doc["schema"] == "pap.agent-trace/1" and doc["model"].startswith("scripted")
    kinds = [st["kind"] for st in doc["steps"]]
    assert kinds == ["model", "tool", "model"]
    tool = doc["steps"][1]
    assert (
        tool["tool"] == "get_experiment_run"
        and tool["permitted"] is True
        and tool["output_sha256"].startswith("sha256:")
    )
    assert doc["usage"]["model_calls"] == 2 and doc["usage"]["input_tokens"] == 200


def test_writes_are_refused_unless_the_session_allows_requests_and_nothing_can_approve(tmp_path: Path) -> None:
    p = Platform()
    req = (
        "request_experiment_run",
        {"org": "lab", "experiment": "stop", "version": 1, "rationale": "more evidence please"},
    )
    s = session([{"tools": [req, ("approve_experiment_request", {"org": "lab"})]}, {"text": "done"}], p, tmp_path)
    refused = [st for st in s.trace.steps if st["kind"] == "tool"]
    assert [(st["tool"], st["permitted"]) for st in refused] == [
        ("request_experiment_run", False),
        ("approve_experiment_request", False),
    ]
    assert "requests are not allowed" in refused[0]["error"] and "no such tool" in refused[1]["error"]
    assert p.calls == []  # nothing reached the platform
    p2 = Platform()
    s2 = session([{"tools": [req]}, {"text": "asked"}], p2, tmp_path, allow_requests=True)
    assert p2.calls == [
        ("POST", "/api/v1/orgs/lab/experiments/stop/versions/1/requests", {"note": "more evidence please"})
    ]
    assert s2.trace.steps[1]["permitted"] is True


def test_the_session_stops_before_a_call_that_would_exceed_the_cap(tmp_path: Path) -> None:
    p = Platform()
    budget = Budget(max_tokens=250, max_usd=1.0)
    turns = [{"tools": [("list_experiments", {"org": "lab"})], "usage": (200, 60)}, {"text": "never reached"}]
    s = session(turns, p, tmp_path, budget=budget)
    assert s.trace.stop is not None and s.trace.stop.startswith("stopped: token cap reached") and s.trace.answer is None
    assert budget.calls == 1  # the second model call was never made
    priced = Budget(max_tokens=10**9, max_usd=0.01, usd_per_m_input=50.0, usd_per_m_output=50.0)
    priced.add(150, 100)
    with pytest.raises(BudgetExceeded, match=r"spend cap reached: \$0\.0125 of \$0\.01"):
        priced.check()


def test_invalid_tool_input_is_answered_not_raised(tmp_path: Path) -> None:
    p = Platform()
    s = session(
        [{"tools": [("get_experiment_run", {"org": "lab", "request_id": "not-a-uuid"})]}, {"text": "ok"}], p, tmp_path
    )
    st = s.trace.steps[1]
    assert st["permitted"] is True and st["error"].startswith("invalid input") and p.calls == []


def test_settings_come_from_the_environment_and_the_key_never_appears(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    for k in ("PAP_LLM_API_KEY", "PAP_LLM_BASE_URL", "PAP_LLM_MODEL"):
        monkeypatch.delenv(k, raising=False)
    with pytest.raises(NotConfigured, match="PAP_LLM_API_KEY"):
        LLMSettings.from_env()
    monkeypatch.setenv("PAP_LLM_API_KEY", "sk-test-SECRET-123")
    monkeypatch.setenv("PAP_LLM_BASE_URL", "https://llm.example/v1")
    monkeypatch.setenv("PAP_LLM_MODEL", "some-model")
    s = LLMSettings.from_env(max_usd=0.2)
    assert "SECRET" not in repr(s) and s.max_usd == 0.2
    sess = session([{"text": "hello"}], Platform(), tmp_path)
    assert "SECRET" not in sess.trace_path.read_text(encoding="utf-8")  # type: ignore[union-attr]


def test_the_instructions_keep_violations_and_regressions_apart() -> None:
    assert "NOT a release regression" in SYSTEM and "cannot approve" in SYSTEM and "not known" in SYSTEM
