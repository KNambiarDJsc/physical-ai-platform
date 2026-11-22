"""Workflow definitions (``pap.workflow/1``) and the built-in templates.

A definition is ordered device actions and, optionally, a verification: which step is the instrument's claim, which
step outputs are independent evidence, and the conditions the engine checks. The platform only assembles the RFC 0004
contract from it; the verdict is the engine's (``openmhs outcome verify``).
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

KEY = r"^[a-z][a-z0-9_-]{0,63}$"
WATER_G_PER_UL = 0.0009982  # density of water at 20 °C; turns a volume target into a mass target


class StepDef(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(pattern=KEY)
    device: str = Field(min_length=1, max_length=128)
    action: str = Field(min_length=1, max_length=128)
    input: dict[str, Any] = Field(default_factory=dict)
    title: str = ""
    timeout_s: float | None = Field(
        default=None, gt=0, le=6 * 3600, description="How long to wait for this step (default: the worker's setting)."
    )


class EvidenceDef(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(pattern=KEY)
    step: str = Field(pattern=KEY)
    output_field: str = Field(
        min_length=1, max_length=128, description="A field of the step's output; dots reach into nested objects."
    )
    signal: str = Field(min_length=1, max_length=128)
    unit: str | None = None
    kind: Literal["independent_sensor", "device_state"] = "independent_sensor"


class ConditionDef(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=200)
    evidence: str = Field(pattern=KEY)
    op: Literal["eq", "ne", "lt", "le", "gt", "ge", "between", "in"]
    value: Any = None
    values: list[Any] | None = None
    min: Any = None
    max: Any = None


class VerificationDef(BaseModel):
    model_config = ConfigDict(extra="forbid")
    contract: str = Field(min_length=1, max_length=120)
    version: str = Field(min_length=1, max_length=32)
    claim_step: str = Field(pattern=KEY)
    window_ms: tuple[int, int] = (0, 120_000)
    max_clock_uncertainty_ms: int = Field(default=1000, ge=0)
    evidence: list[EvidenceDef] = Field(min_length=1)
    conditions: list[ConditionDef] = Field(min_length=1)


class WorkflowDef(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    schema_: Literal["pap.workflow/1"] = Field(default="pap.workflow/1", alias="schema")
    steps: list[StepDef] = Field(min_length=1, max_length=50)
    verification: VerificationDef | None = None

    @model_validator(mode="after")
    def _references(self) -> WorkflowDef:
        ids = [s.id for s in self.steps]
        if len(set(ids)) != len(ids):
            raise ValueError("step ids must be unique")
        v = self.verification
        if v:
            if v.claim_step not in ids:
                raise ValueError(f"claim_step {v.claim_step!r} is not a step")
            names = {e.name for e in v.evidence}
            for e in v.evidence:
                if e.step not in ids:
                    raise ValueError(f"evidence {e.name!r} reads step {e.step!r}, which does not exist")
            for c in v.conditions:
                if c.evidence not in names:
                    raise ValueError(f"condition {c.name!r} uses unknown evidence {c.evidence!r}")
        return self


def definition_sha256(d: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(d, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


# ------------------------------------------------------------------------------------------------------- templates


class DispenseParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    volume_ul: float = Field(default=50.0, gt=0, le=1000, description="Volume to dispense, in µL.")
    tolerance_pct: float = Field(
        default=2.0, gt=0, le=50, description="Accepted deviation of the delivered volume, ±%."
    )
    pump: str = Field(default="pump", description="Device key of the pump.")
    balance: str = Field(default="balance", description="Device key of the balance.")


def dispense_and_verify(p: DispenseParams) -> WorkflowDef:
    """Tare, dispense, weigh; the balance's reading is the independent evidence for the pump's claim."""
    target_g = p.volume_ul * WATER_G_PER_UL
    lo, hi = target_g * (1 - p.tolerance_pct / 100), target_g * (1 + p.tolerance_pct / 100)
    return WorkflowDef(
        steps=[
            StepDef(id="tare", device=p.balance, action="tare", title="Zero the balance"),
            StepDef(
                id="dispense",
                device=p.pump,
                action="dispense",
                input={"volume_ul": p.volume_ul},
                title=f"Dispense {p.volume_ul:g} µL",
            ),
            StepDef(id="weigh", device=p.balance, action="weigh", title="Weigh the delivered liquid"),
        ],
        verification=VerificationDef(
            contract="volume-delivered",
            version="1",
            claim_step="dispense",
            evidence=[
                EvidenceDef(
                    name="delivered_mass", step="weigh", output_field="mass_g", signal="vessel.net_mass", unit="g"
                )
            ],
            conditions=[
                ConditionDef(
                    name=f"{p.volume_ul:g} µL ± {p.tolerance_pct:g} % delivered (as water at 20 °C: "
                    f"{lo:.4f}–{hi:.4f} g)",
                    evidence="delivered_mass",
                    op="between",
                    min={"value": round(lo, 6), "unit": "g"},
                    max={"value": round(hi, 6), "unit": "g"},
                )
            ],
        ),
    )


TEMPLATES: dict[str, tuple[str, str, type[BaseModel]]] = {
    "dispense-and-verify": (
        "Dispense and verify",
        "Tare the balance, dispense a volume with the pump, weigh it. The pump's report is the claim; the balance's "
        "reading is the independent evidence the engine checks against the tolerance.",
        DispenseParams,
    ),
}


def from_template(name: str, params: dict[str, Any]) -> WorkflowDef:
    if name == "dispense-and-verify":
        return dispense_and_verify(DispenseParams(**params))
    raise ValueError(f"unknown template {name!r}")
