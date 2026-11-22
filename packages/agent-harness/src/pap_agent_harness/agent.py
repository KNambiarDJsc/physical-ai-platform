"""One harness session: a Strands agent with the platform's tools, a capped model and a trace."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pap_agent_tools.client import PlatformClient
from strands import Agent
from strands.hooks import BeforeToolCallEvent
from strands.models import Model
from strands.tools.tools import PythonAgentTool

from .budget import Budget, BudgetExceeded
from .models import CappedModel
from .toolbox import Toolbox
from .trace import Trace

SYSTEM = """You are an engineering assistant inside a Physical AI platform for robotics and laboratory teams.
You work only through the tools you are given; each runs as the person who started you, with their permissions.

Rules you never break:
- Say only what the tools returned. Cite the ids you rely on (run ids, request ids, recording ids, evidence ids,
  digests). If something is not in a tool result, say it is not known.
- Verdicts are the OpenMHS engine's. A trial whose verdict is VIOLATED is one run breaking its contract;
  it is NOT a release regression. Only the engine's release comparison (list_release_verdicts) can say
  regression, improvement, no change or insufficient evidence; report its verdict and reasons as given.
- Simulated evidence is simulated: say so when you report it.
- You cannot approve, start a run or command a device. If more evidence is needed you may, when the tool is offered,
  request a run of an exact experiment version or propose a workflow run, with a plain rationale; a person decides.

Answer with: a short answer first, then findings (each with the ids it rests on), then what is not known."""


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


def _budget_cause(e: BaseException | None) -> BudgetExceeded | None:
    while e is not None:
        if isinstance(e, BudgetExceeded):
            return e
        e = e.__cause__ or e.__context__
    return None


@dataclass
class Session:
    trace: Trace
    budget: Budget
    trace_path: Path | None


def run_session(
    *,
    question: str,
    org: str,
    model: Model,
    model_label: str,
    client: PlatformClient,
    budget: Budget,
    allow_requests: bool = False,
    trace_dir: Path | None = None,
) -> Session:
    trace = Trace(question=question, model=model_label, org=org, allow_requests=allow_requests)
    toolbox = Toolbox(client, trace, allow_requests=allow_requests)
    agent = Agent(
        model=CappedModel(model, budget, trace),
        tools=platform_tools(toolbox),  # type: ignore[arg-type]
        system_prompt=SYSTEM + f"\n\nThe workspace is '{org}'. Pass org=\"{org}\" to every tool.",
        callback_handler=None,
    )

    def refuse_unknown(event: BeforeToolCallEvent) -> None:
        """A tool the session did not offer (a write without --allow-requests, or a name that does not exist): the
        toolbox records the refusal in the trace, and the model is told why instead of the call running."""
        if event.selected_tool is None:
            res = toolbox.call(str(event.tool_use.get("name")), dict(event.tool_use.get("input") or {}))
            event.cancel_tool = json.dumps(res)

    agent.hooks.add_callback(BeforeToolCallEvent, refuse_unknown)
    try:
        result = agent(question)
        trace.answer = str(result).strip()
        trace.stop = "answered"
    except Exception as e:  # a spent budget surfaces wrapped in the agent loop's own exception
        cap = _budget_cause(e)
        if cap is None:
            raise
        trace.stop = f"stopped: {cap}"
    path = trace.write(trace_dir, budget.report()) if trace_dir else None
    return Session(trace, budget, path)
