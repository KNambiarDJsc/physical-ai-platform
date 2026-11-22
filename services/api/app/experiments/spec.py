"""The experiment specification (``pap.experiment-spec/1``): immutable, content-addressed, validated against the host.

A version is the canonical JSON of this model; its checksum is sha256 over that JSON, computed here and never taken
from the client. What the spec cannot control (the operator's scenario definition, the simulator) is pinned by digest
and identity, so a change underneath a version invalidates it instead of silently changing what runs (D-037).
"""

from __future__ import annotations

import hashlib
import json
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

KEY = r"^[a-z][a-z0-9_-]{0,63}$"
SLUG = r"^[a-z0-9][a-z0-9-]{0,62}$"
SHA = r"^sha256:[0-9a-f]{64}$"
SCHEMA = "pap.experiment-spec/1"


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SimulatorRef(_Strict):
    """The simulator as the host reported it when the version was created."""

    kind: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=120)
    version: str | None = Field(default=None, max_length=64)


class ScenarioRef(_Strict):
    id: str = Field(pattern=KEY)
    version: str = Field(min_length=1, max_length=32)
    definition_sha256: str = Field(pattern=SHA, description="Digest of the scenario as the host listed it.")


class ModelRef(_Strict):
    """A registered robot or instrument model version (Digital Twin model registry)."""

    project: str = Field(pattern=SLUG)
    model: str = Field(pattern=SLUG)
    version: int = Field(ge=1)


class SoftwareRev(_Strict):
    """A controller or software component and the exact revision under test, as declared by the engineer."""

    name: str = Field(min_length=1, max_length=120)
    revision: str = Field(min_length=1, max_length=120)


class Arm(_Strict):
    key: str = Field(pattern=KEY)
    title: str = Field(default="", max_length=200)
    role: Literal["baseline", "candidate"] = "candidate"
    parameters: dict[str, Any] = Field(default_factory=dict)


class Limits(_Strict):
    max_trials: int = Field(ge=1, le=200, description="Upper bound on arms x repetitions.")
    max_wall_time_s: int = Field(
        ge=1, le=7 * 24 * 3600, description="Upper bound on trials x the scenario's own maximum duration."
    )


class Observations(_Strict):
    """What a trial must produce. Every name must be one the scenario declares."""

    measurements: list[str] = Field(default_factory=list, max_length=50)
    artifacts: list[str] = Field(default_factory=list, max_length=20)
    recording: str | None = Field(
        default=None, description="An MCAP artifact to register as a Digital Twin recording (needs `model`)."
    )
    summary: str | None = Field(
        default=None, description="A JSON artifact: the bag summary (pap.ros.bag-summary/1) of the recording."
    )


class Condition(_Strict):
    name: str = Field(min_length=1, max_length=200)
    measurement: str = Field(min_length=1, max_length=128)
    op: Literal["eq", "ne", "lt", "le", "gt", "ge", "between", "in"]
    value: Any = None
    values: list[Any] | None = None
    min: float | None = None
    max: float | None = None

    @model_validator(mode="after")
    def _operands(self) -> Condition:
        if self.op == "between" and (self.min is None or self.max is None):
            raise ValueError(f"condition {self.name!r}: between needs min and max")
        if self.op == "in" and not self.values:
            raise ValueError(f"condition {self.name!r}: in needs values")
        if self.op not in ("between", "in") and self.value is None:
            raise ValueError(f"condition {self.name!r}: {self.op} needs a value")
        return self


class Contract(_Strict):
    name: str = Field(pattern=KEY)
    version: str = Field(min_length=1, max_length=32)
    conditions: list[Condition] = Field(min_length=1, max_length=20)


class Approval(_Strict):
    role: Literal["engineer", "admin"] = "engineer"
    distinct_approver: bool = Field(default=True, description="The approver must not be the person who requested.")


class ExperimentSpec(_Strict):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    schema_: Literal["pap.experiment-spec/1"] = Field(default="pap.experiment-spec/1", alias="schema")
    environment: str = Field(pattern=SLUG)
    simulator: SimulatorRef
    scenario: ScenarioRef
    model: ModelRef | None = None
    software: list[SoftwareRev] = Field(min_length=1, max_length=20)
    initial_conditions: dict[str, Any] = Field(
        default_factory=dict, description="Scenario parameters shared by every arm (the same conditions in each)."
    )
    seeds: list[Annotated[int, Field(ge=0, le=2**31 - 1)]] = Field(default_factory=list, max_length=50)
    repetitions: int = Field(default=1, ge=1, le=50)
    arms: list[Arm] = Field(min_length=1, max_length=8)
    limits: Limits
    observations: Observations = Field(default_factory=Observations)
    contract: Contract
    approval: Approval = Field(default_factory=Approval)

    @model_validator(mode="after")
    def _shape(self) -> ExperimentSpec:
        keys = [a.key for a in self.arms]
        if len(set(keys)) != len(keys):
            raise ValueError("arm keys must be unique")
        if sum(a.role == "baseline" for a in self.arms) > 1:
            raise ValueError("at most one arm is the baseline")
        if self.seeds and len(self.seeds) != self.repetitions:
            raise ValueError(
                f"{len(self.seeds)} seeds for {self.repetitions} repetitions: give one seed per repetition"
            )
        if len(set(self.seeds)) != len(self.seeds):
            raise ValueError("seeds must differ, or the repetitions are the same trial")
        for a in self.arms:
            shared = sorted(set(a.parameters) & set(self.initial_conditions))
            if shared:
                raise ValueError(f"arm {a.key!r} redefines initial conditions {shared}; arms differ only elsewhere")
            if "seed" in a.parameters or "seed" in self.initial_conditions:
                raise ValueError("the seed comes from `seeds`, not from parameters")
        if self.observations.recording and self.model is None:
            raise ValueError("a recording is registered on a model version: give `model`")
        if self.observations.recording and self.observations.recording not in self.observations.artifacts:
            raise ValueError("the recording must be one of the required artifacts")
        if self.observations.summary and (
            not self.observations.recording or self.observations.summary not in self.observations.artifacts
        ):
            raise ValueError("a summary describes a recording: name both as required artifacts")
        return self

    @property
    def trials(self) -> int:
        return len(self.arms) * self.repetitions

    def canonical(self) -> dict[str, Any]:
        return self.model_dump(mode="json", by_alias=True)


def canonical_json(d: Any) -> str:
    return json.dumps(d, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def checksum(d: Any) -> str:
    return "sha256:" + hashlib.sha256(canonical_json(d).encode()).hexdigest()
