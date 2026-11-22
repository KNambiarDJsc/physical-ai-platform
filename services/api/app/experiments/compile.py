"""Compile an approved spec into ordinary workflows (``pap.workflow/1``): one ``run_scenario`` step whose output's
measurements are the evidence, and the spec's contract as the engine's conditions. Nothing here executes anything."""

from __future__ import annotations

import re
from typing import Any

from ..workflows.definition import ConditionDef, EvidenceDef, StepDef, VerificationDef, WorkflowDef
from .host import HOST, trial_parameters
from .spec import KEY, Condition, ExperimentSpec

STEP = "run"
TIMEOUT_MARGIN_S = 60.0  # only the host can stop a running simulator; wait a little past its own limit (D-037)


def _evidence_name(measurement: str, i: int) -> str:
    return measurement if re.fullmatch(KEY, measurement) else f"m{i}"


def _operand(x: Any, unit: str | None) -> Any:
    numeric = isinstance(x, int | float) and not isinstance(x, bool)
    return {"value": x, "unit": unit} if unit and numeric else x


def _condition(c: Condition, evidence: str, unit: str | None) -> ConditionDef:
    if c.op == "between":
        return ConditionDef(
            name=c.name, evidence=evidence, op="between", min=_operand(c.min, unit), max=_operand(c.max, unit)
        )
    if c.op == "in":
        return ConditionDef(name=c.name, evidence=evidence, op="in", values=c.values)
    return ConditionDef(name=c.name, evidence=evidence, op=c.op, value=_operand(c.value, unit))


def compile_trial(spec: ExperimentSpec, scenario: dict[str, Any], arm: str, seed: int | None) -> WorkflowDef:
    outputs = {o["name"]: o for o in scenario.get("outputs", [])}
    used = list(dict.fromkeys(c.measurement for c in spec.contract.conditions))
    names = {m: _evidence_name(m, i) for i, m in enumerate(used)}
    title = f"{scenario.get('title') or spec.scenario.id} · {arm}" + (f" · seed {seed}" if seed is not None else "")
    return WorkflowDef(
        steps=[
            StepDef(
                id=STEP,
                device=HOST,
                action="run_scenario",
                input={
                    "scenario": spec.scenario.id,
                    "scenario_version": spec.scenario.version,
                    "parameters": trial_parameters(spec, arm, seed),
                },
                title=title,
                timeout_s=float(scenario.get("max_duration_s") or 0) + TIMEOUT_MARGIN_S,
            )
        ],
        verification=VerificationDef(
            contract=spec.contract.name,
            version=spec.contract.version,
            claim_step=STEP,
            evidence=[
                EvidenceDef(
                    name=names[m],
                    step=STEP,
                    output_field=f"measurements.{m}",
                    signal=f"sim.{m}",
                    unit=outputs[m].get("unit"),
                    kind="independent_sensor",
                )
                for m in used
            ],
            conditions=[
                _condition(c, names[c.measurement], outputs[c.measurement].get("unit"))
                for c in spec.contract.conditions
            ],
        ),
    )


def workflow_slug(request_hex: str, arm: str, repetition: int | None) -> str:
    base = f"x-{request_hex[:12]}-{arm.replace('_', '-')}"[:56].rstrip("-")
    return base + (f"-s{repetition}" if repetition is not None else "")
