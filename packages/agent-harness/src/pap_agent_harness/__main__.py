"""``pap-harness ask --org <workspace> "<question>"``: one session against a running platform.

The model: PAP_LLM_PROVIDER (openai-compatible by default), PAP_LLM_API_KEY, PAP_LLM_BASE_URL, PAP_LLM_MODEL. The
platform: PAP_API_URL and PAP_API_TOKEN (or --as <subject> on a development install). Progress streams to stderr;
Ctrl-C cancels cleanly. Requests are off unless --allow-requests, and each one asks you to confirm before it is sent.
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import sys
from pathlib import Path
from typing import Any

from pap_agent_tools.client import PlatformClient

from .agent import Options, run_session
from .budget import Budget
from .config import LLMSettings, NotConfigured
from .ledger import Ledger
from .providers import build_model


def utf8_streams() -> None:
    """A model may stream any Unicode (a non-breaking hyphen, an arrow). Windows consoles default to a legacy code page
    that cannot print it and would crash the session at the answer; write UTF-8 and replace what cannot be shown."""
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


def _confirm(name: str, args: dict[str, Any]) -> bool:
    if not sys.stdin.isatty():
        print(f"[harness] {name} needs your confirmation, but there is no terminal: refused", file=sys.stderr)
        return False
    print(f"\n[harness] the agent wants to {name}: {json.dumps(args)}", file=sys.stderr)
    try:
        return input("[harness] send this request for an engineer to decide? [y/N] ").strip().lower() == "y"
    except EOFError:  # stdin is not readable after all
        print("[harness] no answer could be read: refused", file=sys.stderr)
        return False


def _progress(msg: str) -> None:
    if msg.startswith("text:"):
        sys.stdout.write(msg[5:])
        sys.stdout.flush()
    else:
        print(f"[harness] {msg}", file=sys.stderr, flush=True)


def main() -> None:
    utf8_streams()
    ap = argparse.ArgumentParser(prog="pap-harness")
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("ask", help="ask one question; the agent investigates with the platform's tools")
    a.add_argument("question")
    a.add_argument("--org", required=True)
    a.add_argument("--api", default=os.environ.get("PAP_API_URL", "http://127.0.0.1:8000"))
    a.add_argument("--as", dest="subject", help="development sign-in subject (dev auth mode only)")
    a.add_argument("--allow-requests", action="store_true", help="let the agent ask (with your confirmation) for runs")
    a.add_argument(
        "--draft-requests",
        action="store_true",
        help="let the agent DRAFT a follow-up; it is recorded in the trace and sent nowhere (a person files it)",
    )
    a.add_argument("--max-usd", type=float, help="spend cap for this session")
    a.add_argument("--max-steps", type=int, default=12, help="model calls per session")
    a.add_argument("--timeout-s", type=float, default=300.0)
    a.add_argument("--experiment", help="scope to an experiment slug for its cumulative budget")
    a.add_argument("--experiment-max-usd", type=float)
    a.add_argument("--experiment-max-tokens", type=int)
    a.add_argument("--session", help="resume (or name) a persistent session")
    a.add_argument("--no-fast-paths", action="store_true")
    a.add_argument(
        "--allow-no-model",
        action="store_true",
        help="when no model is configured, still answer the fixed questions (no model call, no cost)",
    )
    a.add_argument("--state", default="var/agent", help="traces, sessions and the cost ledger go here")
    ns = ap.parse_args()

    token = f"dev:{ns.subject}" if ns.subject else os.environ.get("PAP_API_TOKEN", "")
    if not token:
        print(
            "set PAP_API_TOKEN (a service credential) or use --as <subject> on a development install", file=sys.stderr
        )
        sys.exit(2)
    model = None
    try:
        s = LLMSettings.from_env(ns.max_usd)
        model = build_model(s, os.environ.get("PAP_LLM_PROVIDER", "openai"))
        model_label = s.model
        budget = Budget(s.max_tokens, s.max_usd, s.usd_per_m_input, s.usd_per_m_output)
        if s.usd_per_m_input is None or s.usd_per_m_output is None:
            print(f"[harness] no prices set, so only the token cap ({s.max_tokens}) applies", file=sys.stderr)
    except NotConfigured as e:
        if not ns.allow_no_model:
            print(f"not configured: {e}", file=sys.stderr)
            sys.exit(2)
        print("[harness] no model configured: answering fixed questions only", file=sys.stderr)
        model_label = "none"
        budget = Budget(1, 0.0)
    state = Path(ns.state)
    opts = Options(
        org=ns.org, allow_requests=ns.allow_requests, approve=_confirm if ns.allow_requests else None,
        max_calls=ns.max_steps, timeout_s=ns.timeout_s, experiment=ns.experiment,
        experiment_max_tokens=ns.experiment_max_tokens, experiment_max_usd=ns.experiment_max_usd,
        draft_requests=ns.draft_requests,
        ledger=Ledger(state / "ledger.json"), session_id=ns.session, sessions_dir=state / "sessions",
        trace_dir=state / "traces", fast_paths=not ns.no_fast_paths, progress=_progress,
    )  # fmt: skip
    signal.signal(signal.SIGINT, lambda *_: opts.cancel.set())
    sess = run_session(question=ns.question, model=model, model_label=model_label, client=PlatformClient(ns.api, token),
                       budget=budget, options=opts)  # fmt: skip
    print("\n" + (sess.trace.answer or f"(no answer: {sess.trace.stop})"))
    g = sess.trace.grounding
    if g and (g["unsupported"] or g["uncited"]):
        print(f"[harness] grounding: unsupported ids {g['unsupported']}, uncited {g['uncited']}", file=sys.stderr)
    print(f"[harness] {sess.trace.stop}; {json.dumps(budget.report())}; trace {sess.trace_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
