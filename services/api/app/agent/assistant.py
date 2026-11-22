"""The engineering assistant's door into the tool layer: the SAME typed tools the MCP server serves (pap_agent_tools),
run as the caller. Nothing here has more access than the caller: each tool calls the platform API over HTTP with the
caller's own Authorization header, so roles and workspace isolation apply unchanged. Only the read-only tools are
reachable here: a proposal is recorded through its own route by a person, never as a side effect of a question.

The tools call back into this same server on its own listening port (``request.scope['server']``), because they are a
client of the public API by design (they have no database access); ``PAP_ASSISTANT_LOOPBACK_URL`` overrides it.
"""

from __future__ import annotations

import json
import os
from typing import Annotated, Any

from fastapi import APIRouter, Header, Request
from pap_agent_tools.client import PlatformClient, ToolError
from pap_agent_tools.mcp_server import call as call_tool
from pap_agent_tools.mcp_server import tool_listing
from pap_agent_tools.tools import READ_ONLY
from pydantic import BaseModel, Field

from ..auth.deps import ViewerDep, error

router = APIRouter(prefix="/api/v1/orgs/{org_slug}/assistant", tags=["assistant"])


class ToolDescriptor(BaseModel):
    name: str
    description: str
    input_schema: dict[str, Any]


class ToolCallIn(BaseModel):
    arguments: dict[str, Any] = Field(default_factory=dict)


class ToolCallOut(BaseModel):
    tool: str
    arguments: dict[str, Any]
    is_error: bool
    result: Any
    read_only: bool = True


@router.get("/tools")
def list_tools(ctx: ViewerDep) -> list[ToolDescriptor]:
    """The tools the assistant may call here: the read-only ones, with their JSON Schemas."""
    return [
        ToolDescriptor(name=t["name"], description=t["description"], input_schema=t["inputSchema"])
        for t in tool_listing()
        if t["name"] in READ_ONLY
    ]


def _loopback(request: Request) -> str:
    override = os.environ.get("PAP_ASSISTANT_LOOPBACK_URL")
    if override:
        return override
    server = request.scope.get("server")
    port = server[1] if server and server[1] else 8000
    return f"http://127.0.0.1:{port}"


@router.post("/tools/{tool_name}")
def call(
    tool_name: str,
    body: ToolCallIn,
    ctx: ViewerDep,
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
) -> ToolCallOut:
    if tool_name not in READ_ONLY:
        raise error(404, "not_found", "no such read-only tool")
    args = dict(body.arguments)
    if args.setdefault("org", ctx.org.slug) != ctx.org.slug:
        raise error(422, "assistant.org", "a tool call may only name the workspace it is made in")
    token = (authorization or "").removeprefix("Bearer ").strip()
    try:
        client = PlatformClient(_loopback(request), token)
    except ToolError as e:
        raise error(401, "auth.unauthenticated", str(e)) from None
    out = call_tool(client, tool_name, args)
    text = out["content"][0]["text"]
    return ToolCallOut(
        tool=tool_name,
        arguments=args,
        is_error=bool(out["isError"]),
        result=text if out["isError"] else json.loads(text),
    )
