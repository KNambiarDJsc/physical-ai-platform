"""One harness session: routine questions by a deterministic fast path, everything else by a Strands agent with the
platform's tools behind a capped model. Sessions persist (conversation and trace), stop cleanly on a budget, a step
limit, a timeout or cancellation, and every answer is checked against the evidence the tools returned."""

from __future__ import annotations

import json
import re
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pap_agent_tools.client import PlatformClient, ToolError
from strands import Agent
from strands.hooks import BeforeToolCallEvent
from strands.models import Model
from strands.session.file_session_manager import FileSessionManager
from strands.tools.tools import PythonAgentTool

from . import grounding
from .budget import Budget, BudgetExceeded
from .fastpath import try_fast_path
from .focus import INSTRUCTIONS, Focus
from .ledger import Ledger
from .models import CappedModel, StopSession
from .toolbox import Approver, Progress, Toolbox
from .trace import Trace

SYSTEM = """You are an engineering assistant inside a Physical AI platform for robotics and laboratory teams.
You work only through the tools you are given; each runs as the person who started you, with their permissions.

Rules you never break:
- Say only what the tools returned. Cite the ids you rely on (run ids, request ids, recording ids, evaluation ids,
  digests) exactly as the tools gave them. If something is not in a tool result, say it is not known.
- Verdicts are the OpenMHS engine's. A trial whose verdict is VIOLATED is one run breaking its contract;
  it is NOT a release regression. Only the engine's release comparison (list_release_verdicts) can say
  regression, improvement, no change or insufficient evidence; report its verdict and reasons as given.
- Simulated evidence is simulated: say so when you report it.
- You cannot approve, start a run or command a device. If more evidence is needed you may, when the tool is offered,
  request a run of an exact experiment version or propose a workflow run, with a plain rationale; a person decides.
- Call independent read tools together in one turn. Stop once you can answer; do not loop.

Answer with: a short answer first, then findings (each with the ids it rests on), then what is not known."""


@dataclass
class Options:
    org: str
    allow_requests: bool = False
    approve: Approver | None = None  # the person running the session approves each write; None: no writes
    max_calls: int = 12  # bounded planning: model calls per session
    timeout_s: float | None = 300.0
    experiment: str | None = None  # scope a session to an experiment for its per-experiment cost limit
    experiment_max_tokens: int | None = None
    experiment_max_usd: float | None = None
    ledger: Ledger | None = None
    session_id: str | None = None  # persist and resume the conversation
    sessions_dir: Path | None = None
    trace_dir: Path | None = None
    fast_paths: bool = True
    draft_requests: bool = False  # the agent may DRAFT a follow-up; a person files it elsewhere (never sent from here)
    progress: Progress | None = None
    cancel: threading.Event = field(default_factory=threading.Event)
    focus: Focus = Focus.general


@dataclass
class Session:
    trace: Trace
    budget: Budget
    trace_path: Path | None


def platform_tools(toolbox: Toolbox) -> list[PythonAgentTool]:
    def make(spec: dict[str, Any]) -> PythonAgentTool:
        name = spec["name"]

        def run(tool_use: dict[str, Any], **_: Any) -> dict[str, Any]:
            res = toolbox.call(name, dict(tool_use.get("input") or {}))
            return {
                "toolUseId": tool_use["toolUseId"],
                "status": "error" if "error" in res else "success",
                "content": [{"text": json.dumps(res, default=str)}],
            }

        spec_ = {"name": name, "description": spec["description"], "inputSchema": {"json": spec["input_schema"]}}
        return PythonAgentTool(name, spec_, run)  # type: ignore[arg-type]

    return [make(s) for s in toolbox.specs()]


def _stop_cause(e: BaseException | None) -> BaseException | None:
    while e is not None:
        if isinstance(e, BudgetExceeded | StopSession):
            return e
        e = e.__cause__ or e.__context__
    return None


SIMULATED_NOTE = (
    "\n\n[Added by the platform, not by the model: the evidence above is SIMULATED. It comes from a simulated "
    "instrument bench, not physical hardware.]"
)


def _label_simulated(trace: Trace) -> None:
    """A model may forget the rule that simulated evidence is labelled. When any tool result says the evidence is
    simulated and the answer does not, the platform says it, in words marked as its own."""
    if trace.route != "agent" or not trace.answer or "simulat" in trace.answer.lower():
        return
    if any(
        s.get("kind") == "tool" and '"evidence_class": "simulated"' in json.dumps(s.get("output"), default=str)
        for s in trace.steps
    ):
        trace.answer += SIMULATED_NOTE


UNDRAFTED_NOTE = (
    "\n\n[Added by the platform, not by the model: no draft was recorded in this session, so the follow-up described "
    "above is only a suggestion. Nothing was drafted, filed or run.]"
)


def _label_undrafted(trace: Trace, o: Options) -> None:
    """A model may say it drafted a follow-up without calling the tool. An answer must not claim an action that is not
    in the trace: when drafting is on, the answer talks of a draft and no draft was recorded, the platform says so."""
    if not o.draft_requests or trace.route != "agent" or not trace.answer:
        return
    drafted = any(
        s.get("kind") == "tool" and isinstance(s.get("output"), dict) and s["output"].get("drafted")
        for s in trace.steps
    )
    if not drafted and re.search(r"\bdraft(ed|s)?\b", trace.answer, re.IGNORECASE):
        trace.answer += UNDRAFTED_NOTE


def _finish(trace: Trace, budget: Budget, o: Options) -> Session:
    _label_undrafted(trace, o)
    _label_simulated(trace)
    trace.grounding = grounding.check(trace.answer, trace.steps) if trace.route == "agent" else None
    if o.ledger and o.experiment:
        o.ledger.add(f"{o.org}/{o.experiment}", trace.id, budget.input_tokens + budget.output_tokens, budget.usd)
    path = trace.write(o.trace_dir, budget.report()) if o.trace_dir else None
    return Session(trace, budget, path)


NO_MODEL = (
    "No language model is configured on this server, so only the fixed questions are answered "
    "(status of run <id>, list experiments, verdicts for <experiment>)."
)


def run_session(
    *, question: str, model: Model | None, model_label: str, client: PlatformClient, budget: Budget, options: Options
) -> Session:
    o = options
    trace = Trace(question=question, model=model_label, org=o.org, allow_requests=o.allow_requests)
    if o.session_id:
        trace.id = o.session_id
    say: Callable[[str], None] = o.progress or (lambda _m: None)
    try:
        role = Toolbox.discover_role(client, o.org)
    except ToolError as e:
        trace.stop = f"stopped: {e}"
        return _finish(trace, budget, o)
    toolbox = Toolbox(
        client, trace, o.allow_requests, approve=o.approve, progress=o.progress, cancel=o.cancel, role=role,
        draft_writes=o.draft_requests, focus=o.focus,
    )  # fmt: skip
    if role is None:
        trace.stop = f"stopped: not a member of workspace {o.org}"
        return _finish(trace, budget, o)

    if o.fast_paths:
        fast = try_fast_path(question, toolbox, o.org)
        if fast:
            trace.route, trace.answer, trace.stop = f"fast:{fast[0]}", fast[1], "answered"
            say(f"answered by the {fast[0]} fast path (no model call)")
            return _finish(trace, budget, o)

    if model is None:  # nothing fixed matched and there is no model: say so, never guess
        trace.stop = f"stopped: {NO_MODEL}"
        return _finish(trace, budget, o)

    key = f"{o.org}/{o.experiment}" if o.experiment else None

    def experiment_gate() -> None:
        if o.ledger and key:
            used = budget.input_tokens + budget.output_tokens
            o.ledger.check(key, o.experiment_max_tokens, o.experiment_max_usd, used, budget.usd or 0.0)

    try:
        experiment_gate()  # refuse before starting when the experiment's budget is already spent
    except BudgetExceeded as e:
        trace.stop = f"stopped: {e}"
        return _finish(trace, budget, o)

    timer = None
    deadline = None
    if o.timeout_s:
        deadline = time.monotonic() + o.timeout_s
        timer = threading.Timer(o.timeout_s, o.cancel.set)
        timer.daemon = True
        timer.start()
    capped = CappedModel(
        model, budget, trace, max_calls=o.max_calls, deadline=deadline, cancel=o.cancel,
        before_call=experiment_gate, progress=o.progress,
    )  # fmt: skip
    session_manager = (
        FileSessionManager(session_id=trace.id, storage_dir=str(o.sessions_dir)) if o.sessions_dir else None
    )
    drafting = (
        "\n\nDrafting is on. When your investigation points to a follow-up experiment, DRAFT it once with "
        "propose_experiment: an existing workflow of this workspace (list_workflows shows them), a plain rationale and "
        "the evidence ids. A draft is only recorded; a person decides whether to file it and a second person must "
        "approve before anything runs. Then say what you drafted and why. "
        "Never describe a follow-up without drafting it."
        if o.draft_requests
        else ""
    )
    agent = Agent(
        model=capped,
        tools=platform_tools(toolbox),  # type: ignore[arg-type]
        system_prompt=SYSTEM
        + "\n"
        + INSTRUCTIONS[o.focus]
        + drafting
        + f'\n\nThe workspace is "{o.org}". Pass org="{o.org}" to every tool.',
        callback_handler=None,
        session_manager=session_manager,
    )

    def refuse_unknown(event: BeforeToolCallEvent) -> None:
        if event.selected_tool is None:  # not offered in this session: refused and traced, the model told why
            res = toolbox.call(str(event.tool_use.get("name")), dict(event.tool_use.get("input") or {}))
            event.cancel_tool = json.dumps(res)

    agent.hooks.add_callback(BeforeToolCallEvent, refuse_unknown)
    try:
        result = agent(question, cancel_signal=o.cancel)
        text = str(result).strip()
        if o.cancel.is_set():
            trace.stop = "stopped: timed out" if deadline and time.monotonic() >= deadline else "stopped: cancelled"
        else:
            trace.answer, trace.stop = text, "answered"
    except Exception as e:  # noqa: BLE001 - any failure of the agent loop is recorded as the session outcome
        cause = _stop_cause(e)
        trace.stop = f"failed: {type(e).__name__}: {e}" if cause is None else f"stopped: {cause}"
    finally:
        if timer:
            timer.cancel()
    say(trace.stop or "")
    return _finish(trace, budget, o)
