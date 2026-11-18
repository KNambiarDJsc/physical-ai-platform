"""The process runner, exercised with the Python interpreter standing in for a binary. No engine semantics here."""

from __future__ import annotations

import json
import sys
import threading
import time

import pytest
from openmhs_bridge import Engine, EngineConfig, EngineError, canonical_json, digest, sha256_file


def python_engine(**kw: object) -> Engine:
    cfg = EngineConfig(
        binary=sys.executable, expected_sha256=sha256_file(sys.executable), commit="test", interfaces={}, **kw
    )  # type: ignore[arg-type]
    return Engine(cfg)


def test_digest_mismatch_is_refused_before_running() -> None:
    e = Engine(EngineConfig(binary=sys.executable, expected_sha256="sha256:" + "0" * 64, commit="t", interfaces={}))
    with pytest.raises(EngineError) as info:
        e._run(["-c", "print(1)"])
    assert info.value.code == "engine.digest_mismatch"
    assert info.value.detail["actual"].startswith("sha256:")


def test_missing_binary() -> None:
    e = Engine(EngineConfig(binary="does/not/exist.exe", expected_sha256="sha256:x", commit="t", interfaces={}))
    with pytest.raises(EngineError) as info:
        e.check_binary()
    assert info.value.code == "engine.binary_missing"


def test_arguments_reach_the_process_verbatim_without_a_shell() -> None:
    hostile = 'x"; echo pwned & del * | $(rm -rf /) `id` %PATH%'
    run = python_engine()._run(["-c", "import json,sys; print(json.dumps(sys.argv[1:]))", hostile, "--json"])
    assert run.returncode == 0
    assert json.loads(run.stdout) == [hostile, "--json"]


def test_nul_in_argument_is_refused() -> None:
    with pytest.raises(EngineError) as info:
        python_engine()._run(["-c", "pass", "a\x00b"])
    assert info.value.code == "engine.input_invalid"


def test_timeout_kills_the_process() -> None:
    t0 = time.monotonic()
    with pytest.raises(EngineError) as info:
        python_engine()._run(["-c", "import time; time.sleep(30)"], timeout_s=0.5)
    assert info.value.code == "engine.timeout"
    assert info.value.transient
    assert time.monotonic() - t0 < 10


def test_cancel_kills_the_process() -> None:
    cancel = threading.Event()
    threading.Timer(0.3, cancel.set).start()
    with pytest.raises(EngineError) as info:
        python_engine()._run(["-c", "import time; time.sleep(30)"], cancel=cancel)
    assert info.value.code == "engine.cancelled"
    assert not info.value.transient


def test_output_cap() -> None:
    e = python_engine(max_output_bytes=10_000)
    with pytest.raises(EngineError) as info:
        e._run(["-c", "import sys\nwhile True: sys.stdout.write('x' * 65536)"], timeout_s=20)
    assert info.value.code == "engine.output_too_large"


def test_invalid_output_is_a_structured_error() -> None:
    from openmhs_bridge.models import Comparison

    run = python_engine()._run(["-c", "print('{\"task_type\": 1}')"])
    with pytest.raises(EngineError) as info:
        Engine._parse(Comparison, run)
    assert info.value.code == "engine.output_invalid"
    assert info.value.detail["errors"]


def test_canonical_json_sorts_keys_and_matches_the_engine_rules() -> None:
    a = {"b": 1, "a": {"y": [1, {"d": 2, "c": 3}], "x": None}}
    assert canonical_json(a) == '{"a":{"x":null,"y":[1,{"c":3,"d":2}]},"b":1}'
    assert canonical_json({'k"': "a\nb"}) == '{"k\\"":"a\\nb"}'
    assert digest("") == "sha256:12ae32cb1ec02d01eda3581b127c1fee3b0dc53572ed6baf239721a03d82e126"  # sha256 of '""'


@pytest.mark.parametrize("bad", [1e-7, 1e16, float("nan"), float("inf")])
def test_numbers_the_engine_could_write_differently_are_refused(bad: float) -> None:
    with pytest.raises(ValueError):
        canonical_json({"x": bad})


def test_unknown_error_code_is_a_programming_error() -> None:
    with pytest.raises(ValueError):
        EngineError("engine.whatever", "x")
