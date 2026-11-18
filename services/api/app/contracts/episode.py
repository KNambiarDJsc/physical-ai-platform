"""``pap.episode/1``: one normalized episode with its provenance, and ``pap.evaluation-config/1``."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

EPISODE_SCHEMA = "pap.episode/1"
CONFIG_SCHEMA = "pap.evaluation-config/1"
UNAVAILABLE = "unavailable"

OutcomeClass = Literal[
    "supported_success",  # reported success, verifier satisfied
    "verified_success",  # no usable report, verifier satisfied
    "verified_failure",  # verifier violated, report agrees or is missing
    "contradiction",  # report and verdict disagree
    "unknown",  # verifier could not decide although evidence was present
    "reported_only",  # a report, but no independent evidence at all
    "insufficient_evidence",  # neither a usable report nor independent evidence
]


class Field_(BaseModel):
    """A value with its availability. ``value`` is None exactly when ``available`` is False."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    available: bool
    value: str | None = None

    @model_validator(mode="after")
    def _consistent(self) -> Field_:
        if self.available != (self.value is not None):
            raise ValueError("value is present exactly when available is true")
        return self


class SourceLocator(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    artifact_sha256: str
    row: int = Field(ge=1, description="1-based data row (CSV header excluded) or JSONL line number")


class Episode(BaseModel):
    """Everything known about one attempt, and what is explicitly not known."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_: Literal["pap.episode/1"] = Field(default="pap.episode/1", alias="schema")
    organization: str
    project: str
    evaluation: str = Field(description="sha256 of the canonical evaluation configuration this episode was read for")
    episode_key: str
    release: str
    robot: str
    task_type: str
    site: Field_
    scenario: Field_
    started_at: Field_
    ended_at: str
    clock_domain: str
    reported: Literal["succeeded", "failed", "aborted", "canceled", "timeout", "unknown"]
    reported_raw: str | None
    measurements: dict[str, str | None] = Field(description="Raw cell per measurement name; None = blank cell")
    source: SourceLocator
    mapping: str = Field(description="Mapping name@version sha256")
    evidence_class: Literal["synthetic", "simulated", "physical", "production"]


class EpisodeContext(BaseModel):
    """Who the episode belongs to and which evaluation read it."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    organization: str
    project: str
    evaluation: str


class EvaluationConfig(BaseModel):
    """What to compare and how; passed to ``ops compare`` unchanged."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_: Literal["pap.evaluation-config/1"] = Field(default="pap.evaluation-config/1", alias="schema")
    task_type: str = Field(min_length=1, max_length=200)
    min_known: int = Field(default=30, ge=1, le=100_000)
    margin: float = Field(default=0.01, ge=0, le=1)
    paired: bool = False
    per_attempt: bool = False
    stratify_by_site: bool = True
