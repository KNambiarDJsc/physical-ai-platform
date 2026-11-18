"""``pap.mapping/1``: how rows of a customer file become episodes, OpenMHS events and verifier evidence.

A mapping is declarative and versioned; it never contains code. It names where every value comes from (a column,
or a constant), how to read times, which column holds what the robot reported, which columns are independent
measurements (with units), and the RFC 0004 outcome contract those measurements are judged against. Fields that are
missing are marked unavailable or reject the row, per ``missing_data``; nothing is guessed.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

SCHEMA = "pap.mapping/1"
NAME = r"^[a-z0-9][a-z0-9._-]{0,99}$"
REPORTED = ("succeeded", "failed", "aborted", "canceled", "timeout", "unknown")
OPS = ("eq", "ne", "lt", "le", "gt", "ge", "between", "in")


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Source(_Strict):
    """Where a value comes from: a column (dotted path for JSONL objects) or a constant. Exactly one."""

    column: str | None = Field(default=None, min_length=1, max_length=200)
    const: str | None = Field(default=None, min_length=1, max_length=200)

    @model_validator(mode="after")
    def _one(self) -> Source:
        if (self.column is None) == (self.const is None):
            raise ValueError("set exactly one of column or const")
        return self


class TimeSource(Source):
    format: Literal["rfc3339", "unix_s", "unix_ms"] = "rfc3339"
    clock_domain: str = Field(min_length=1, max_length=200, description="Names the clock (RFC 0005 time.clock_domain)")
    uncertainty_ms: float | None = Field(default=None, ge=0, description="Absent means unknown, not zero")


class InputSpec(_Strict):
    format: Literal["csv", "jsonl"]
    delimiter: Annotated[str, Field(min_length=1, max_length=1)] = ","
    max_rows: int = Field(default=200_000, ge=1, le=2_000_000)


class ReportedOutcome(_Strict):
    column: str = Field(min_length=1, max_length=200)
    values: dict[str, Literal["succeeded", "failed", "aborted", "canceled", "timeout", "unknown"]] = Field(
        min_length=1, description="Source value -> RFC 0005 reported outcome. Unlisted values reject the row."
    )
    missing: Literal["unknown", "reject"] = "unknown"


class Measurement(_Strict):
    """An independent (or device) measurement column, turned into an RFC 0004 evidence record."""

    name: str = Field(pattern=r"^[a-z][a-z0-9_]{0,40}$", description="Evidence item name used by the contract")
    column: str = Field(min_length=1, max_length=200)
    signal: str = Field(min_length=1, max_length=200)
    kind: Literal["independent_sensor", "device_state", "operator"] = "independent_sensor"
    value_type: Literal["number", "string", "boolean"] = "number"
    unit: str | None = Field(default=None, max_length=40, description="UCUM unit for numbers; omit for unitless")
    system: str = Field(min_length=1, max_length=100)
    device: str | None = Field(default=None, max_length=100)
    time: TimeSource | None = Field(
        default=None, description="When it was measured. Without it the record has no time and the verifier says so."
    )
    quality_column: str | None = Field(default=None, description="Column holding GOOD / UNCERTAIN / BAD")


class Condition(_Strict):
    name: str = Field(min_length=1, max_length=200)
    evidence: str
    op: Literal["eq", "ne", "lt", "le", "gt", "ge", "between", "in"]
    value: Any = None
    values: list[Any] | None = None
    min: Any = None
    max: Any = None


class ContractTemplate(_Strict):
    """An RFC 0004 contract without its binding: the platform binds it to each episode and anchors it on the
    robot's own end-of-task report, so ``window_ms`` is relative to that report."""

    name: str = Field(pattern=NAME)
    version: str = "0.1"
    window_ms: tuple[int, int] = (0, 2000)
    max_clock_uncertainty_ms: float = Field(default=50, gt=0)
    conditions: list[Condition] = Field(min_length=1)


class MissingData(_Strict):
    site: Literal["unavailable", "reject"] = "unavailable"
    scenario: Literal["unavailable", "reject"] = "unavailable"
    started_at: Literal["unavailable", "reject"] = "unavailable"
    measurement: Literal["absent", "reject"] = Field(
        default="absent", description="A blank measurement cell: leave the record out (verdict says why) or reject"
    )


class MappingSpec(_Strict):
    model_config = ConfigDict(extra="forbid", frozen=True, populate_by_name=True)

    schema_: Literal["pap.mapping/1"] = Field(alias="schema")
    name: str = Field(pattern=NAME)
    description: str | None = Field(default=None, max_length=2000)
    evidence_class: Literal["synthetic", "simulated", "physical", "production"] = Field(
        description="Where the data comes from. Synthetic and simulated evidence is labelled as such everywhere."
    )
    input: InputSpec
    episode_id: Source
    robot: Source
    task_type: Source
    site: Source | None = None
    scenario: Source | None = None
    started_at: TimeSource | None = None
    ended_at: TimeSource
    reported_outcome: ReportedOutcome
    measurements: list[Measurement] = Field(default_factory=list, max_length=32)
    contract: ContractTemplate | None = None
    missing_data: MissingData = MissingData()

    @model_validator(mode="after")
    def _consistent(self) -> MappingSpec:
        names = [m.name for m in self.measurements]
        if len(set(names)) != len(names):
            raise ValueError("measurement names must be unique")
        if self.contract is None and self.measurements:
            raise ValueError("measurements need a contract that judges them")
        if self.contract is not None:
            unknown = {c.evidence for c in self.contract.conditions} - set(names)
            if unknown:
                raise ValueError(f"contract conditions name unknown measurements: {sorted(unknown)}")
            lo, hi = self.contract.window_ms
            if lo > hi:
                raise ValueError("contract.window_ms must be [low, high]")
        return self
