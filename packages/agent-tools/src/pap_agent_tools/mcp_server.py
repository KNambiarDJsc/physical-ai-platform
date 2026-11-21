"""A minimal MCP server over stdio (newline-delimited JSON-RPC 2.0), tools capability only: initialize, ping,
tools/list, tools/call. It implements just that part of the protocol; it is not the official SDK."""

from __future__ import annotations

import json
import sys
from typing import Any, TextIO

from pydantic import ValidationError

from . import __version__
from .client import PlatformClient, ToolError
from .tools import TOOLS

PROTOCOL = "2025-06-18"


def tool_listing() -> list[dict[str, Any]]:
    out = []
    for t in TOOLS.values():
        schema = t.model.model_json_schema()
        schema.pop("title", None)
        out.append(
            {
                "name": t.name,
                "description": t.description,
                "inputSchema": schema,
                "annotations": {
                    "readOnlyHint": not t.writes,
                    "destructiveHint": False,
                    "idempotentHint": not t.writes,
                    "openWorldHint": False,
                },
            }
        )
    return out


def call(client: PlatformClient, name: str, args: dict[str, Any]) -> dict[str, Any]:
    tool = TOOLS.get(name)
    if tool is None:
        return {"isError": True, "content": [{"type": "text", "text": f"unknown tool {name!r}"}]}
    try:
        value = tool.fn(client, tool.model.model_validate(args))
    except ValidationError as e:
        msg = "; ".join(f"{'.'.join(map(str, x['loc']))}: {x['msg']}" for x in e.errors())
        return {"isError": True, "content": [{"type": "text", "text": f"invalid input: {msg}"}]}
    except ToolError as e:
        return {"isError": True, "content": [{"type": "text", "text": str(e)}]}
    structured = value if isinstance(value, dict) else {"result": value}
    return {
        "content": [{"type": "text", "text": json.dumps(value, sort_keys=True)}],
        "structuredContent": structured,
        "isError": False,
    }


def handle(client: PlatformClient, msg: dict[str, Any]) -> dict[str, Any] | None:
    mid, method, params = msg.get("id"), msg.get("method"), msg.get("params") or {}
    if mid is None:  # a notification (initialized, cancelled, ...): no reply
        return None

    def ok(result: Any) -> dict[str, Any]:
        return {"jsonrpc": "2.0", "id": mid, "result": result}

    if method == "initialize":
        return ok(
            {
                "protocolVersion": params.get("protocolVersion") or PROTOCOL,
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": "pap-agent-tools", "version": __version__},
            }
        )
    if method == "ping":
        return ok({})
    if method == "tools/list":
        return ok({"tools": tool_listing()})
    if method == "tools/call":
        return ok(call(client, str(params.get("name")), params.get("arguments") or {}))
    return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32601, "message": f"method not found: {method}"}}


def serve(client: PlatformClient, stdin: TextIO = sys.stdin, stdout: TextIO = sys.stdout) -> None:
    for line in stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
            reply = handle(client, msg) if isinstance(msg, dict) else None
        except json.JSONDecodeError:
            reply = {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "parse error"}}
        if reply is not None:
            stdout.write(json.dumps(reply, separators=(",", ":")) + "\n")
            stdout.flush()
