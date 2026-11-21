"""ROS-003: a REAL bag, recorded from the real mock bringup, summarised and checked against `ros2 bag info`."""

from __future__ import annotations

import json
import os
import re
import shutil
import signal
import subprocess
import time
from pathlib import Path
from typing import Any

import pytest
from conftest import SRC, eventually, run, sh

TOPICS = "/joint_states /diagnostics /tf_static /dynamic_joint_states"


def record(out: Path, seconds: float, freeze_s: float = 0.0) -> None:
    """ros2 bag record to MCAP for `seconds`; optionally freeze the controller process for `freeze_s` in the middle."""
    p = sh(f"ros2 bag record -s mcap -o '{out}' {TOPICS}", stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        time.sleep(3.0)  # discovery
        t_end = time.monotonic() + seconds
        if freeze_s:
            time.sleep(seconds / 3)
            pid = int(run("pgrep -f '[r]os2_control_node' | head -1").split()[0])
            os.kill(pid, signal.SIGSTOP)
            time.sleep(freeze_s)
            os.kill(pid, signal.SIGCONT)
        time.sleep(max(0.0, t_end - time.monotonic()))
    finally:
        os.killpg(os.getpgid(p.pid), signal.SIGINT)  # a clean stop lets the recorder finalise the MCAP and metadata
        p.wait(timeout=30)


@pytest.fixture(scope="module")
def bag(stack: dict[str, Any], tmp_path_factory: pytest.TempPathFactory) -> Path:
    out = tmp_path_factory.mktemp("bags") / "real"
    record(out, seconds=14, freeze_s=3.5)
    (out / "pap-run-identity.json").write_text(
        json.dumps({"run_id": "test-run-1", "software": {"commit": "abc"}}), encoding="utf-8"
    )
    return out


def summary(bag: Path, *args: str) -> dict[str, Any]:
    text = run(f"python3 -m pap_ros_observer bag-summary '{bag}' {' '.join(args)}", timeout=120)
    return json.loads(text)


def test_counts_and_duration_match_ros2_bag_info(bag: Path) -> None:
    info = run(f"ros2 bag info '{bag}'")
    assert "Storage id:   mcap" in info or "mcap" in info
    truth_total = int(re.search(r"Messages:\s+(\d+)", info).group(1))  # type: ignore[union-attr]
    s = summary(bag)
    assert s["schema"] == "pap.ros.bag-summary/1" and s["storage"] == "mcap"
    assert s["recording"]["messages"] == truth_total
    per_topic = dict(re.findall(r"Topic: (\S+) \| Type: \S+ \| Count: (\d+)", info))
    got = {t["name"]: t["messages"] for t in s["topics"]}
    assert {k: int(v) for k, v in per_topic.items()} == got
    assert any(f["name"].endswith(".mcap") and len(f["sha256"]) == 64 for f in s["files"])


def test_a_real_freeze_shows_up_as_a_listed_stale_interval_and_is_not_interpolated(bag: Path) -> None:
    s = summary(bag)
    js = next(t for t in s["topics"] if t["name"] == "/joint_states")
    assert js["state"] == "recorded" and js["rate_hz"] and js["rate_hz"] > 50, js
    gaps = js["stale_intervals"]
    assert len(gaps) == 1 and 3.0 < gaps[0]["length_s"] < 5.5, gaps  # the 3.5 s SIGSTOP of ros2_control_node
    assert js["max_gap_s"] == gaps[0]["length_s"]
    # the latched, one-shot topic is not called silent for being quiet
    tf = next(t for t in s["topics"] if t["name"] == "/tf_static")
    assert tf["messages"] >= 1 and tf["stale_intervals"] == []


def test_expected_topics_missing_from_the_recording_are_listed_not_invented(bag: Path) -> None:
    s = summary(bag)
    names = {t["name"] for t in s["topics"]}
    assert "/clock" not in names and s["clock"] == {"state": "absent", "messages": 0}


def test_the_run_identity_beside_the_bag_is_embedded(bag: Path) -> None:
    s = summary(bag)
    assert s["identity"] == {"run_id": "test-run-1", "software": {"commit": "abc"}}


def test_the_summary_is_deterministic_byte_for_byte(bag: Path, tmp_path: Path) -> None:
    a, b = tmp_path / "a.json", tmp_path / "b.json"
    run(f"python3 -m pap_ros_observer bag-summary '{bag}' --out '{a}'", timeout=120)
    copy = tmp_path / "copy"
    shutil.copytree(bag, copy)  # a different path, the same recording
    run(f"python3 -m pap_ros_observer bag-summary '{copy}' --out '{b}'", timeout=120)
    ta = a.read_text(encoding="utf-8")
    tb = b.read_text(encoding="utf-8").replace('"bag": "copy"', '"bag": "real"')
    assert ta == tb and len(ta) > 500


def test_the_summary_reader_cannot_write_to_the_bag(bag: Path) -> None:
    before = sorted((p.name, p.stat().st_mtime_ns) for p in bag.iterdir())
    summary(bag)
    assert sorted((p.name, p.stat().st_mtime_ns) for p in bag.iterdir()) == before
    assert SRC.is_dir() and eventually(lambda: True, 1, "noop")
