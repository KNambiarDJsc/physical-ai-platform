"""DATA-001: versioned contracts. Pydantic is the source; committed JSON Schemas must match it."""

from __future__ import annotations

import json

import pytest
from app.contracts import export
from app.contracts.episode import Episode
from pydantic import ValidationError


def test_committed_schemas_match_the_models() -> None:
    files = export.render()
    assert set(files) == {
        "pap.mapping-1.schema.json",
        "pap.episode-1.schema.json",
        "pap.evaluation-config-1.schema.json",
    }
    for name, text in files.items():
        path = export.OUT / name
        assert path.exists(), f"{name} not generated; run python -m app.contracts.export"
        assert path.read_text(encoding="utf-8") == text, f"{name} is stale; run python -m app.contracts.export"


@pytest.mark.parametrize("name", ["pap.mapping-1", "pap.episode-1", "pap.evaluation-config-1"])
def test_every_document_carries_its_schema_version(name: str) -> None:
    schema = json.loads((export.OUT / f"{name}.schema.json").read_text(encoding="utf-8"))
    assert schema["properties"]["schema"]["const"] == name.replace("-1", "/1")


def test_episode_cannot_omit_context_or_provenance() -> None:
    required = set(Episode.model_json_schema(by_alias=True)["required"])
    for field in ("organization", "project", "evaluation", "robot", "task_type", "release", "site", "scenario",
                  "started_at", "ended_at", "source", "mapping", "evidence_class"):  # fmt: skip
        assert field in required, f"{field} must be present (value or explicit unavailable marker)"


def test_unavailable_marker_cannot_carry_a_value() -> None:
    from app.contracts.episode import Field_

    Field_(available=False)
    Field_(available=True, value="x")
    with pytest.raises(ValidationError):
        Field_(available=False, value="x")
    with pytest.raises(ValidationError):
        Field_(available=True)
