"""The platform's tools as the agent sees them. Every call runs as the caller (their token, their role) through the
platform API, so the platform's own permissions apply on top of these. The two writes only record something for a
person to decide, and are offered only when the session was started with requests allowed."""

from __future__ import annotations

import json
from typing import Any

from pap_agent_tools.client import PlatformClient, ToolError
from pap_agent_tools.tools import TOOLS, WRITES
from pydantic import ValidationError

from .trace import Trace

MAX_OUTPUT_CHARS = 20_000  # what the model is shown of one tool output; the trace keeps all of it


class Toolbox:
    def __init__(self, client: PlatformClient, trace: Trace, allow_requests: bool = False) -> None:
        self.client, self.trace, self.allow_requests = client, trace, allow_requests

    def names(self) -> list[str]:
        return [n for n in TOOLS if self.allow_requests or n not in WRITES]

    def specs(self) -> list[dict[str, Any]]:
        return [
            {"name": n, "description": TOOLS[n].description, "input_schema": TOOLS[n].model.model_json_schema()}
            for n in self.names()
        ]

    def call(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
        """Run one tool. Refusals and errors are answers the model can read, never exceptions that end the session."""
        if name not in self.names():
            why = "requests are not allowed in this session" if name in WRITES else "no such tool"
            self.trace.tool(name, args, permitted=False, error=why)
            return {"error": f"refused: {why}"}
        t = TOOLS[name]
        try:
            a = t.model.model_validate(args)
        except ValidationError as e:
            msg = "; ".join(f"{'.'.join(map(str, x['loc']))}: {x['msg']}" for x in e.errors())
            self.trace.tool(name, args, permitted=True, error=f"invalid input: {msg}")
            return {"error": f"invalid input: {msg}"}
        try:
            out = t.fn(self.client, a)
        except ToolError as e:
            self.trace.tool(name, args, permitted=True, error=str(e))
            return {"error": str(e)}
        self.trace.tool(name, args, permitted=True, output=out)
        text = json.dumps(out, default=str)
        if len(text) > MAX_OUTPUT_CHARS:
            return {"result_truncated": True, "chars": len(text), "result_head": text[:MAX_OUTPUT_CHARS]}
        return {"result": out}
