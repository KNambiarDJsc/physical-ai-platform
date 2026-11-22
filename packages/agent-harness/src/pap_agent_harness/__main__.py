"""``pap-harness ask --org <workspace> "<question>"``: one session against a running platform.

The model comes from PAP_LLM_API_KEY / PAP_LLM_BASE_URL / PAP_LLM_MODEL (an OpenAI-compatible endpoint); the platform
from PAP_API_URL and PAP_API_TOKEN (or --as <subject> against a development install). The trace is written under
var/agent-traces/. Requests (asking an engineer to approve a run) are off unless --allow-requests is given.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from pap_agent_tools.client import PlatformClient

from .agent import run_session
from .budget import Budget
from .config import LLMSettings, NotConfigured


def main() -> None:
    ap = argparse.ArgumentParser(prog="pap-harness")
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("ask", help="ask one question; the agent investigates with the platform's tools")
    a.add_argument("question")
    a.add_argument("--org", required=True)
    a.add_argument("--api", default=os.environ.get("PAP_API_URL", "http://127.0.0.1:8000"))
    a.add_argument("--as", dest="subject", help="development sign-in subject (dev auth mode only)")
    a.add_argument("--allow-requests", action="store_true", help="let the agent record run requests and proposals")
    a.add_argument("--max-usd", type=float, help="spend cap for this session (default PAP_LLM_MAX_USD or 0.50)")
    a.add_argument("--traces", default="var/agent-traces")
    ns = ap.parse_args()

    try:
        s = LLMSettings.from_env(ns.max_usd)
    except NotConfigured as e:
        print(f"not configured: {e}", file=sys.stderr)
        sys.exit(2)
    token = f"dev:{ns.subject}" if ns.subject else os.environ.get("PAP_API_TOKEN", "")
    if not token:
        print(
            "set PAP_API_TOKEN (a service credential) or use --as <subject> on a development install", file=sys.stderr
        )
        sys.exit(2)
    if s.usd_per_m_input is None or s.usd_per_m_output is None:
        print(
            f"note: no prices set (PAP_LLM_USD_PER_M_INPUT/OUTPUT), so only the token cap ({s.max_tokens}) applies",
            file=sys.stderr,
        )
    from strands.models.openai import OpenAIModel

    model = OpenAIModel(
        client_args={"api_key": s.api_key, "base_url": s.base_url}, model_id=s.model, params={"temperature": 0}
    )
    budget = Budget(s.max_tokens, s.max_usd, s.usd_per_m_input, s.usd_per_m_output)
    session = run_session(
        question=ns.question,
        org=ns.org,
        model=model,
        model_label=s.model,
        client=PlatformClient(ns.api, token),
        budget=budget,
        allow_requests=ns.allow_requests,
        trace_dir=Path(ns.traces),
    )
    print(session.trace.answer or f"(no answer: {session.trace.stop})")
    print(
        f"\n-- {session.trace.stop}; usage {json.dumps(budget.report())}; trace {session.trace_path}", file=sys.stderr
    )


if __name__ == "__main__":
    main()
