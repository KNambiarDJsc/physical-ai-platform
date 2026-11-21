"""OBS-002 check, run by `scripts/smoke.sh --compose --observability` after a real evaluation has run:

- Prometheus reports both scrape targets (the API and the worker) up, and has counted engine invocations (the worker's);
- the OpenTelemetry Collector's log contains spans named `engine <command>`: traces from a real evaluation arrived.

    python scripts/check_observability.py --prometheus http://127.0.0.1:9090 \
        --collector-logs "docker compose logs otel-collector"
"""

from __future__ import annotations

import argparse
import json
import re
import shlex
import subprocess
import sys
import time
import urllib.parse
import urllib.request


def prom(base: str, query: str) -> list[dict]:
    url = f"{base}/api/v1/query?" + urllib.parse.urlencode({"query": query})
    with urllib.request.urlopen(url, timeout=10) as r:  # noqa: S310  (the local Prometheus we started)
        body = json.load(r)
    return body["data"]["result"] if body.get("status") == "success" else []


def wait(what: str, cond, seconds: float = 90.0) -> None:  # type: ignore[no-untyped-def]
    end = time.monotonic() + seconds
    last = None
    while time.monotonic() < end:
        try:
            last = cond()
            if last:
                print(f"ok   {what}")
                return
        except (OSError, ValueError, KeyError):
            pass
        time.sleep(3)
    sys.exit(f"FAIL {what} (after {seconds:g} s; last: {last!r})")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--prometheus", required=True)
    ap.add_argument(
        "--collector-logs", required=True, help="command that prints the collector's log (run on every poll)"
    )
    ns = ap.parse_args()
    for job in ("pap-api", "pap-worker"):
        wait(
            f"Prometheus scrapes {job} (up == 1)",
            lambda j=job: any(r["value"][1] == "1" for r in prom(ns.prometheus, f'up{{job="{j}"}}')),
        )
    wait(
        "the worker's engine invocations are counted (pap_engine_invocations_total > 0)",
        lambda: any(float(r["value"][1]) > 0 for r in prom(ns.prometheus, "sum(pap_engine_invocations_total)")),
    )
    wait(
        "the API's request durations are counted (pap_http_request_duration_seconds_count > 0)",
        lambda: any(
            float(r["value"][1]) > 0 for r in prom(ns.prometheus, "sum(pap_http_request_duration_seconds_count)")
        ),
    )

    def collector_log() -> str:
        r = subprocess.run(shlex.split(ns.collector_logs), capture_output=True, text=True, check=False, timeout=30)
        return r.stdout + r.stderr

    wait(
        "the collector received spans named 'engine <command>' from a real evaluation",
        lambda: re.search(r"Name\s*:\s*engine \w+", collector_log()),
        seconds=60,
    )


if __name__ == "__main__":
    main()
