"""Versions, requests, approval and results. Approval compiles a version into workflows and queues trials through the
unchanged workflow service; the worker executes them. Nothing here commands a device."""

from __future__ import annotations

import uuid
from collections import Counter
from typing import Any

from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..auth.deps import RANK, OrgContext
from ..config import Settings
from ..db import utcnow
from ..hardware.models import Environment
from ..workflows.definition import definition_sha256
from ..workflows.models import Workflow, WorkflowRun, WorkflowStep
from ..workflows.service import WorkflowError, submit_run
from .compile import compile_trial, workflow_slug
from .host import SpecError, check_model, read_listing, validate
from .models import Experiment, ExperimentRequest, ExperimentTrial, ExperimentVersion
from .spec import ExperimentSpec, checksum

FINAL = ("succeeded", "failed", "outcome_unknown", "cancelled")


def principal_key(ctx: OrgContext) -> str:
    return f"{ctx.principal.kind}:{ctx.principal.id}"


def parse_spec(raw: dict[str, Any]) -> ExperimentSpec:
    try:
        return ExperimentSpec.model_validate(raw)
    except ValidationError as e:
        msg = "; ".join(f"{'.'.join(map(str, x['loc'])) or 'spec'}: {x['msg']}" for x in e.errors())
        raise SpecError(422, "experiment.invalid", msg) from None


def environment(session: Session, org_id: uuid.UUID, slug: str) -> Environment:
    env = session.scalar(select(Environment).where(Environment.organization_id == org_id, Environment.slug == slug))
    if env is None:
        raise SpecError(404, "not_found", "environment not found")
    return env


def create_version(
    session: Session, settings: Settings, ctx: OrgContext, exp: Experiment, raw: dict[str, Any], notes: str
) -> tuple[ExperimentVersion, bool]:
    """Validate against the host's current listing and store, or return the existing version of the same spec."""
    spec = parse_spec(raw)
    if not spec.approval.distinct_approver:
        raise SpecError(422, "experiment.invalid", "An independent approver is required.")
    env = environment(session, ctx.org.id, spec.environment)
    listing = read_listing(session, env, settings)
    scenario = validate(spec, listing)
    check_model(session, ctx.org.id, spec)
    canon = spec.canonical()
    sha = checksum(canon)
    existing = session.scalar(
        select(ExperimentVersion).where(ExperimentVersion.experiment_id == exp.id, ExperimentVersion.spec_sha256 == sha)
    )
    if existing is not None:
        return existing, False
    n = session.scalar(select(func.coalesce(func.max(ExperimentVersion.number), 0)).where(
        ExperimentVersion.experiment_id == exp.id
    ))  # fmt: skip
    v = ExperimentVersion(
        experiment_id=exp.id,
        organization_id=ctx.org.id,
        environment_id=env.id,
        number=int(n or 0) + 1,
        spec=canon,
        spec_sha256=sha,
        scenario=scenario,
        notes=notes,
        created_by=ctx.principal.label,
    )
    session.add(v)
    session.flush()
    return v, True


def request_run(session: Session, ctx: OrgContext, v: ExperimentVersion, note: str) -> ExperimentRequest:
    r = ExperimentRequest(
        organization_id=ctx.org.id,
        version_id=v.id,
        spec_sha256=v.spec_sha256,
        state="awaiting_approval",
        requested_by=ctx.principal.label,
        requested_by_id=principal_key(ctx),
        note=note,
        decision_note="",
    )
    session.add(r)
    session.flush()
    return r


def _decidable(session: Session, ctx: OrgContext, r: ExperimentRequest, reviewed_sha: str) -> ExperimentVersion:
    if r.state != "awaiting_approval":
        raise SpecError(409, "experiment.decided", f"this request is already {r.state.replace('_', ' ')}")
    v = session.get(ExperimentVersion, r.version_id)
    assert v is not None
    if reviewed_sha != v.spec_sha256 or r.spec_sha256 != v.spec_sha256:
        raise SpecError(
            409,
            "experiment.checksum",
            "the checksum you reviewed is not this version's: a decision applies to one exact specification",
        )
    spec = ExperimentSpec.model_validate(v.spec)
    if RANK[ctx.role] < RANK[spec.approval.role]:
        raise SpecError(403, "forbidden", f"this experiment needs an approver with the {spec.approval.role} role")
    if principal_key(ctx) == r.requested_by_id:
        raise SpecError(403, "experiment.self_approval", "this experiment needs someone other than the requester")
    return v


def reject(session: Session, ctx: OrgContext, r: ExperimentRequest, reviewed_sha: str, note: str) -> None:
    _decidable(session, ctx, r, reviewed_sha)
    r.state, r.decided_by, r.decided_at, r.decision_note = "rejected", ctx.principal.label, utcnow(), note
    session.flush()


def approve(
    session: Session, settings: Settings, ctx: OrgContext, r: ExperimentRequest, reviewed_sha: str, note: str
) -> list[ExperimentTrial]:
    """Re-check the version against the host now, then compile and queue every trial. All or nothing."""
    v = _decidable(session, ctx, r, reviewed_sha)
    spec = ExperimentSpec.model_validate(v.spec)
    env = session.get(Environment, v.environment_id)
    assert env is not None
    scenario = validate(spec, read_listing(session, env, settings))
    check_model(session, ctx.org.id, spec)
    trials: list[ExperimentTrial] = []
    capture = "pending" if spec.observations.artifacts else "none"
    for arm in spec.arms:
        plan: list[tuple[int | None, list[int]]] = (
            [(seed, [i]) for i, seed in enumerate(spec.seeds)]
            if spec.seeds
            else [(None, list(range(spec.repetitions)))]
        )
        for seed, reps in plan:
            wf = compile_trial(spec, scenario, arm.key, seed)
            definition = wf.model_dump(mode="json", by_alias=True, exclude_none=True)
            w = Workflow(
                organization_id=ctx.org.id,
                environment_id=env.id,
                slug=workflow_slug(r.id.hex, arm.key, reps[0] if seed is not None else None),
                name=f"{v.spec['scenario']['id']} · {arm.key}" + (f" · seed {seed}" if seed is not None else ""),
                description=f"Compiled from experiment version {v.number} ({v.spec_sha256}), request {r.id}.",
                template="experiment",
                parameters={"experiment_version": str(v.id), "arm": arm.key, "seed": seed},
                definition=definition,
                definition_sha256=definition_sha256(definition),
            )
            session.add(w)
            session.flush()
            for rep in reps:
                try:
                    run = submit_run(session, w, r.requested_by)
                except WorkflowError as e:
                    raise SpecError(e.status, e.code, e.message) from e
                t = ExperimentTrial(
                    request_id=r.id,
                    organization_id=ctx.org.id,
                    arm=arm.key,
                    repetition=rep,
                    seed=seed,
                    workflow_id=w.id,
                    run_id=run.id,
                    capture_state=capture,
                    artifacts=[],
                )
                session.add(t)
                trials.append(t)
    r.state, r.decided_by, r.decided_at, r.decision_note = "approved", ctx.principal.label, utcnow(), note
    session.flush()
    return trials


# ------------------------------------------------------------------------------------------------------ results


def trial_view(session: Session, t: ExperimentTrial, spec: ExperimentSpec) -> dict[str, Any]:
    run = session.get(WorkflowRun, t.run_id)
    assert run is not None
    step = session.scalar(select(WorkflowStep).where(WorkflowStep.run_id == run.id).order_by(WorkflowStep.position))
    out = step.output if step is not None and step.state == "completed" else None
    measurements = (out or {}).get("measurements") if isinstance(out, dict) else None
    wanted = list(dict.fromkeys([*spec.observations.measurements, *(c.measurement for c in spec.contract.conditions)]))
    return {
        "id": str(t.id),
        "arm": t.arm,
        "repetition": t.repetition,
        "seed": t.seed,
        "run_id": str(run.id),
        "state": run.state,
        "step_state": step.state if step is not None else None,
        "verdict": (run.verification or {}).get("verdict"),
        "error": run.error,
        "measurements": {m: measurements[m] for m in wanted if m in measurements}
        if isinstance(measurements, dict)
        else None,
        "host_run": {k: out.get(k) for k in ("run_id", "identity", "started_at", "finished_at", "duration_s")}
        if isinstance(out, dict)
        else None,
        "capture_state": t.capture_state,
        "capture_error": t.capture_error,
        "artifacts": t.artifacts,
        "recording_id": str(t.recording_id) if t.recording_id else None,
        "started_at": run.started_at,
        "finished_at": run.finished_at,
    }


def arm_summary(spec: ExperimentSpec, trials: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Raw values and verdict counts per arm. No statistic: a comparison verdict is the engine's (`ops compare`)."""
    out = []
    for a in spec.arms:
        mine = [t for t in trials if t["arm"] == a.key]
        values: dict[str, list[Any]] = {}
        for t in mine:
            for k, val in (t["measurements"] or {}).items():
                values.setdefault(k, []).append(val)
        out.append(
            {
                "arm": a.key,
                "title": a.title,
                "role": a.role,
                "parameters": a.parameters,
                "trials": len(mine),
                "states": dict(Counter(t["state"] for t in mine)),
                "verdicts": dict(Counter(t["verdict"] or "none" for t in mine if t["state"] in FINAL)),
                "values": values,
            }
        )
    return out
