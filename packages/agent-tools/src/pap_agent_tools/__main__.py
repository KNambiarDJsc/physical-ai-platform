"""python -m pap_agent_tools : serve the tools over stdio as the holder of PAP_API_TOKEN.

Use a VIEWER credential for an assistant: it can then read everything in the workspace and record proposals, and the
platform itself refuses everything else (approving a proposal needs the engineer role).

    PAP_API_URL=http://127.0.0.1:8000 PAP_API_TOKEN=<credential> python -m pap_agent_tools
"""

from __future__ import annotations

import os
import sys

from .client import PlatformClient, ToolError
from .mcp_server import serve


def main() -> None:
    try:
        client = PlatformClient(
            os.environ.get("PAP_API_URL", "http://127.0.0.1:8000"), os.environ.get("PAP_API_TOKEN", "")
        )
    except ToolError as e:
        sys.exit(f"pap-agent-tools: {e}")
    serve(client)


if __name__ == "__main__":
    main()
