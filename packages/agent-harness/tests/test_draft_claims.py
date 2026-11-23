"""An answer must not claim an action that is not in the trace. With drafting on, an answer that says it drafted a
follow-up when no draft was recorded gets a note marked as the platform's own. Scripted stand-in model (labelled in
every trace): these tests say nothing about how a real model behaves."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import httpx
from pap_agent_harness.agent import Options, run_session
from pap_agent_harness.budget import Budget
from pap_agent_harness.models import ScriptedModel
from pap_agent_tools.client import PlatformClient

PROPOSE = (
    "propose_experiment",
    {"org": "lab", "workflow": "w", "rationale": "Repeat once to check.", "evidence_ids": []},
)


def ask(turns: list[dict[str, Any]], tmp_path: Path, draft: bool = True):  # type: ignore[no-untyped-def]
    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.path == "/api/v1/me":
            return httpx.Response(200, json={"kind": "user", "organizations": [{"slug": "lab", "role": "engineer"}]})
        return httpx.Response(404, json={"detail": {"code": "not_found", "message": "nope"}})

    http = httpx.Client(transport=httpx.MockTransport(handler), base_url="http://platform.test")
    return run_session(
        question="Why?", model=ScriptedModel(turns), model_label=ScriptedModel.label,
        client=PlatformClient("http://platform.test", "dev:ada", http=http), budget=Budget(100_000, 1.0),
        options=Options(org="lab", draft_requests=draft, trace_dir=tmp_path / "t"),
    )  # fmt: skip


def test_a_claimed_draft_that_was_never_recorded_is_corrected_by_the_platform(tmp_path: Path) -> None:
    s = ask([{"text": "I have drafted a proposal to repeat the run."}], tmp_path)
    assert "Added by the platform, not by the model" in (s.trace.answer or "") and "Nothing was drafted" in (
        s.trace.answer or ""
    )


def test_a_recorded_draft_needs_no_correction(tmp_path: Path) -> None:
    s = ask([{"tools": [PROPOSE]}, {"text": "I drafted a proposal to repeat the run."}], tmp_path)
    assert "Added by the platform" not in (s.trace.answer or "")
    assert [st["output"]["drafted"] for st in s.trace.steps if st.get("tool") == "propose_experiment"] == [True]


def test_without_drafting_the_word_alone_is_not_corrected(tmp_path: Path) -> None:
    s = ask([{"text": "I drafted nothing; drafting is off."}], tmp_path, draft=False)
    assert "Added by the platform" not in (s.trace.answer or "")
