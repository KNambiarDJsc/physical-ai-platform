"""The observer's judgements, with synthetic monotonic times (no ROS). These are tests of the rules; the observations
themselves are tested against a real graph in tests_ros/."""

from __future__ import annotations

from pap_ros_observer.model import (
    GRACE_S,
    ClockTracker,
    ExpectedTopic,
    JointTracker,
    TfTracker,
    TopicTracker,
    check_expected,
    finite,
    is_hidden,
    summarize,
)


def fed(period: float, n: int, start: float = 100.0, **kw: object) -> TopicTracker:
    t = TopicTracker("/x", ["std_msgs/msg/String"], created=start, publishers=1, sampled=True, **kw)  # type: ignore[arg-type]
    for i in range(n):
        t.on_message(start + i * period)
    return t


def test_a_fast_topic_goes_stale_after_two_seconds_of_silence() -> None:
    t = fed(0.1, 50)  # 10 Hz, last message at 104.9
    assert t.rate_hz() == 10.0
    assert t.state(104.9 + 1.9) == "fresh"
    assert t.state(104.9 + 2.1) == "stale"


def test_a_slow_topic_is_not_called_stale_before_five_of_its_own_periods() -> None:
    t = fed(2.0, 10)  # 0.5 Hz, last at 118
    assert t.stale_after_s() == 10.0
    assert t.state(118 + 9) == "fresh"
    assert t.state(118 + 11) == "stale"


def test_silence_right_after_subscribing_is_pending_then_never() -> None:
    t = TopicTracker("/y", ["a/msg/B"], created=50.0, publishers=1, sampled=True)
    assert t.state(50.0 + GRACE_S - 0.1) == "pending"
    assert t.state(50.0 + GRACE_S + 0.1) == "never"  # a publisher exists, nothing ever arrived


def test_a_topic_nobody_publishes_is_not_called_fresh_or_never() -> None:
    t = TopicTracker("/z", ["a/msg/B"], created=0.0, publishers=0, subscribers=2)
    assert t.state(99.0) == "no_publishers"


def test_heavy_topics_are_reported_as_not_sampled() -> None:
    t = TopicTracker("/cam", ["sensor_msgs/msg/Image"], created=0.0, publishers=1, not_sampled_reason="heavy")
    assert t.state(99.0) == "not_sampled"
    assert t.as_dict(99.0)["age_s"] is None  # no age is invented for a topic that is not watched


def test_a_latched_topic_is_never_stale_after_its_one_message() -> None:
    t = TopicTracker("/tf_static", ["tf2_msgs/msg/TFMessage"], created=0.0, publishers=1, sampled=True, latched=True)
    t.on_message(1.0)
    assert t.state(10_000.0) == "latched"


def test_a_transient_local_topic_that_keeps_publishing_is_judged_by_freshness() -> None:
    """ros2_control publishes /joint_states at 100 Hz with transient-local QoS; that must not read as 'latched'."""
    t = fed(0.01, 200, latched=True)  # 100 Hz, last message at 101.99
    assert t.state(102.0) == "fresh"
    assert t.state(101.99 + 2.5) == "stale"


def test_expected_topics_are_missing_stale_or_present() -> None:
    now = 200.0
    trackers = {"/a": fed(0.1, 10, start=now - 1.0), "/b": fed(0.1, 10, start=now - 30.0)}
    exp = [
        ExpectedTopic("/a"),
        ExpectedTopic("/b"),
        ExpectedTopic("/c", required=False),
        ExpectedTopic("/a", max_age_s=0.01),
    ]
    got = {(e["name"], e["max_age_s"]): e["state"] for e in check_expected(exp, trackers, now)}
    assert got[("/a", None)] == "fresh"
    assert got[("/b", None)] == "stale"
    assert got[("/c", None)] == "missing"
    assert got[("/a", 0.01)] == "stale"  # the profile's own age limit applies


def test_summary_counts_required_problems_only() -> None:
    topics = [{"state": "fresh"}, {"state": "stale"}, {"state": "fresh"}]
    expected = [
        {"name": "/need", "required": True, "state": "missing"},
        {"name": "/opt", "required": False, "state": "missing"},
        {"name": "/ok", "required": True, "state": "fresh"},
    ]
    s = summarize(topics, expected, {"state": "absent"})
    assert s["topics_by_state"] == {"fresh": 2, "stale": 1}
    assert s["required_expected_problems"] == ["/need"]
    assert s["clock_state"] == "absent"


def test_clock_states_monotonicity_and_real_time_factor() -> None:
    c = ClockTracker()
    assert c.as_dict(10.0)["state"] == "absent"
    c.publishers = 1
    assert c.as_dict(10.0)["state"] == "silent"
    for i in range(11):  # simulation runs at a tenth of real time
        c.on_clock(100.0 + i, 5.0 + i * 0.1)
    d = c.as_dict(110.5)
    assert d["state"] == "running" and d["monotonic"] and d["real_time_factor"] == 0.1
    c.on_clock(111.0, 5.5)  # the clock jumps back half a second
    d = c.as_dict(111.2)
    assert not d["monotonic"] and d["backward_jumps"] == 1 and d["largest_backward_s"] == 0.5
    assert c.as_dict(111.0 + 5.0)["state"] == "stale"


def test_a_frozen_joint_keeps_its_fresh_stamp_but_reports_how_long_it_has_not_moved() -> None:
    j = JointTracker()
    t = TopicTracker("/joint_states", ["sensor_msgs/msg/JointState"], created=0.0, publishers=1, sampled=True)
    for i in range(30):  # 10 Hz; joint_a moves for the first second, then freezes; the stamp keeps advancing
        now = 100.0 + i * 0.1
        pos_a = i * 0.01 if i < 10 else 0.09
        t.on_message(now, now)
        j.on_message(now, now, ["joint_a", "joint_b"], [pos_a, 1.0], [], [])
    d = j.as_dict(102.9, t)
    by = {x["name"]: x for x in d["joints"]}
    assert d["state"] == "fresh" and d["age_s"] < 0.2  # receipt is fresh
    assert by["joint_a"]["unchanged_for_s"] > 1.8  # ...but joint_a has not changed for about 2 s
    assert by["joint_b"]["unchanged_for_s"] > 2.8


def test_tf_static_frames_report_no_age_and_roots_are_listed() -> None:
    tf = TfTracker()
    tf.on_transform(1.0, "base_link", "arm_link", True, (0, 0, 0.1), (0, 0, 0, 1))
    tf.on_transform(1.0, "odom", "base_link", False, (1, 0, 0), (0, 0, 0, 1))
    d = tf.as_dict(5.0)
    by = {f["child"]: f for f in d["frames"]}
    assert by["arm_link"]["age_s"] is None and by["base_link"]["age_s"] == 4.0
    assert d["roots"] == ["odom"] and d["count"] == 2


def test_hidden_names_follow_the_ros_convention() -> None:
    assert is_hidden("/_ros2cli_daemon_0_abc") and is_hidden("/lift_controller/follow_joint_trajectory/_action/status")
    assert not is_hidden("/joint_states") and not is_hidden("/a_b/c_d")


def test_non_finite_sensor_values_become_no_value_not_invalid_json() -> None:
    assert finite(float("nan")) is None and finite(float("inf")) is None and finite(None) is None and finite(1.5) == 1.5
    j = JointTracker()
    j.on_message(1.0, None, ["a", "b"], [0.5, float("nan")], [float("inf"), 0.0], [float("nan"), 2.0])
    d = {x["name"]: x for x in j.as_dict(1.5, None)["joints"]}
    assert (
        d["a"]["velocity"] is None
        and d["a"]["effort"] is None
        and d["b"]["position"] is None
        and d["b"]["effort"] == 2.0
    )
