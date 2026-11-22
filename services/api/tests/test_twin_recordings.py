"""TWN-002: MCAP recordings decoded into deterministic playback tracks, with evidence events and engine verdicts.

The inputs are the two real Gazebo recordings in examples/openamr-cmd-timeout/recorded (the committed fix, and the
pre-fix wiring). Their independent ground truth is Gazebo's own world-pose measurement in each run's probe.json, which
the track builder never reads.
"""

from __future__ import annotations

import io
import json
from pathlib import Path
from typing import Any

import pytest
from app.twin.track import RecordingError, build_track, canonical, track_sha256
from fastapi.testclient import TestClient
from helpers import add_member, as_user, make_org, ok
from mcap_ros2.writer import Writer as Ros2Writer
from test_twin_models import post_model, real

EXP = Path(__file__).resolve().parents[3] / "examples" / "openamr-cmd-timeout"
FIX, MAIN = "fix_20261121T185851Z", "main_20261122T053012Z"
P = "/api/v1/orgs/lab/projects/arm/twin"
H = as_user("ada")


def run_files(run: str) -> tuple[bytes, dict[str, Any], dict[str, Any], dict[str, Any]]:
    d = EXP / "recorded" / run
    mcap = next((d / "bag").glob("*.mcap")).read_bytes()
    summary = json.loads((d / "bag-summary.json").read_text(encoding="utf-8"))
    identity = json.loads((d / "pap-run-identity.json").read_text(encoding="utf-8"))
    probe = json.loads((d / "probe.json").read_text(encoding="utf-8"))["result"]
    return mcap, summary, identity, probe


def upload(client: TestClient, run: str, label: str, headers: dict[str, str] = H, **form: Any) -> Any:
    mcap, summary, identity, _ = run_files(run)
    data = {"label": label, "summary": json.dumps(summary), "identity": json.dumps(identity), **form}
    return client.post(
        P + "/recordings", data=data, files={"file": (f"{run}.mcap", mcap, "application/octet-stream")}, headers=headers
    )


def setup(client: TestClient) -> None:
    make_org(client, "ada", "lab", "arm")
    add_member(client, "ada", "lab", "vera", "viewer")


def kinds(detail: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {e["kind"]: e for e in detail["events"]}


def test_the_fix_recording_decodes_to_a_deterministic_track_that_agrees_with_its_summary(client: TestClient) -> None:
    setup(client)
    manifest, blobs = real()
    assert post_model(client, manifest, blobs).status_code == 201
    r = upload(client, FIX, "Command loss, fix 505d17a", model_slug="openamrobot-platform", model_version=1)
    assert r.status_code == 201, r.text
    rid = r.json()["id"]
    d = client.get(f"{P}/recordings/{rid}", headers=as_user("vera")).json()
    _, summary, identity, probe = run_files(FIX)
    assert d["model"] == "openamrobot-platform@1" and d["model_version"]["license_spdx"] == "CERN-OHL-P-2.0"
    assert d["identity"] == identity and d["summary"] == summary  # stored as given, shown as reported
    assert d["clock"] == "sim" and d["duration_s"] == summary["clock"]["sim_span_s"]
    # per-channel message counts equal the bag summary's (an independent reader of the same file)
    assert d["counts"] == {t["name"]: t["messages"] for t in summary["topics"]}
    assert d["frames"] == {"parent": "odom", "child": "base_footprint", "source": "/tf"}
    ev = kinds(d)
    assert {"command_first", "command_last", "applied_command_zero", "motion_stopped"} <= set(ev)
    assert not [e for e in d["events"] if e["severity"] == "problem"]  # the fix stops the base promptly
    stop = ev["motion_stopped"]["detail"]
    assert stop["seconds_after_last_command"] <= d["limits"]["grace_s"]
    # Gazebo's own world-pose measurement of travel after the kill, which the track never saw
    assert stop["travel_after_last_command_m"] == pytest.approx(probe["travel_after_kill_m"], abs=0.03)
    assert all(e["rule"] and e["topics"] for e in d["events"])  # every event states its rule and source
    # deterministic: the same bytes twice, and equal to the digest in the ETag
    t1 = client.get(f"{P}/recordings/{rid}/track", headers=H)
    t2 = client.get(f"{P}/recordings/{rid}/track", headers=as_user("vera"))
    assert t1.content == t2.content and t1.headers["etag"] == f'"{d["track_sha256"]}"'
    mcap = run_files(FIX)[0]
    assert canonical(build_track(mcap, summary)) == canonical(build_track(mcap, summary))
    assert track_sha256(build_track(mcap, summary)) == d["track_sha256"]
    track = t1.json()
    assert track["base"]["t"] == sorted(track["base"]["t"]) and track["base"]["x"][0] == 0.0
    assert track["base"]["x"][-1] == pytest.approx(
        probe["driven_before_kill_m"] + probe["travel_after_kill_m"], abs=0.1
    )
    # the wheel joints report a constant 0 rad in these recordings: said, not animated
    assert {e["detail"]["position_rad"] for e in d["events"] if e["kind"] == "joint_constant"} == {0.0}
    assert (
        track["joints"]["stats"]["left_wheel_joint"]["min"]
        == track["joints"]["stats"]["left_wheel_joint"]["max"]
        == 0.0
    )


def test_the_pre_fix_recording_shows_the_base_driving_on_and_that_its_clock_went_backwards(client: TestClient) -> None:
    setup(client)
    rid = upload(client, MAIN, "Command loss, pre-fix wiring").json()["id"]
    d = client.get(f"{P}/recordings/{rid}", headers=H).json()
    _, summary, _, probe = run_files(MAIN)
    ev = kinds(d)
    assert ev["motion_continues"]["severity"] == "problem" and "motion_stopped" not in ev
    detail = ev["motion_continues"]["detail"]
    assert (
        detail["speed_at_end_m_s"] == pytest.approx(0.2, abs=0.02) and detail["seconds_after_last_command_at_end"] > 4
    )
    assert detail["travel_after_last_command_m"] == pytest.approx(probe["travel_after_kill_m"], abs=0.05)  # ~1.0 m
    assert "applied_command_zero" not in ev  # this arm has no /sim/base_cmd_vel
    # the anomaly the bag summary found is reported, and playback time still never goes backwards
    assert summary["clock"]["monotonic"] is False
    assert (
        ev["clock_not_monotonic"]["severity"] == "warning" and ev["clock_not_monotonic"]["detail"]["backward_jumps"] > 0
    )
    track = client.get(f"{P}/recordings/{rid}/track", headers=H).json()
    for series in (
        track["base"]["t"],
        track["joints"]["t"],
        track["odom_speed"]["t"],
        track["commands"]["cmd_vel"]["t"],
    ):
        assert series == sorted(series)
    assert track["clock_stats"]["backward_jumps"] == ev["clock_not_monotonic"]["detail"]["backward_jumps"]
    # events are in time order and each has a stable id
    ts = [e["t"] for e in d["events"]]
    assert ts == sorted(ts) and [e["id"] for e in d["events"]] == [f"ev-{i}" for i in range(1, len(ts) + 1)]


def test_stale_intervals_from_the_bag_summary_become_warning_events_on_the_recording_clock() -> None:
    mcap, summary, _, _ = run_files(FIX)
    s = json.loads(json.dumps(summary))
    clock_topic = next(t for t in s["topics"] if t["name"] == "/clock")
    first = clock_topic["first_log_ns"]
    for t in s["topics"]:
        if t["name"] == "/joint_states":
            t["stale_intervals"] = [
                {"start_ns": first + 3_000_000_000, "end_ns": first + 5_000_000_000, "length_s": 2.0}
            ]
    ev = [e for e in build_track(mcap, s)["events"] if e["kind"] == "stale_interval"]
    assert len(ev) == 1 and ev[0]["topics"] == ["/joint_states"] and ev[0]["severity"] == "warning"
    assert ev[0]["detail"]["length_s"] == 2.0 and 0 < ev[0]["detail"]["from_s"] < ev[0]["detail"]["to_s"] < 12


CLOCK = "builtin_interfaces/Time clock"
SEP = "=" * 80
TIME = SEP + "\nMSG: builtin_interfaces/Time\nint32 sec\nuint32 nanosec"
TWIST = "Vector3 linear\nVector3 angular\n" + SEP + "\nMSG: geometry_msgs/Vector3\nfloat64 x\nfloat64 y\nfloat64 z"


def synthetic(clock: list[float] | None, cmds: list[tuple[int, float]]) -> bytes:
    """A tiny recording written with the same library that reads it: /clock (optional) and /cmd_vel at log times."""
    buf = io.BytesIO()
    w = Ros2Writer(buf)
    sc = w.register_msgdef("rosgraph_msgs/msg/Clock", CLOCK + "\n" + TIME)
    st = w.register_msgdef("geometry_msgs/msg/Twist", TWIST)
    zero = {"x": 0.0, "y": 0.0, "z": 0.0}
    for i, v in enumerate(clock or []):
        msg = {"clock": {"sec": int(v), "nanosec": int((v % 1) * 1e9)}}
        w.write_message("/clock", sc, msg, log_time=i * 10_000_000, publish_time=i * 10_000_000, sequence=i)
    for t, x in cmds:
        w.write_message("/cmd_vel", st, {"linear": {**zero, "x": x}, "angular": zero}, log_time=t, publish_time=t)
    w.finish()
    return buf.getvalue()


def test_a_recording_without_a_clock_uses_log_time_and_one_without_the_topics_is_refused() -> None:
    t = build_track(synthetic(None, [(1_000_000_000, 0.2), (1_500_000_000, 0.2), (2_000_000_000, 0.0)]))
    assert t["clock"] == "log" and t["duration_s"] == 1.0 and t["base"]["t"] == []
    assert [e["kind"] for e in t["events"]] == ["command_first", "command_last"] and t["events"][0]["t"] == 0.0
    with pytest.raises(RecordingError, match="none of the topics"):
        build_track(synthetic([1.0, 1.1], []))
    with pytest.raises(RecordingError):
        build_track(b"\x89MCAP0\r\n" + b"garbage" * 20)


def test_a_clock_that_moves_backwards_is_followed_by_its_running_maximum() -> None:
    t = build_track(synthetic([1.0, 1.1, 1.2, 1.05, 1.3, 1.1, 1.4], [(5_000_000, 0.2), (65_000_000, 0.2)]))
    assert t["clock_stats"] == {"backward_jumps": 2, "largest_backward_s": 0.2, "first_backward_at_s": 0.2}
    assert t["duration_s"] == pytest.approx(0.4)
    first = next(e for e in t["events"] if e["kind"] == "clock_not_monotonic")
    assert first["severity"] == "warning" and "running maximum" in first["rule"]


def test_uploads_are_checked_before_anything_is_stored(client: TestClient) -> None:
    setup(client)
    mcap, summary, identity, _ = run_files(FIX)
    other = run_files(MAIN)[1]  # a real summary, but of a different file
    cases: list[tuple[dict[str, Any], tuple[str, bytes], int, str]] = [
        ({"label": "x", "summary": json.dumps(other)}, ("a.mcap", mcap), 422, "twin.summary"),
        ({"label": "x"}, ("a.txt", mcap), 415, "twin.type"),
        ({"label": "x"}, ("a.mcap", b"plain text, not mcap"), 415, "twin.type"),
        ({"label": "x"}, ("a.mcap", b"\x89MCAP0\r\n" + b"junk" * 50), 422, "twin.recording"),
        ({"label": "x", "summary": "{not json"}, ("a.mcap", mcap), 422, "twin.json"),
        ({"label": "x", "identity": json.dumps({"schema": "something/else"})}, ("a.mcap", mcap), 422, "twin.json"),
        ({"label": "x", "model_slug": "nope", "model_version": 1}, ("a.mcap", mcap), 404, "not_found"),
        ({"label": "x", "model_slug": "nope"}, ("a.mcap", mcap), 422, "twin.model"),
        ({"label": "x", "episode_id": "00000000-0000-0000-0000-000000000001"}, ("a.mcap", mcap), 404, "not_found"),
    ]
    for form, (name, body), status, code in cases:
        r = client.post(
            P + "/recordings", data=form, files={"file": (name, body, "application/octet-stream")}, headers=H
        )
        assert r.status_code == status and r.json()["detail"]["code"] == code, (form, r.status_code, r.text[:200])
    assert client.get(P + "/recordings", headers=H).json() == []
    assert summary and identity


def test_roles_duplicates_and_workspace_isolation(client: TestClient) -> None:
    setup(client)
    assert upload(client, FIX, "x", as_user("vera")).status_code == 403
    first = upload(client, FIX, "first")
    assert first.status_code == 201
    again = upload(client, FIX, "same bytes, another label")
    assert again.status_code == 200 and again.json()["id"] == first.json()["id"]
    rid = first.json()["id"]
    assert [r["id"] for r in client.get(P + "/recordings", headers=as_user("vera")).json()] == [rid]
    make_org(client, "mallory", "evil", "other")
    for path in (f"/recordings/{rid}", f"/recordings/{rid}/track"):
        assert client.get(P + path, headers=as_user("mallory")).status_code == 404
        assert client.get("/api/v1/orgs/evil/projects/other/twin" + path, headers=as_user("mallory")).status_code == 404
    assert client.get("/api/v1/orgs/evil/projects/other/twin/recordings", headers=as_user("mallory")).json() == []


def evaluate(client: TestClient) -> tuple[dict[str, Any], dict[str, dict[str, Any]], dict[str, Any]]:
    """A real evaluation of the OpenAMRobot command-timeout runs through the API, worker and pinned engine."""
    from test_jobs import work_once
    from test_ros_regression import COMPONENTS, LABEL

    setup(client)
    p = "/api/v1/orgs/lab/projects/arm"
    runs = json.loads((EXP / "runs.json").read_text(encoding="utf-8"))
    rel: dict[str, str] = {}
    art: dict[str, str] = {}
    for arm in ("main", "fix"):
        rel[arm] = ok(
            client.post(
                f"{p}/releases",
                json={"label": LABEL[arm], "kind": "software", "components": COMPONENTS[arm]},
                headers=H,
            ),
            201,
        )["id"]
        art[arm] = ok(
            client.post(
                f"{p}/artifacts", files={"file": (f"{arm}.csv", (EXP / "data" / f"{arm}.csv").read_bytes())}, headers=H
            ),
            201,
        )["id"]
    mapping = ok(
        client.post(f"{p}/mappings", json=json.loads((EXP / "mapping.json").read_text(encoding="utf-8")), headers=H),
        201,
    )["id"]
    body = {
        "baseline_release_id": rel["main"], "candidate_release_id": rel["fix"], "mapping_id": mapping,
        "baseline_artifact_ids": [art["main"]], "candidate_artifact_ids": [art["fix"]],
        "config": {"task_type": "command_loss_stop", "paired": False, "min_known": 30, "stratify_by_site": False},
    }  # fmt: skip
    job = ok(client.post(f"{p}/evaluations", json=body, headers=H), 201)
    assert work_once() == "succeeded"
    eps = {
        e["episode_key"]: e
        for e in ok(client.get(f"{p}/evaluations/{job['id']}/episodes?limit=50", headers=H))["items"]
    }
    assert len(eps) == len(runs["runs"])
    return job, eps, runs


@pytest.mark.engine
def test_a_recording_linked_to_an_episode_shows_the_engines_verdict_not_a_recomputed_one(
    client: TestClient, omhs: Any
) -> None:
    from test_ros_regression import LABEL

    job, eps, runs = evaluate(client)
    assert len(eps) == len(runs["runs"])
    out = {}
    for run in (MAIN, FIX):
        r = upload(client, run, run, episode_id=eps[run]["id"])
        assert r.status_code == 201, r.text
        out[run] = client.get(f"{P}/recordings/{r.json()['id']}", headers=H).json()
    m, f = out[MAIN]["episode"], out[FIX]["episode"]
    assert (m["verdict"], m["outcome_class"], m["release_label"]) == (
        eps[MAIN]["verdict"],
        "verified_failure",
        LABEL["main"],
    )
    assert (f["verdict"], f["outcome_class"], f["release_label"]) == (
        eps[FIX]["verdict"],
        "verified_success",
        LABEL["fix"],
    )
    assert m["evaluation_id"] == job["id"] and m["episode_key"] == MAIN
    # independent agreement: the engine's verdict and this reader's rule point the same way (they are different things)
    assert any(e["kind"] == "motion_continues" for e in out[MAIN]["events"]) and not any(
        e["severity"] == "problem" for e in out[FIX]["events"]
    )
    # an episode of another project cannot be linked
    make_org(client, "mallory", "evil", "other")
    mcap, summary, identity, _ = run_files(MAIN)
    r = client.post(
        "/api/v1/orgs/evil/projects/other/twin/recordings",
        data={"label": "x", "episode_id": eps[MAIN]["id"]},
        files={"file": ("a.mcap", mcap, "application/octet-stream")},
        headers=as_user("mallory"),
    )
    assert r.status_code == 404
