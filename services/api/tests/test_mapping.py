"""DATA-001 / DATA-003: mapping contract validation and row-level behaviour on untrusted input."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from app.contracts.episode import EpisodeContext
from app.contracts.mapping import MappingSpec
from app.ingestion.mapping import ArtifactRejected, apply_mapping, verifier_input
from pydantic import ValidationError

CTX = EpisodeContext(organization="acme", project="picking", evaluation="sha256:cfg")
DEMO = Path(__file__).resolve().parents[3] / "examples" / "manipulation-demo"


def spec(**over: Any) -> MappingSpec:
    base = json.loads((DEMO / "mapping.json").read_text(encoding="utf-8"))
    base.update(over)
    return MappingSpec.model_validate(base)


HEADER = (
    "episode_id,robot_id,site,sku,scenario,start_time,end_time,robot_status,bin_mass_delta_g,bin_mass_quality,"
    "bin_mass_time,vision_in_bin,vision_time,operator_assist\n"
)
GOOD = (
    "e1,arm-1,site-a,sku,sc1,2026-11-02T08:00:00Z,2026-11-02T08:00:10Z,success,300,GOOD,"
    "2026-11-02T08:00:11Z,true,2026-11-02T08:00:10.5Z,false\n"
)


def run(text: str, s: MappingSpec | None = None) -> Any:
    return apply_mapping(
        s or spec(), text.encode(), artifact_sha256="sha256:x", release="r1", mapping_ref="m@1", context=CTX
    )


def test_every_row_is_an_episode_or_a_rejection() -> None:
    rows = [GOOD, GOOD.replace("e1", "e2").replace("success", "boom"), GOOD.replace("e1", "e3")]
    r = run(HEADER + "".join(rows))
    assert r.rows == 3 and len(r.episodes) == 2 and len(r.rejections) == 1
    assert r.rejections[0].row == 2 and r.rejections[0].code == "row.reported"


def test_demo_files_reconcile() -> None:
    for name in ("baseline.csv", "candidate.csv"):
        data = (DEMO / "data" / name).read_bytes()
        r = apply_mapping(spec(), data, artifact_sha256="sha256:x", release="r", mapping_ref="m", context=CTX)
        assert r.rows == len(r.episodes) + len(r.rejections) == 123
        assert sorted(x.code for x in r.rejections) == ["row.reported", "row.required", "row.time"]
        assert all(e.episode.evidence_class == "synthetic" for e in r.episodes)


def test_missing_optional_fields_are_unavailable_not_invented() -> None:
    row = GOOD.replace(",site-a,", ",,").replace(",sc1,", ",,").replace("2026-11-02T08:00:00Z,", ",", 1)
    r = run(HEADER + row)
    ep = r.episodes[0].episode
    assert ep.site.available is False and ep.site.value is None
    assert ep.scenario.available is False
    assert ep.started_at.available is False
    assert r.unavailable == {"scenario": 1, "site": 1, "started_at": 1}


def test_missing_data_policy_reject() -> None:
    s = spec(missing_data={"site": "reject"})
    r = run(HEADER + GOOD.replace(",site-a,", ",,"), s)
    assert [x.code for x in r.rejections] == ["row.required"]


@pytest.mark.parametrize(
    ("change", "code"),
    [
        (("2026-11-02T08:00:10Z", "2026-11-02 08:00:10"), "row.time"),  # no UTC offset: never assumed
        (("2026-11-02T08:00:10Z", "yesterday"), "row.time"),
        ((",300,", ",heavy,"), "row.measurement"),
        ((",GOOD,", ",FINE,"), "row.quality"),
        ((",true,", ",maybe,"), "row.measurement"),
        (("e1,", ","), "row.required"),
        ((",arm-1,", ",,"), "row.required"),
    ],
)
def test_bad_cells_reject_the_row(change: tuple[str, str], code: str) -> None:
    r = run(HEADER + GOOD.replace(*change, 1))
    assert [x.code for x in r.rejections] == [code]


def test_duplicate_episode_is_rejected_with_the_first_row_named() -> None:
    r = run(HEADER + GOOD + GOOD)
    assert r.rejections[0].code == "row.duplicate" and "row 1" in r.rejections[0].message


def test_wrong_cell_count_rejects_only_that_row() -> None:
    r = run(HEADER + GOOD + "e9,arm\n")
    assert len(r.episodes) == 1 and r.rejections[0].code == "row.columns"


@pytest.mark.parametrize(
    ("data", "code"),
    [
        (b"\xff\xfe" + b"x" * 10, "input.encoding"),
        ((HEADER + GOOD).encode().replace(b"e1", b"e\x00"), "input.nul"),
        (b"", "input.empty"),
        (b"a,a\n1,2\n", "input.header"),
        ((HEADER + 'e1,"unterminated\n').encode(), "input.csv"),
    ],
)
def test_artifact_level_problems_reject_the_whole_artifact(data: bytes, code: str) -> None:
    with pytest.raises(ArtifactRejected) as info:
        apply_mapping(spec(), data, artifact_sha256="sha256:x", release="r", mapping_ref="m", context=CTX)
    assert info.value.code == code


def test_row_limit_rejects_the_artifact_instead_of_truncating() -> None:
    s = spec(input={"format": "csv", "max_rows": 2})
    with pytest.raises(ArtifactRejected) as info:
        run(HEADER + GOOD + GOOD.replace("e1", "e2") + GOOD.replace("e1", "e3"), s)
    assert info.value.code == "input.too_many_rows"


def jsonl_spec() -> MappingSpec:
    return spec(
        input={"format": "jsonl"},
        episode_id={"column": "id"},
        robot={"column": "robot.name"},
        site=None,
        scenario=None,
        started_at=None,
        ended_at={"column": "t_end", "format": "unix_ms", "clock_domain": "robot"},
        reported_outcome={"column": "status", "values": {"ok": "succeeded", "fail": "failed"}},
        measurements=[],
        contract=None,
    )


def test_jsonl_nested_fields_unix_times_and_bad_lines() -> None:
    lines = [
        json.dumps({"id": "a", "robot": {"name": "r1"}, "t_end": 1762070400000, "status": "ok"}),
        "{not json",
        "[1, 2]",
        "[" * 100_000 + "]" * 100_000,  # nesting deep enough to exhaust the parser: a row error, not a crash
        json.dumps({"id": "b", "robot": {"name": ["x"]}, "t_end": 1, "status": "ok"}),
        json.dumps({"id": "c", "robot": {"name": "r1"}, "t_end": float("inf"), "status": "ok"}).replace(
            "Infinity", "1e999"
        ),
    ]
    r = apply_mapping(
        jsonl_spec(), "\n".join(lines).encode(), artifact_sha256="s", release="r", mapping_ref="m", context=CTX
    )
    assert r.rows == 6
    assert r.episodes[0].episode.ended_at == "2025-11-02T08:00:00.000000Z"
    assert r.episodes[0].episode.site.available is False
    assert [x.code for x in r.rejections] == ["row.json", "row.json", "row.json", "row.value", "row.value"]


@pytest.mark.parametrize(
    ("over", "message"),
    [
        ({"robot": {"column": "a", "const": "b"}}, "exactly one"),
        ({"contract": None}, "measurements need a contract"),
        ({"schema": "pap.mapping/2"}, "pap.mapping/1"),
        ({"unexpected": 1}, "Extra inputs"),
        ({"evidence_class": "real"}, "synthetic"),
    ],
)
def test_invalid_mappings_are_refused(over: dict[str, Any], message: str) -> None:
    with pytest.raises(ValidationError, match=message):
        spec(**over)


def test_contract_cannot_name_an_unknown_measurement() -> None:
    base = json.loads((DEMO / "mapping.json").read_text(encoding="utf-8"))
    base["contract"]["conditions"][0]["evidence"] = "weight"
    with pytest.raises(ValidationError, match="unknown measurements"):
        MappingSpec.model_validate(base)


def test_verifier_input_is_bound_anchored_and_labelled() -> None:
    r = run(HEADER + GOOD)
    contract, records = verifier_input(spec(), r.episodes[0])  # type: ignore[misc]
    assert contract["binding"] == {"episode": "e1"}
    assert contract["timing"]["anchor"] == "claim"
    assert {rec["id"] for rec in records} == {"claim", "bin_mass", "vision", "assist"}
    assert all(rec["source"]["provenance"] == "simulator" for rec in records)  # synthetic is never "device"
    mass = next(rec for rec in records if rec["id"] == "bin_mass")
    assert mass["value"] == {"value": 300, "unit": "g"} and mass["quality"] == "GOOD"


def test_blank_measurement_produces_no_record() -> None:
    r = run(HEADER + GOOD.replace(",300,", ",,"))
    _, records = verifier_input(spec(), r.episodes[0])  # type: ignore[misc]
    assert "bin_mass" not in {rec["id"] for rec in records}
    assert r.unavailable == {"measurement.bin_mass": 1}
