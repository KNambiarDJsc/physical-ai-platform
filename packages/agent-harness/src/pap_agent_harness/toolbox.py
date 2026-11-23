"""The platform's tools as the agent sees them: typed (each tool's pydantic model is its JSON Schema), discovered per
session and scoped by permission, and run as the caller through the platform API so the platform's own roles apply on
top. Reads may run in parallel and are retried a bounded number of times on transient failures. The two writes only
record something for a person to decide; they are offered only when the session allows requests, run one at a time,
and each one needs the approval of the person running the session before it is sent."""

from __future__ import annotations

import json
import threading
import time
from collections.abc import Callable
from typing import Any

from pap_agent_tools.client import PlatformClient, ToolError
from pap_agent_tools.tools import TOOLS, WRITES
from pydantic import ValidationError

from .trace import Trace

MAX_OUTPUT_CHARS = 20_000  # what the model is shown of one tool output; the trace keeps all of it
READ_RETRIES = 2
Approver = Callable[[str, dict[str, Any]], bool]
Progress = Callable[[str], None]


def _transient(e: ToolError) -> bool:
    m = str(e)
    return "did not answer" in m or any(f"HTTP {c}" in m for c in (500, 502, 503, 504))


class Cancelled(RuntimeError):
    pass


class Toolbox:
    def __init__(
        self,
        client: PlatformClient,
        trace: Trace,
        allow_requests: bool = False,
        *,
        approve: Approver | None = None,
        progress: Progress | None = None,
        cancel: threading.Event | None = None,
        role: str | None = None,
        backoff_s: float = 0.5,
    ) -> None:
        self.client, self.trace, self.allow_requests = client, trace, allow_requests
        self.approve, self.progress, self.cancel, self.role = approve, progress, cancel, role
        self.backoff_s = backoff_s
        self._write_lock = threading.Lock()

    @classmethod
    def discover_role(cls, client: PlatformClient, org: str) -> str | None:
        """The caller's role in the workspace, from the platform (None: not a member, so no tool is offered)."""
        me = client.get("/api/v1/me")
        return next((o["role"] for o in me.get("organizations", []) if o["slug"] == org), None)

    def names(self) -> list[str]:
        if self.role is None and self.trace.org:  # discovery said the caller is not in this workspace
            return []
        writes_ok = self.allow_requests and self.approve is not None
        return [n for n in TOOLS if writes_ok or n not in WRITES]

    def specs(self) -> list[dict[str, Any]]:
        return [
            {"name": n, "description": TOOLS[n].description, "input_schema": TOOLS[n].model.model_json_schema()}
            for n in self.names()
        ]

    def _say(self, msg: str) -> None:
        if self.progress:
            self.progress(msg)

    def call(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
        """Run one tool. Refusals and errors are answers the model can read, never exceptions that end the session."""
        if self.cancel is not None and self.cancel.is_set():
            self.trace.tool(name, args, permitted=False, error="cancelled")
            return {"error": "cancelled: the session is stopping"}
        if name not in self.names():
            why = (
                "requests are not allowed in this session" if name in WRITES
                else "not a member of this workspace" if self.role is None and name in TOOLS
                else "no such tool"
            )  # fmt: skip
            self.trace.tool(name, args, permitted=False, error=why)
            self._say(f"refused {name}: {why}")
            return {"error": f"refused: {why}"}
        t = TOOLS[name]
        try:
            a = t.model.model_validate(args)
        except ValidationError as e:
            msg = "; ".join(f"{'.'.join(map(str, x['loc']))}: {x['msg']}" for x in e.errors())
            self.trace.tool(name, args, permitted=True, error=f"invalid input: {msg}")
            return {"error": f"invalid input: {msg}"}
        if name in WRITES:
            with self._write_lock:  # writes one at a time, each approved by the person running the session
                assert self.approve is not None
                try:
                    approved = bool(self.approve(name, args))
                except (
                    EOFError,
                    KeyboardInterrupt,
                    OSError,
                ):  # no one could answer: that is a refusal, never a failure
                    approved = False
                if not approved:
                    self.trace.tool(name, args, permitted=False, error="not approved by the person running the session")
                    self._say(f"{name} was not approved (do not ask again in this session)")
                    return {"error": "refused: the person running this session did not approve this request. "
                                     "Do not retry; say what you would have requested and why."}  # fmt: skip
                return self._run(name, t, a, args, retries=0)
        return self._run(name, t, a, args, retries=READ_RETRIES)

    def _run(self, name: str, t: Any, a: Any, args: dict[str, Any], retries: int) -> dict[str, Any]:
        self._say(f"calling {name}")
        for attempt in range(retries + 1):
            try:
                out = t.fn(self.client, a)
                break
            except ToolError as e:
                if attempt < retries and _transient(e) and not (self.cancel and self.cancel.is_set()):
                    self._say(f"{name}: {e}; retrying")
                    time.sleep(self.backoff_s * (attempt + 1))
                    continue
                self.trace.tool(name, args, permitted=True, error=str(e))
                self._say(f"{name} failed: {e}")
                return {"error": str(e)}
        self.trace.tool(name, args, permitted=True, output=out)
        self._say(f"{name} done")
        text = json.dumps(out, default=str)
        if len(text) > MAX_OUTPUT_CHARS:
            return {"result_truncated": True, "chars": len(text), "result_head": text[:MAX_OUTPUT_CHARS]}
        return {"result": out}
