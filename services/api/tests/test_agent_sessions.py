"""AGT-002: the Agent page's backend runs one harness session as the caller and keeps the trace.

The runner here is the labelled stand-in ``fake_harness.py`` (same command line, no model): these tests are about what
the API guarantees around a session. How the real harness behaves is tested in packages/agent-harness, and with a real
model only by a real run."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from helpers import add_member, as_user, make_org, ok

ORG = "/api/v1/orgs/lab"
ALICE = as_user("alice")  # admin
EVE = as_user("eve")  # engineer
VIC = as_user("vic")  # viewer


def setting(monkeypatch: pytest.MonkeyPatch, name: str, value: str) -> None:
    from app.config import get_settings

    monkeypatch.setenv(name, value)
    get_settings.cache_clear()


@pytest.fixture
def lab(client: TestClient) -> TestClient:
    make_org(client, "alice", "lab")
    add_member(client, "alice", "lab", "eve", "engineer")
    add_member(client, "alice", "lab", "vic", "viewer")
    return client


def state_dir(monkeypatch_env: Any = None) -> Path:
    from app.config import get_settings

    return get_settings().agent_state_path


def ask(c: TestClient, question: str, headers: dict[str, str] = EVE, org: str = "lab") -> Any:
    return c.post(f"/api/v1/orgs/{org}/agent/sessions", json={"question": question}, headers=headers)


def wait(c: TestClient, sid: str, headers: dict[str, str] = EVE, org: str = "lab") -> dict[str, Any]:
    for _ in range(100):
        d = ok(c.get(f"/api/v1/orgs/{org}/agent/sessions/{sid}", headers=headers))
        if d["state"] != "running":
            return d  # type: ignore[no-any-return]
        time.sleep(0.2)
    raise AssertionError("the session never finished")


def test_status_says_what_is_and_is_not_configured(lab: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    for n in ("PAP_LLM_API_KEY", "PAP_LLM_BASE_URL", "PAP_LLM_MODEL"):
        monkeypatch.delenv(n, raising=False)
    s = ok(lab.get(f"{ORG}/agent/status", headers=EVE))
    assert s["runner_available"] is True and s["model_configured"] is False and s["model"] is None
    assert s["can_ask"] is True and ok(lab.get(f"{ORG}/agent/status", headers=VIC))["can_ask"] is False
    credential = "FAKE-MODEL-CREDENTIAL-0123456789"
    monkeypatch.setenv("PAP_LLM_API_KEY", credential)
    monkeypatch.setenv("PAP_LLM_BASE_URL", "https://llm.example/v1")
    monkeypatch.setenv("PAP_LLM_MODEL", "some-model")
    r = lab.get(f"{ORG}/agent/status", headers=EVE)
    assert r.json()["model_configured"] is True and r.json()["model"] == "some-model"
    assert (
        credential not in r.text and "llm.example" not in r.text
    )  # presence only: the key and the endpoint stay server-side


def test_a_viewer_can_read_but_not_ask_and_nobody_unauthenticated_can_do_either(lab: TestClient) -> None:
    assert ask(lab, "list experiments", VIC).status_code == 403  # asking costs money: engineers
    assert ask(lab, "list experiments", {}).status_code == 401
    assert lab.get(f"{ORG}/agent/sessions").status_code == 401
    assert ok(lab.get(f"{ORG}/agent/sessions", headers=VIC)) == []


def test_a_session_runs_as_the_caller_with_a_minimal_environment_and_keeps_its_trace(
    lab: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PAP_LLM_API_KEY", "FAKE-MODEL-CREDENTIAL-0123456789")
    r = ask(lab, "Why did the pre-fix run fail?")
    assert r.status_code == 202, r.text
    started = r.json()
    assert started["state"] == "running" and started["asked_by"] == "eve" and not started["answer"]
    d = wait(lab, started["id"])
    assert d["state"] == "done" and d["answer"] == "fake answer to: Why did the pre-fix run fail?"
    assert d["route"] == "agent" and d["model"] == "fake" and d["stop"] == "answered"
    assert d["usage"]["usd"] == 0.0123 and d["usage"]["input_tokens"] == 10
    assert [s["kind"] for s in d["steps"]] == ["tool", "tool", "model"]
    assert d["steps"][1]["output"] == {"omitted": "larger than the page shows; the stored trace has it whole"}
    # what the subprocess received: the caller's own credential, the workspace, and no server secret
    seen = json.loads((state_dir() / f"seen-{started['id']}.json").read_text(encoding="utf-8"))
    assert seen["token"] == "dev:eve" and seen["org"] == "lab"
    assert "PAP_API_TOKEN" in seen["pap_env"] and "PAP_LLM_API_KEY" in seen["pap_env"]
    assert "PAP_DATABASE_URL" not in seen["pap_env"] and "PAP_STORAGE_PATH" not in seen["pap_env"]
    assert "--allow-requests" not in seen["argv"]  # the website never lets the agent even record a request
    listed = ok(lab.get(f"{ORG}/agent/sessions", headers=VIC))  # a viewer may read what an engineer asked
    assert [x["id"] for x in listed] == [started["id"]] and "steps" not in listed[0]


def test_a_question_is_data_never_an_option(lab: TestClient) -> None:
    q = "--allow-requests --max-usd 999 please"
    sid = ask(lab, q).json()["id"]
    d = wait(lab, sid)
    assert d["state"] == "done" and d["answer"] == f"fake answer to: {q}"
    argv = json.loads((state_dir() / f"seen-{sid}.json").read_text(encoding="utf-8"))["argv"]
    assert argv[-2:] == ["--", q] and "--allow-requests" not in argv[:-2] and "999" not in argv[:-1]
    assert ask(lab, "x").status_code == 422 and ask(lab, "a" * 1001).status_code == 422
    assert ask(lab, "bad\x00question").status_code == 422


def test_another_workspace_cannot_see_a_session(lab: TestClient) -> None:
    sid = wait(lab, ask(lab, "list experiments").json()["id"])["id"]
    make_org(lab, "mallory", "other")
    mal = as_user("mallory")
    assert lab.get(f"{ORG}/agent/sessions/{sid}", headers=mal).status_code == 404  # not a member of lab
    assert (
        lab.get(f"/api/v1/orgs/other/agent/sessions/{sid}", headers=mal).status_code == 404
    )  # lab's id, her workspace
    assert ok(lab.get("/api/v1/orgs/other/agent/sessions", headers=mal)) == []
    assert lab.get(f"{ORG}/agent/sessions/not-an-id", headers=ALICE).status_code == 422


def test_the_daily_limits_refuse_before_any_spend(lab: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    setting(monkeypatch, "PAP_AGENT_DAILY_SESSIONS", "3")
    setting(monkeypatch, "PAP_AGENT_DAILY_USD", "0.02")
    wait(lab, ask(lab, "first question").json()["id"])  # costs 0.0123 in the stand-in
    wait(lab, ask(lab, "second question").json()["id"])  # 0.0246 spent in total: over the 0.02 dollar cap
    r = ask(lab, "third question")
    assert r.status_code == 429 and r.json()["detail"]["code"] == "agent.daily_spend"
    setting(monkeypatch, "PAP_AGENT_DAILY_USD", "100")
    setting(monkeypatch, "PAP_AGENT_DAILY_SESSIONS", "2")
    r = ask(lab, "third question")
    assert r.status_code == 429 and r.json()["detail"]["code"] == "agent.daily_sessions"
    s = ok(lab.get(f"{ORG}/agent/status", headers=EVE))
    assert s["sessions_today"] == 2 and s["usd_today"] == pytest.approx(0.0246)


def test_sessions_running_at_once_are_limited(lab: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    setting(monkeypatch, "PAP_AGENT_MAX_RUNNING", "1")
    first = ask(lab, "SLOW one").json()["id"]
    r = ask(lab, "second question")
    assert r.status_code == 429 and r.json()["detail"]["code"] == "agent.busy"
    assert wait(lab, first)["state"] == "done"
    assert ask(lab, "second question").status_code == 202


def test_a_failed_session_says_why_without_leaking_a_secret(lab: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    key = "FAKE-MODEL-CREDENTIAL-0123456789"
    monkeypatch.setenv("PAP_LLM_API_KEY", key)
    d = wait(lab, ask(lab, "FAIL on purpose").json()["id"])
    assert d["state"] == "failed" and d["answer"] is None
    assert "boom" in d["error"] and key not in d["error"] and "dev:eve" not in d["error"] and "[removed]" in d["error"]


def test_a_session_left_running_by_a_restart_is_reported_as_interrupted(lab: TestClient) -> None:
    status = state_dir() / "status"
    status.mkdir(parents=True, exist_ok=True)
    sid = "c" * 32
    (status / f"{sid}.json").write_text(
        json.dumps({"id": sid, "org": "lab", "asked_by": "eve", "question": "q", "state": "running",
                    "started_at": "2026-01-01T00:00:00+00:00", "finished_at": None, "error": None}),
        encoding="utf-8",
    )  # fmt: skip
    d = ok(lab.get(f"{ORG}/agent/sessions/{sid}", headers=EVE))
    assert d["state"] == "interrupted" and "restarted" in d["error"]


def test_asking_is_audited_without_the_question_text(lab: TestClient) -> None:
    from app.db import get_engine
    from sqlalchemy import text

    secret_words = "unmistakable-question-words"
    wait(lab, ask(lab, secret_words).json()["id"])
    with get_engine().connect() as conn:
        rows = conn.execute(text("select action, detail::text from audit_events where action = 'agent.ask'")).all()
    assert len(rows) == 1 and "question_sha256" in rows[0][1] and secret_words not in rows[0][1]


def test_a_follow_up_is_drafted_only_when_the_engineer_asks_for_it_and_is_never_sent(lab: TestClient) -> None:
    plain = ask(lab, "DRAFT a repeat run").json()["id"]
    wait(lab, plain)
    assert (
        "--draft-requests" not in json.loads((state_dir() / f"seen-{plain}.json").read_text(encoding="utf-8"))["argv"]
    )
    r = lab.post(f"{ORG}/agent/sessions", json={"question": "DRAFT a repeat run", "propose": True}, headers=EVE)
    assert r.status_code == 202
    sid = r.json()["id"]
    d = wait(lab, sid)
    argv = json.loads((state_dir() / f"seen-{sid}.json").read_text(encoding="utf-8"))["argv"]
    assert "--draft-requests" in argv and "--allow-requests" not in argv  # a draft, never a request
    draft = next(s for s in d["steps"] if s.get("tool") == "propose_experiment")
    assert draft["output"]["drafted"] is True and draft["output"]["filed"] is False
    assert ok(lab.get(f"{ORG}/experiment-proposals", headers=ALICE)) == []  # nothing was proposed by the agent
    # a viewer cannot ask at all, with or without the box
    assert (
        lab.post(f"{ORG}/agent/sessions", json={"question": "DRAFT x", "propose": True}, headers=VIC).status_code == 403
    )


def test_a_server_that_cannot_keep_sessions_says_so_instead_of_failing(
    lab: TestClient, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A non-root container on a read-only file system: the page must show 'unavailable', not break."""
    blocker = tmp_path / "a-file"
    blocker.write_text("not a directory", encoding="utf-8")
    setting(monkeypatch, "PAP_AGENT_STATE_PATH", str(blocker / "agent"))  # a directory cannot be created under a file
    s = ok(lab.get(f"{ORG}/agent/status", headers=EVE))
    assert s["runner_available"] is False and s["can_ask"] is True
    assert ok(lab.get(f"{ORG}/agent/sessions", headers=EVE)) == []
    r = ask(lab, "list experiments")
    assert r.status_code == 503 and r.json()["detail"]["code"] == "agent.unavailable"
    assert lab.get(f"{ORG}/agent/sessions/{'a' * 32}", headers=EVE).status_code == 404


def test_without_the_harness_installed_the_runner_is_unavailable(
    lab: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    setting(monkeypatch, "PAP_AGENT_COMMAND", "")
    monkeypatch.setattr("app.agent.sessions.shutil.which", lambda _name: None)  # no uv on this server
    assert ok(lab.get(f"{ORG}/agent/status", headers=EVE))["runner_available"] is False
    assert ask(lab, "list experiments").status_code == 503
