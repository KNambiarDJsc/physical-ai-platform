"""Interoperability check: the official MCP Python SDK's client against pap-agent-tools' stdio server.

Run in an isolated environment so the SDK never enters the platform's lock (D-031):

    uv run --isolated --no-project --with mcp==2.3.0 python scripts/mcp_sdk_interop.py

It starts the server as the project does (uv run python -m pap_agent_tools), negotiates, lists the tools, validates
each input schema with the SDK's own types, and calls one tool with bad input and one unknown tool. No platform API is
needed: those answers come from the server before any request is made. Prints one JSON line and exits non-zero on any
mismatch.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import anyio
from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

ROOT = Path(__file__).resolve().parents[1]
EXPECTED = 16


async def main() -> int:
    env = {**os.environ, "PAP_API_URL": "http://127.0.0.1:9", "PAP_API_TOKEN": "dev:interop"}
    params = StdioServerParameters(
        command="uv", args=["run", "--project", str(ROOT), "python", "-m", "pap_agent_tools"], env=env, cwd=str(ROOT)
    )
    out: dict[str, object] = {}
    problems: list[str] = []
    async with stdio_client(params) as streams, ClientSession(*streams) as session:
        init = await session.initialize()
        out["protocol"] = init.protocol_version
        out["server"] = f"{init.server_info.name} {init.server_info.version}"
        if init.protocol_version != "2025-06-18":
            problems.append(f"negotiated {init.protocol_version}, which the server does not implement")
        await session.send_ping()
        listing = await session.list_tools()
        out["tools"] = len(listing.tools)
        if len(listing.tools) != EXPECTED:
            problems.append(f"expected {EXPECTED} tools, got {len(listing.tools)}")
        writes = [t.name for t in listing.tools if not (t.annotations and t.annotations.read_only_hint)]
        out["writes"] = writes
        if writes != ["propose_experiment"]:
            problems.append(f"write tools {writes}")
        bad = await session.call_tool("get_workflow_run", {})
        out["bad_input_is_error"] = bad.is_error
        if not bad.is_error:
            problems.append("missing arguments were accepted")
        unknown = await session.call_tool("approve_proposal", {})
        out["unknown_tool_is_error"] = unknown.is_error
        if not unknown.is_error:
            problems.append("an unlisted tool answered")
    out["problems"] = problems
    print(json.dumps(out, sort_keys=True))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(anyio.run(main))
