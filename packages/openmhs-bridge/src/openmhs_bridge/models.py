"""Typed views of the engine's JSON outputs at the pinned commit.

Fields the platform reads are required and typed, so a change in the engine's output fails here, loudly, instead
of downstream. Unknown extra fields are kept (``extra="allow"``): additive engine changes do not break the bridge,
and the raw output is always persisted verbatim next to the parsed view.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class _Out(BaseModel):
    model_config = ConfigDict(extra="allow", frozen=True)


# ------------------------------------------------------------------------------------------------ outcome verify


class ConditionResult(_Out):
    evidence: str
    index: int
    op: str
    result: Literal["TRUE", "FALSE", "UNDETERMINED"]
    observed: list[Any]
    records: list[str]
    name: str | None = None


class Reason(_Out):
    code: str
    detail: str | None = None
    item: str | None = None
    record: str | None = None


class ItemReport(_Out):
    accepted: list[str]
    anchor: bool
    rejected: list[Reason]
    provenance: list[str] = Field(default_factory=list)


class VerifierReport(_Out):
    verdict: Literal["SATISFIED", "VIOLATED", "UNKNOWN"]
    verifier: str
    conditions: list[ConditionResult]
    reasons: list[Reason]
    items: dict[str, ItemReport]
    contract: dict[str, Any]
    evidence: dict[str, Any]


# ------------------------------------------------------------------------------------------------ ops ingest


class RebuildSummary(_Out):
    rules_version: str
    task_attempts: int
    incidents: int
    rollouts: int
    rollout_conflicts: int


class IngestResult(_Out):
    ingested: dict[str, int]
    rejected: list[str]
    rebuild: RebuildSummary


# ------------------------------------------------------------------------------------------------ ops compare


class Arm(_Out):
    selector: str
    manifests: list[str]
    attempts: int
    attempt_outcomes: tuple[int, int, int]
    scenarios: int
    unit: Literal["attempt", "scenario"]
    succeeded: int
    failed: int
    unknown: int
    excluded: dict[str, int]
    rate: float | None
    ci95: tuple[float, float] | None
    unknown_bounds: tuple[float, float] | None
    sites: dict[str, int]
    incidents: list[str]
    duration_s: tuple[float, float, int] | None
    wall_s: tuple[float, float, int] | None
    goal_verdicts: dict[str, tuple[int, int, int]]


class Stratum(_Out):
    site: str
    a: tuple[int, int]
    b: tuple[int, int]
    difference: tuple[float, float, float] | None


class Paired(_Out):
    pairs: int
    both_fail: int
    a_only_fails: int
    b_only_fails: int
    both_ok: int
    unknown_pairs: int
    unmatched_a: int
    unmatched_b: int
    difference: tuple[float, float, float] | None
    mcnemar_p: float | None


class Comparison(_Out):
    task_type: str
    outcome: Literal["reported", "verified"]
    a: Arm
    b: Arm
    difference: tuple[float, float, float] | None
    difference_method: str
    unknown_bounds: tuple[float, float] | None
    strata: list[Stratum]
    paired: Paired | None
    verdict: Literal["regression", "improvement", "no_change", "insufficient_evidence"]
    reasons: list[str]
    warnings: list[str]
    rules_version: str


# ------------------------------------------------------------------------------------------------ ops incidents


class IncidentSummary(_Out):
    incident_id: str
    robot: str
    site: str | None
    task_id: str
    task_type: str
    opened_ns: int | None
    triggers: list[str]
    reported: str | None
    verified: str | None
    release: str | None
    members: int
    status: str
    headline: str | None = None
    signature: str | None = None


class IncidentDetail(_Out):
    summary: IncidentSummary
    members: list[dict[str, Any]]
    rules_version: str


# ------------------------------------------------------------------------------------------------ provenance


class EngineProvenance(_Out):
    """What produced a result. Attached to everything the bridge returns."""

    engine: Literal["openmhs"] = "openmhs"
    version: str
    binary_sha256: str
    commit: str
    interfaces: dict[str, str]
