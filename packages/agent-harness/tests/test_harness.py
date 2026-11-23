"""The harness's orchestration guarantees, tested with a SCRIPTED model (a labelled stand-in that decides nothing) and
an in-memory double of the platform API that records what was asked. These tests say nothing about how well a real
language model investigates; that is measured only with a real model (HAR-001 evidence). The platform's own behaviour
is tested in services/api."""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Any

import httpx
import pytest
from pap_agent_harness import grounding
from pap_agent_harness.agent import SYSTEM, Options, run_session
from pap_agent_harness.budget import Budget, BudgetExceeded
from pap_agent_harness.config import LLMSettings, NotConfigured
from pap_agent_harness.ledger import Ledger
from pap_agent_harness.models import ScriptedModel
from pap_agent_harness.providers import build_model
from pap_agent_tools.client import PlatformClient

RUN = "5f1f2b9e-0000-4000-8000-000000000001"
TRIAL_RUN = "aaaaaaaa-0000-4000-8000-000000000002"


class Platform:
    """Answers a few API paths and records every request (method, path, body). Optional delay and failures."""

    def __init__(self, role: str | None = "viewer", delay_s: float = 0.0, fail_first: int = 0) -> None:
        self.calls: list[tuple[str, str, Any]] = []
        self.role, self.delay_s, self.fail_first = role, delay_s, fail_first
        self._lock = threading.Lock()

    def handler(self, req: httpx.Request) -> httpx.Response:
        body = json.loads(req.content) if req.content else None
        p = req.url.path
        if p == "/api/v1/me":
            orgs = [{"slug": "lab", "role": self.role}] if self.role else []
            return httpx.Response(200, json={"kind": "user", "organizations": orgs})
        with self._lock:
            self.calls.append((req.method, p, body))
            if self.fail_first > 0:
                self.fail_first -= 1
                return httpx.Response(503, json={"detail": {"code": "busy", "message": "try later"}})
        if self.delay_s:
            time.sleep(self.delay_s)
        if p.endswith("/experiments") and req.method == "GET":
            return httpx.Response(200, json=[{"slug": "stop", "name": "Stop", "description": "", "versions": [],
                                               "requests": [{"id": RUN, "state": "approved", "trials": 2, "trials_done": 2}]}])  # fmt: skip  # noqa: E501
        if p.endswith(f"/experiment-requests/{RUN}"):
            return httpx.Response(200, json={
                "id": RUN, "experiment_name": "Stop", "version": 1, "state": "approved", "trials": 1, "trials_done": 1,
                "trial_results": [{"arm": "pre-fix", "repetition": 0, "state": "succeeded", "verdict": "VIOLATED",
                                   "run_id": TRIAL_RUN, "measurements": {"travel_after_kill_m": 1.0}}],
            })  # fmt: skip
        if p.endswith("/release-evaluations"):
            return httpx.Response(200, json=[])
        if p.endswith("/simulation-environments"):
            return httpx.Response(200, json=[])
        if p.endswith("/versions/1/requests") and req.method == "POST":
            return httpx.Response(201, json={"id": "req-1", "state": "awaiting_approval"})
        return httpx.Response(404, json={"detail": {"code": "not_found", "message": "not found"}})

    def client(self) -> PlatformClient:
        http = httpx.Client(transport=httpx.MockTransport(self.handler), base_url="http://platform.test")
        return PlatformClient("http://platform.test", "dev:ada", http=http)


def session(turns: list[dict[str, Any]], platform: Platform, tmp_path: Path, question: str = "Why did it fail?",
            budget: Budget | None = None, **kw: Any):  # type: ignore[no-untyped-def]  # fmt: skip
    opts = Options(org="lab", trace_dir=tmp_path / "traces", **kw)
    return run_session(question=question, model=ScriptedModel(turns), model_label=ScriptedModel.label,
                       client=platform.client(), budget=budget or Budget(100_000, 1.0), options=opts)  # fmt: skip


def doc(s) -> dict[str, Any]:  # type: ignore[no-untyped-def]
    return json.loads(s.trace_path.read_text(encoding="utf-8"))  # type: ignore[no-any-return]


# ---------------------------------------------------------------------------------------- orchestration basics


def test_a_session_reads_through_the_tools_and_answers_with_a_full_grounded_trace(tmp_path: Path) -> None:
    p = Platform()
    s = session([{"tools": [("get_experiment_run", {"org": "lab", "request_id": RUN})]},
                 {"text": f"The pre-fix trial violated its contract (trial run {TRIAL_RUN}). Not a release regression."}],  # noqa: E501
                p, tmp_path)  # fmt: skip
    d = doc(s)
    assert d["stop"] == "answered" and d["route"] == "agent" and d["model"].startswith("scripted")
    assert [st["kind"] for st in d["steps"]] == ["model", "tool", "model"]
    assert d["steps"][1]["output_sha256"].startswith("sha256:")
    assert d["grounding"] == {"cited": [TRIAL_RUN], "unsupported": [], "uncited": False, "grounded": True}
    assert d["usage"]["model_calls"] == 2


def test_an_answer_citing_ids_no_tool_returned_is_flagged_as_unsupported(tmp_path: Path) -> None:
    made_up = "11111111-2222-4333-8444-555555555555"
    s = session([{"tools": [("get_experiment_run", {"org": "lab", "request_id": RUN})]},
                 {"text": f"It failed, see run {made_up}."}], Platform(), tmp_path)  # fmt: skip
    assert doc(s)["grounding"]["unsupported"] == [made_up] and doc(s)["grounding"]["grounded"] is False
    assert grounding.check("A plain answer.", [{"kind": "tool", "permitted": True, "output": {}}])["uncited"] is True


def test_routine_questions_take_a_deterministic_fast_path_without_a_model(tmp_path: Path) -> None:
    p = Platform()
    s = session([], p, tmp_path, question=f"status of run {RUN}")
    d = doc(s)
    assert d["route"] == "fast:run_status" and d["usage"]["model_calls"] == 0
    assert f"[run:{TRIAL_RUN}]" in d["answer"] and "not a release regression" in d["answer"]
    assert doc(session([], Platform(), tmp_path, question="list experiments"))["route"] == "fast:list_experiments"
    assert (
        doc(session([{"text": "x"}], Platform(), tmp_path, question=f"status of run {RUN}", fast_paths=False))["route"]
        == "agent"
    )


# --------------------------------------------------------------------------------------- permissions, approval


def test_discovery_is_scoped_to_the_callers_membership(tmp_path: Path) -> None:
    p = Platform(role=None)
    s = session([{"text": "never"}], p, tmp_path)
    assert s.trace.stop == "stopped: not a member of workspace lab" and p.calls == [] and s.budget.calls == 0


def test_writes_need_the_session_to_allow_them_and_the_operator_to_approve_each_one(tmp_path: Path) -> None:
    req = (
        "request_experiment_run",
        {"org": "lab", "experiment": "stop", "version": 1, "rationale": "more evidence please"},
    )
    p = Platform()
    s = session([{"tools": [req, ("approve_experiment_request", {"org": "lab"})]}, {"text": "done"}], p, tmp_path)
    tools = [st for st in s.trace.steps if st["kind"] == "tool"]
    assert {(st["tool"], st["permitted"]) for st in tools} == {
        ("request_experiment_run", False),
        ("approve_experiment_request", False),
    }
    assert p.calls == []  # nothing reached the platform
    asked: list[str] = []
    p2 = Platform()
    session([{"tools": [req]}, {"text": "declined"}], p2, tmp_path, allow_requests=True,
            approve=lambda n, a: asked.append(n) is not None)  # fmt: skip  # returns False: the operator declines
    assert asked == ["request_experiment_run"] and p2.calls == []
    p3 = Platform()
    session([{"tools": [req]}, {"text": "asked"}], p3, tmp_path, allow_requests=True, approve=lambda n, a: True)
    assert p3.calls == [
        ("POST", "/api/v1/orgs/lab/experiments/stop/versions/1/requests", {"note": "more evidence please"})
    ]


# ------------------------------------------------------------------------- parallelism, recovery, bounds, limits


def test_independent_read_calls_in_one_turn_run_in_parallel(tmp_path: Path) -> None:
    p = Platform(delay_s=0.4)
    reads = [("list_experiments", {"org": "lab"}), ("list_simulation_environments", {"org": "lab"}),
             ("list_release_verdicts", {"org": "lab", "experiment": "stop"})]  # fmt: skip
    t0 = time.monotonic()
    s = session([{"tools": reads}, {"text": "ok"}], p, tmp_path)
    took = time.monotonic() - t0
    assert len([st for st in s.trace.steps if st["kind"] == "tool" and st["permitted"]]) == 3
    assert took < 1.0, took  # three 0.4 s reads one after another would take 1.2 s


def test_transient_platform_failures_are_retried_a_bounded_number_of_times(tmp_path: Path) -> None:
    p = Platform(fail_first=2)
    s = session([{"tools": [("list_experiments", {"org": "lab"})]}, {"text": "ok"}], p, tmp_path)
    assert len(p.calls) == 3 and s.trace.steps[1]["error"] is None  # two 503s, then the answer
    p2 = Platform(fail_first=5)
    s2 = session([{"tools": [("list_experiments", {"org": "lab"})]}, {"text": "ok"}], p2, tmp_path)
    assert len(p2.calls) == 3 and "HTTP 503" in s2.trace.steps[1]["error"]  # gave up after its retries, told the model


def test_planning_is_bounded_by_a_step_limit(tmp_path: Path) -> None:
    loop = [{"tools": [("list_experiments", {"org": "lab"})]}] * 10
    s = session(loop, Platform(), tmp_path, max_calls=3)
    assert s.trace.stop == "stopped: step limit reached: 3 model calls" and s.budget.calls == 3


def test_the_session_stops_before_a_call_that_would_exceed_its_budget(tmp_path: Path) -> None:
    turns = [{"tools": [("list_experiments", {"org": "lab"})], "usage": (200, 60)}, {"text": "never reached"}]
    s = session(turns, Platform(), tmp_path, budget=Budget(max_tokens=250, max_usd=1.0))
    assert s.trace.stop == "stopped: token cap reached: 260 of 250 tokens used" and s.budget.calls == 1
    priced = Budget(max_tokens=10**9, max_usd=0.01, usd_per_m_input=50.0, usd_per_m_output=50.0)
    priced.add(150, 100)
    with pytest.raises(BudgetExceeded, match=r"spend cap reached: \$0\.0125 of \$0\.01"):
        priced.check()


def test_an_experiment_budget_holds_across_sessions(tmp_path: Path) -> None:
    ledger = Ledger(tmp_path / "ledger.json")
    kw: dict[str, Any] = {"experiment": "stop", "experiment_max_tokens": 300, "ledger": ledger}
    s1 = session([{"text": "first", "usage": (150, 50)}], Platform(), tmp_path, **kw)
    assert s1.trace.stop == "answered" and ledger.entry("lab/stop")["tokens"] == 200
    s2 = session(
        [{"tools": [("list_experiments", {"org": "lab"})], "usage": (90, 20)}, {"text": "x"}],
        Platform(),
        tmp_path,
        **kw,
    )
    assert s2.trace.stop.startswith("stopped: experiment lab/stop has used its token budget")
    s3 = session([{"text": "never"}], Platform(), tmp_path, **kw)
    assert s3.trace.stop.startswith("stopped: experiment lab/stop") and s3.budget.calls == 0  # refused before starting
    assert set(ledger.entry("lab/stop")["sessions"]) == {s1.trace.id, s2.trace.id, s3.trace.id}


def test_cancellation_and_timeouts_stop_the_session_cleanly(tmp_path: Path) -> None:
    cancel = threading.Event()
    cancel.set()
    s = session([{"text": "never"}], Platform(), tmp_path, cancel=cancel)
    assert s.trace.stop in ("stopped: cancelled", "stopped: timed out") and s.budget.calls == 0
    slow = Platform(delay_s=0.6)
    s2 = session([{"tools": [("list_experiments", {"org": "lab"})]}, {"text": "late"}], slow, tmp_path, timeout_s=0.3)
    assert s2.trace.stop == "stopped: timed out" and s2.trace.answer is None


def test_a_session_persists_and_resumes_its_conversation(tmp_path: Path) -> None:
    sessions = tmp_path / "sessions"
    session([{"text": "first answer"}], Platform(), tmp_path, session_id="s-1", sessions_dir=sessions)
    m = ScriptedModel([{"text": "second answer"}])
    run_session(question="and then?", model=m, model_label=m.label, client=Platform().client(), budget=Budget(10**5, 1.0),  # noqa: E501
                options=Options(org="lab", session_id="s-1", sessions_dir=sessions))  # fmt: skip
    texts = json.dumps(m.seen[0])
    assert "first answer" in texts and "and then?" in texts  # the resumed session saw the earlier exchange


# --------------------------------------------------------------------------------------------- configuration


def test_providers_are_configuration_and_the_key_never_appears(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    for k in ("PAP_LLM_API_KEY", "PAP_LLM_BASE_URL", "PAP_LLM_MODEL"):
        monkeypatch.delenv(k, raising=False)
    with pytest.raises(NotConfigured, match="PAP_LLM_API_KEY"):
        LLMSettings.from_env()
    monkeypatch.setenv("PAP_LLM_API_KEY", "sk-test-SECRET-123")
    monkeypatch.setenv("PAP_LLM_BASE_URL", "https://llm.example/v1")
    monkeypatch.setenv("PAP_LLM_MODEL", "some-model")
    s = LLMSettings.from_env(max_usd=0.2)
    assert "SECRET" not in repr(s) and s.max_usd == 0.2
    assert type(build_model(s, "openai")).__name__ == "OpenAIModel"  # constructed, nothing sent
    with pytest.raises(NotConfigured, match="unknown provider"):
        build_model(s, "nope")
    sess = session([{"text": "hello"}], Platform(), tmp_path, sessions_dir=tmp_path / "sessions", session_id="k")
    stored = "".join(p.read_text(encoding="utf-8", errors="ignore") for p in tmp_path.rglob("*") if p.is_file())
    assert "SECRET" not in stored and sess.trace.stop == "answered"  # not in traces, sessions or anything written


def test_the_instructions_keep_violations_and_regressions_apart() -> None:
    assert "NOT a release regression" in SYSTEM and "cannot approve" in SYSTEM and "not known" in SYSTEM


def test_the_cli_prints_any_unicode_a_model_streams_even_on_a_legacy_console_code_page(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import io
    import sys

    from pap_agent_harness.__main__ import utf8_streams

    raw = io.BytesIO()
    legacy = io.TextIOWrapper(raw, encoding="cp1252", errors="strict")  # what a Windows console defaults to
    with pytest.raises(UnicodeEncodeError):
        legacy.write("non‑breaking")
        legacy.flush()
    legacy = io.TextIOWrapper(io.BytesIO(), encoding="cp1252", errors="strict")
    monkeypatch.setattr(sys, "stdout", legacy)
    utf8_streams()
    sys.stdout.write("non‑breaking → ok")
    sys.stdout.flush()
    assert sys.stdout.buffer.getvalue().decode("utf-8") == "non‑breaking → ok"


def test_ids_written_with_unicode_hyphens_are_still_checked() -> None:
    real = "d46bca2f-e322-450c-b19a-e029e645369e"
    fake = "11111111-2222-4333-8444-555555555555"
    steps = [{"kind": "tool", "permitted": True, "output": {"id": real}}]
    typed = f"trial {real.replace('-', chr(0x2011))} and {fake.replace('-', chr(0x2011))}"  # non-breaking hyphens
    g = grounding.check(typed, steps)
    assert g["cited"] == sorted([real, fake]) and g["unsupported"] == [fake] and g["grounded"] is False


def test_an_approval_that_cannot_be_answered_is_a_refusal_not_a_failure(tmp_path: Path) -> None:
    req = (
        "request_experiment_run",
        {"org": "lab", "experiment": "stop", "version": 1, "rationale": "more evidence please"},
    )

    def no_one_to_ask(name: str, args: dict[str, Any]) -> bool:
        raise EOFError

    p = Platform()
    s = session([{"tools": [req]}, {"text": "I would have requested a run for more evidence."}], p, tmp_path,
                allow_requests=True, approve=no_one_to_ask)  # fmt: skip
    st = s.trace.steps[1]
    assert st["permitted"] is False and "not approved" in st["error"] and p.calls == []
    assert s.trace.stop == "answered" and s.budget.calls == 2  # the session went on to answer; nothing was retried
