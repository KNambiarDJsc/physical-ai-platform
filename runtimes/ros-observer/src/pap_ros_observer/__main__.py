"""Command line: serve the observer (needs ROS 2), or inspect recorded evidence (bag.py, needs rosbag2_py).

python -m pap_ros_observer serve [--host 127.0.0.1] [--port 8200] [--profile profiles/openamr-upperbody.json]
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .model import ExpectedTopic

PROFILES = Path(__file__).resolve().parents[2] / "profiles"


def load_profile(path: str | None) -> list[ExpectedTopic]:
    if not path:
        return []
    p = Path(path)
    if not p.is_file() and (PROFILES / path).is_file():
        p = PROFILES / path
    return ExpectedTopic.parse(json.loads(p.read_text(encoding="utf-8"))["expected_topics"])


def main() -> None:
    ap = argparse.ArgumentParser(prog="pap_ros_observer", description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("serve", help="observe the ROS 2 graph and serve Thing Descriptions over HTTP (read-only)")
    s.add_argument("--host", default="127.0.0.1")
    s.add_argument("--port", type=int, default=8200)
    s.add_argument("--profile", help="JSON file listing the topics this robot is expected to publish")
    s.add_argument(
        "--include-hidden", action="store_true", help="also show nodes and topics with a segment starting with _"
    )
    r = sub.add_parser("replay", help="serve a recorded snapshot (labelled recorded_not_live); needs no ROS")
    r.add_argument("snapshot")
    r.add_argument("--host", default="127.0.0.1")
    r.add_argument("--port", type=int, default=8200)
    b = sub.add_parser("bag-summary", help="summarise a rosbag2 recording (MCAP or SQLite3) as deterministic JSON")
    b.add_argument("bag", help="bag directory")
    b.add_argument("--identity", help="run identity JSON to embed (default: <bag>/pap-run-identity.json when present)")
    b.add_argument("--out", help="write here instead of stdout")
    ns = ap.parse_args()
    if ns.cmd == "replay":
        from .replay import replay_server

        replay_server(ns.snapshot, ns.host, ns.port).serve_forever()
    elif ns.cmd == "serve":
        from .node import run

        run(load_profile(ns.profile), ns.host, ns.port, ns.include_hidden)
    else:
        from .bag import summarize_bag

        text = json.dumps(summarize_bag(Path(ns.bag), ns.identity), indent=1, sort_keys=True) + "\n"
        if ns.out:
            Path(ns.out).write_text(text, encoding="utf-8", newline="\n")
        else:
            print(text, end="")


if __name__ == "__main__":
    main()
