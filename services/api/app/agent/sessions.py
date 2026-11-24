"""The Agent page's backend: run one harness session as the caller, keep its trace, never touch the model key.

The harness (``packages/agent-harness``, D-039) is a separate uv project so its model framework never enters this
environment. A session is therefore a subprocess of the operator's command, started with the caller's own credential,
so the platform's roles and workspace isolation apply to everything it reads. This module adds what a website needs
around it and nothing the harness already does:

* the key is read by the harness from ``PAP_LLM_*`` in the server's environment; it is not a setting here, never
  returned, and scrubbed from anything stored;
* the question travels as an argument after ``--`` (never through a shell, never parsed as an option);
* spend is bounded three ways: the harness's own per-session cap, a daily cap over all sessions on this server, and a
  limit on sessions running at once; asking needs the engineer role because asking costs money;
* the agent never writes: the website never passes ``--allow-requests``. At most it may DRAFT a follow-up
  (``--draft-requests``, when the engineer ticks the box): the draft stays in the trace and a person files it.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
import threading
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Header, Request
from fastapi import Path as PathParam
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from ..auth.deps import EngineerDep, ViewerDep, audit_allow, error
from ..config import REPO_ROOT, get_settings
from ..db import get_session
from .assistant import _loopback

router = APIRouter(prefix="/api/v1/orgs/{org_slug}/agent", tags=["agent-sessions"])
SessionDep = Annotated[Session, Depends(get_session)]
SID = re.compile(r"^[0-9a-f]{32}$")
MAX_OUTPUT_JSON = 20_000  # a tool output larger than this is summarised in the page; the trace file keeps it whole

_RUNNING: dict[str, threading.Thread] = {}
_LOCK = threading.Lock()


# --------------------------------------------------------------------------------------------------- configuration


def _command() -> list[str] | None:
    s = get_settings()
    if s.agent_command:
        raw = s.agent_command.strip()
        return [str(x) for x in json.loads(raw)] if raw.startswith("[") else shlex.split(raw)
    uv = shutil.which("uv")
    project = REPO_ROOT / "packages" / "agent-harness"
    return [uv, "run", "--quiet", "--project", str(project), "pap-harness"] if uv and project.is_dir() else None


def _model() -> tuple[bool, str | None, bool]:
    """(configured, model name, priced). Presence only: the key itself is never read here."""
    configured = all(os.environ.get(n) for n in ("PAP_LLM_API_KEY", "PAP_LLM_BASE_URL", "PAP_LLM_MODEL"))
    priced = bool(os.environ.get("PAP_LLM_USD_PER_M_INPUT") and os.environ.get("PAP_LLM_USD_PER_M_OUTPUT"))
    return configured, os.environ.get("PAP_LLM_MODEL") if configured else None, priced


def _dirs() -> tuple[Path, Path]:
    """The status and trace directories. Pure: nothing is created, so reading never fails on a read-only disk."""
    base = get_settings().agent_state_path
    return base / "status", base / "traces"


def _state_writable() -> bool:
    """Whether sessions can be kept here. A non-root container on a read-only disk cannot; the page says so."""
    status_dir, _ = _dirs()
    try:
        status_dir.mkdir(parents=True, exist_ok=True)
    except OSError:
        return False
    return os.access(status_dir, os.W_OK)


# --------------------------------------------------------------------------------------------------------- state


def _write(path: Path, doc: dict[str, Any]) -> None:
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(doc, indent=1, sort_keys=True), encoding="utf-8")
    tmp.replace(path)


def _read(sid: str) -> dict[str, Any] | None:
    status_dir, _ = _dirs()
    p = status_dir / f"{sid}.json"
    if not p.is_file():
        return None
    st: dict[str, Any] = json.loads(p.read_text(encoding="utf-8"))
    with _LOCK:
        alive = sid in _RUNNING and _RUNNING[sid].is_alive()
    if st["state"] == "running" and not alive:  # the server restarted mid-session
        st.update(state="interrupted", error="The server restarted while this session was running.")
        _write(p, st)
    return st


def _trace(sid: str) -> dict[str, Any] | None:
    _, traces = _dirs()
    p = traces / f"{sid}.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.is_file() else None


def _today() -> tuple[int, float]:
    """Sessions started today (UTC) and the dollars they cost, over every workspace on this server."""
    status_dir, _ = _dirs()
    today = datetime.now(UTC).date().isoformat()
    count, usd = 0, 0.0
    for p in status_dir.glob("*.json"):
        st = json.loads(p.read_text(encoding="utf-8"))
        if str(st.get("started_at", ""))[:10] != today:
            continue
        count += 1
        t = _trace(p.stem)
        usd += float(((t or {}).get("usage") or {}).get("usd") or 0.0)
    return count, usd


def _scrub(text: str, secrets: list[str]) -> str:
    for s in secrets:
        if s and len(s) >= 6:
            text = text.replace(s, "[removed]")
    return text


# ------------------------------------------------------------------------------------------------------ models


class AskIn(BaseModel):
    focus: Literal["general", "robotics", "laboratory", "release"] = "general"
    question: str = Field(min_length=3, max_length=1000)
    # The agent may DRAFT a follow-up experiment. It is recorded in the trace and sent nowhere: a person files it
    # from the page, as themselves, and a different person must still approve it.
    propose: bool = False

    @field_validator("question")
    @classmethod
    def _plain(cls, v: str) -> str:
        v = v.strip()
        if len(v) < 3 or any(ord(c) < 32 and c not in "\n\t" for c in v):
            raise ValueError("a question is plain text of at least 3 characters")
        return v


class AgentStatus(BaseModel):
    runner_available: bool
    model_configured: bool
    model: str | None
    priced: bool  # false: only the token cap bounds a session, not dollars
    role: str
    can_ask: bool
    session_usd_cap: float
    daily_usd_cap: float
    daily_sessions_cap: int
    sessions_today: int
    usd_today: float
    max_steps: int
    timeout_s: float


class SessionOut(BaseModel):
    id: str
    question: str
    state: Literal["running", "done", "failed", "interrupted"]
    asked_by: str
    started_at: str
    finished_at: str | None
    route: str | None = None  # "agent" (a model wrote it) or "fast:<name>" (a fixed tool call, no model)
    model: str | None = None
    stop: str | None = None
    answer: str | None = None
    grounding: dict[str, Any] | None = None
    usage: dict[str, Any] | None = None
    duration_s: float | None = None
    error: str | None = None


class SessionDetail(SessionOut):
    steps: list[dict[str, Any]] = Field(default_factory=list)


def _fields(st: dict[str, Any], t: dict[str, Any] | None) -> dict[str, Any]:
    base: dict[str, Any] = {
        k: st.get(k) for k in ("id", "question", "state", "asked_by", "started_at", "finished_at", "error")
    }
    if t:
        base.update({k: t.get(k) for k in ("route", "model", "stop", "answer", "grounding", "usage", "duration_s")})
    return base


def _summary(st: dict[str, Any]) -> SessionOut:
    t = _trace(st["id"]) if st["state"] != "running" else None
    return SessionOut(**_fields(st, t))


def _detail(st: dict[str, Any]) -> SessionDetail:
    t = _trace(st["id"]) if st["state"] != "running" else None
    shown: list[dict[str, Any]] = []
    for s in (t or {}).get("steps", []):
        s = dict(s)
        if "output" in s and len(json.dumps(s["output"], default=str)) > MAX_OUTPUT_JSON:
            s["output"] = {"omitted": "larger than the page shows; the stored trace has it whole"}
        shown.append(s)
    return SessionDetail(**_fields(st, t), steps=shown)


# ------------------------------------------------------------------------------------------------------ routes


@router.get("/status")
def agent_status(ctx: ViewerDep) -> AgentStatus:
    s = get_settings()
    configured, model, priced = _model()
    count, usd = _today()
    return AgentStatus(
        runner_available=_command() is not None and _state_writable(),
        model_configured=configured,
        model=model,
        priced=priced,
        role=ctx.role,
        can_ask=ctx.role in ("engineer", "admin"),
        session_usd_cap=s.agent_session_usd,
        daily_usd_cap=s.agent_daily_usd,
        daily_sessions_cap=s.agent_daily_sessions,
        sessions_today=count,
        usd_today=round(usd, 6),
        max_steps=s.agent_max_steps,
        timeout_s=s.agent_timeout_s,
    )


@router.get("/sessions")
def list_sessions(ctx: ViewerDep) -> list[SessionOut]:
    status_dir, _ = _dirs()
    files = sorted(status_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    out: list[SessionOut] = []
    for p in files:
        st = _read(p.stem)
        if st and st.get("org") == ctx.org.slug:
            out.append(_summary(st))
        if len(out) >= 30:
            break
    return out


@router.get("/sessions/{session_id}")
def get_session_detail(session_id: Annotated[str, PathParam(pattern=SID.pattern)], ctx: ViewerDep) -> SessionDetail:
    st = _read(session_id)
    if st is None or st.get("org") != ctx.org.slug:  # another workspace's session is simply not found
        raise error(404, "not_found", "no such session")
    return _detail(st)


@router.post("/sessions", status_code=202)
def ask(
    body: AskIn,
    ctx: EngineerDep,
    request: Request,
    session: SessionDep,
    authorization: Annotated[str | None, Header()] = None,
) -> SessionOut:
    s = get_settings()
    cmd = _command()
    if cmd is None:
        raise error(503, "agent.unavailable", "The agent runner is not installed on this server.")
    if not _state_writable():
        raise error(
            503, "agent.unavailable", "This server cannot keep agent sessions: its state directory is not writable."
        )
    token = (authorization or "").removeprefix("Bearer ").strip()
    if not token:
        raise error(401, "auth.unauthenticated", "sign in to ask the agent")
    count, usd = _today()
    if count >= s.agent_daily_sessions:
        raise error(429, "agent.daily_sessions", f"The daily limit of {s.agent_daily_sessions} sessions is reached.")
    if usd >= s.agent_daily_usd:
        raise error(429, "agent.daily_spend", f"The daily spend limit of ${s.agent_daily_usd:.2f} is reached.")
    with _LOCK:
        busy = sum(1 for t in _RUNNING.values() if t.is_alive())
        if busy >= s.agent_max_running:
            raise error(429, "agent.busy", "Other sessions are still running. Try again in a moment.")
        sid = uuid.uuid4().hex
        status_dir, _ = _dirs()
        st = {
            "id": sid,
            "org": ctx.org.slug,
            "asked_by": ctx.principal.label.split("|")[-1],
            "question": body.question,
            "state": "running",
            "started_at": datetime.now(UTC).isoformat(timespec="seconds"),
            "finished_at": None,
            "error": None,
        }
        _write(status_dir / f"{sid}.json", st)
        argv = [
            *cmd, "ask", "--org", ctx.org.slug, "--api", _loopback(request),
            "--max-usd", str(s.agent_session_usd), "--max-steps", str(s.agent_max_steps),
            "--timeout-s", str(s.agent_timeout_s), "--state", str(s.agent_state_path), "--session", sid,
            "--allow-no-model",
            *(["--focus", body.focus] if body.focus != "general" else []),
            *(["--draft-requests"] if body.propose else []),
            "--", body.question,
        ]  # fmt: skip
        # Only what the harness needs: the model settings and the caller's credential. No database URL, no other secret.
        env = {k: v for k, v in os.environ.items() if not k.startswith("PAP_") or k.startswith("PAP_LLM_")}
        env.update(PAP_API_TOKEN=token, PYTHONUTF8="1")
        worker = threading.Thread(target=_execute, args=(sid, argv, env, s.agent_timeout_s), daemon=True)
        _RUNNING[sid] = worker
        worker.start()
    audit_allow(
        session,
        ctx,
        "agent.ask",
        f"agent_session:{sid}",
        question_sha256=hashlib.sha256(body.question.encode()).hexdigest(),
    )
    session.commit()
    return _summary(st)


def _execute(sid: str, argv: list[str], env: dict[str, str], timeout_s: float) -> None:
    status_dir, traces = _dirs()
    path = status_dir / f"{sid}.json"
    secrets = [os.environ.get("PAP_LLM_API_KEY", ""), env.get("PAP_API_TOKEN", "")]
    state, err = "done", None
    try:
        p = subprocess.run(
            argv, env=env, stdin=subprocess.DEVNULL, capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=timeout_s + 30, cwd=str(REPO_ROOT),
        )  # fmt: skip
        if not (traces / f"{sid}.json").is_file():
            state, err = "failed", _scrub((p.stderr or p.stdout or "the harness left no trace")[-1500:], secrets)
    except subprocess.TimeoutExpired:
        state, err = "failed", "The session did not finish in time and was stopped."
    except OSError as e:
        state, err = "failed", _scrub(f"the harness could not start: {e}", secrets)
    st = json.loads(path.read_text(encoding="utf-8"))
    st.update(state=state, error=err, finished_at=datetime.now(UTC).isoformat(timespec="seconds"))
    _write(path, st)
    with _LOCK:
        _RUNNING.pop(sid, None)
