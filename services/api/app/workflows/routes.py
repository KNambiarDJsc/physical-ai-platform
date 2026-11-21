"""Workflows API. Submitting a run only queues it: the worker executes it (the API never commands a device)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Path, Query
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..auth.deps import SLUG, EngineerDep, ViewerDep, audit_allow, error
from ..db import get_session
from ..hardware.models import Environment
from .definition import TEMPLATES, WorkflowDef, definition_sha256, from_template
from .models import Workflow, WorkflowRun, WorkflowStep
from .service import WorkflowError, check_against_devices, submit_run

router = APIRouter(prefix="/api/v1/orgs/{org_slug}", tags=["workflows"])
SessionDep = Annotated[Session, Depends(get_session)]


class TemplateOut(BaseModel):
    key: str
    title: str
    description: str
    parameters: dict[str, Any]  # JSON Schema of the template's parameters


class WorkflowIn(BaseModel):
    slug: str = Field(pattern=SLUG)
    name: str = Field(min_length=1, max_length=200)
    environment: str = Field(pattern=SLUG)
    template: str | None = Field(default=None, max_length=64)
    parameters: dict[str, Any] = Field(default_factory=dict)
    definition: dict[str, Any] | None = None  # pap.workflow/1, when not from a template
    description: str = Field(default="", max_length=2000)


class WorkflowOut(BaseModel):
    id: uuid.UUID
    slug: str
    name: str
    description: str
    environment: str
    template: str | None
    parameters: dict[str, Any]
    definition: dict[str, Any]
    definition_sha256: str
    created_at: datetime


class StepOut(BaseModel):
    position: int
    key: str
    device_id: uuid.UUID | None
    device: str
    action: str
    input: dict[str, Any]
    request_id: str
    idempotent: bool
    state: str
    dispatches: int
    output: Any
    error: str | None
    invocation_id: str | None
    started_at: datetime | None
    finished_at: datetime | None


class RunOut(BaseModel):
    id: uuid.UUID
    workflow: str
    workflow_name: str
    environment: str
    state: str
    attempts: int
    submitted_by: str
    reported: dict[str, Any] | None
    verdict: str | None
    outcome_class: str | None
    error: dict[str, Any] | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


class RunDetailOut(RunOut):
    definition: dict[str, Any]
    steps: list[StepOut]
    verification: dict[str, Any] | None
    provenance: dict[str, Any] | None


def _wf_out(w: Workflow, env: Environment) -> WorkflowOut:
    return WorkflowOut(
        id=w.id,
        slug=w.slug,
        name=w.name,
        description=w.description,
        environment=env.slug,
        template=w.template,
        parameters=w.parameters,
        definition=w.definition,
        definition_sha256=w.definition_sha256,
        created_at=w.created_at,
    )


def _run_out(session: Session, r: WorkflowRun, *, detail: bool = False) -> RunOut:
    w = session.get(Workflow, r.workflow_id)
    env = session.get(Environment, r.environment_id)
    assert w is not None and env is not None
    base: dict[str, Any] = dict(
        id=r.id,
        workflow=w.slug,
        workflow_name=w.name,
        environment=env.slug,
        state=r.state,
        attempts=r.attempts,
        submitted_by=r.submitted_by,
        reported=r.reported,
        verdict=(r.verification or {}).get("verdict"),
        outcome_class=r.outcome_class,
        error=r.error,
        created_at=r.created_at,
        started_at=r.started_at,
        finished_at=r.finished_at,
    )
    if not detail:
        return RunOut(**base)
    steps = session.scalars(select(WorkflowStep).where(WorkflowStep.run_id == r.id).order_by(WorkflowStep.position))
    return RunDetailOut(
        **base,
        definition=r.definition,
        verification=r.verification,
        provenance=r.provenance,
        steps=[
            StepOut(
                position=s.position,
                key=s.step_key,
                device_id=s.device_id,
                device=s.device_key,
                action=s.action,
                input=s.input,
                request_id=s.request_id,
                idempotent=s.idempotent,
                state=s.state,
                dispatches=s.dispatches,
                output=s.output,
                error=s.error,
                invocation_id=s.invocation_id,
                started_at=s.started_at,
                finished_at=s.finished_at,
            )
            for s in steps
        ],
    )


def _workflow(session: Session, org_id: uuid.UUID, slug: str) -> tuple[Workflow, Environment]:
    w = session.scalar(select(Workflow).where(Workflow.organization_id == org_id, Workflow.slug == slug))
    if w is None:
        raise error(404, "not_found", "workflow not found")
    env = session.get(Environment, w.environment_id)
    assert env is not None
    return w, env


@router.get("/workflow-templates")
def list_templates(ctx: ViewerDep) -> list[TemplateOut]:
    return [
        TemplateOut(key=k, title=t, description=d, parameters=m.model_json_schema())
        for k, (t, d, m) in TEMPLATES.items()
    ]


@router.post("/workflows", status_code=201)
def create_workflow(body: WorkflowIn, ctx: EngineerDep, session: SessionDep) -> WorkflowOut:
    env = session.scalar(
        select(Environment).where(Environment.organization_id == ctx.org.id, Environment.slug == body.environment)
    )
    if env is None:
        raise error(404, "not_found", "environment not found")
    try:
        if body.template:
            if body.template not in TEMPLATES:
                raise error(422, "workflow.unknown_template", f"no template {body.template!r}")
            wf = from_template(body.template, body.parameters)
        elif body.definition is not None:
            wf = WorkflowDef.model_validate(body.definition)
        else:
            raise error(422, "workflow.empty", "give a template or a definition")
    except ValidationError as e:
        raise error(
            422, "workflow.invalid", "; ".join(f"{'.'.join(map(str, x['loc']))}: {x['msg']}" for x in e.errors())
        ) from e
    try:
        check_against_devices(session, env, wf)
    except WorkflowError as e:
        raise error(e.status, e.code, e.message) from e
    definition = wf.model_dump(mode="json", by_alias=True, exclude_none=True)
    w = Workflow(
        organization_id=ctx.org.id,
        environment_id=env.id,
        slug=body.slug,
        name=body.name,
        description=body.description,
        template=body.template,
        parameters=body.parameters,
        definition=definition,
        definition_sha256=definition_sha256(definition),
    )
    session.add(w)
    try:
        session.flush()
    except IntegrityError as e:
        session.rollback()
        raise error(409, "conflict", "a workflow with that slug exists in this workspace") from e
    audit_allow(session, ctx, "workflow.create", f"workflow:{w.id}", environment=env.slug)
    session.commit()
    return _wf_out(w, env)


@router.get("/workflows")
def list_workflows(ctx: ViewerDep, session: SessionDep) -> list[WorkflowOut]:
    rows = session.execute(
        select(Workflow, Environment)
        .join(Environment, Environment.id == Workflow.environment_id)
        .where(Workflow.organization_id == ctx.org.id)
        .order_by(Workflow.slug)
    ).all()
    return [_wf_out(w, e) for w, e in rows]


@router.get("/workflows/{workflow_slug}")
def get_workflow(workflow_slug: Annotated[str, Path(pattern=SLUG)], ctx: ViewerDep, session: SessionDep) -> WorkflowOut:
    return _wf_out(*_workflow(session, ctx.org.id, workflow_slug))


@router.post("/workflows/{workflow_slug}/runs", status_code=201)
def start_run(workflow_slug: Annotated[str, Path(pattern=SLUG)], ctx: EngineerDep, session: SessionDep) -> RunDetailOut:
    """Queue a run. The worker executes it; poll the run for progress."""
    w, _ = _workflow(session, ctx.org.id, workflow_slug)
    try:
        run = submit_run(session, w, ctx.principal.label)
    except WorkflowError as e:
        raise error(e.status, e.code, e.message) from e
    audit_allow(session, ctx, "workflow.run", f"workflow_run:{run.id}", workflow=w.slug)
    session.commit()
    out = _run_out(session, run, detail=True)
    assert isinstance(out, RunDetailOut)
    return out


@router.get("/workflow-runs")
def list_runs(
    ctx: ViewerDep, session: SessionDep, workflow: Annotated[str | None, Query(pattern=SLUG)] = None
) -> list[RunOut]:
    q = select(WorkflowRun).where(WorkflowRun.organization_id == ctx.org.id)
    if workflow:
        w, _ = _workflow(session, ctx.org.id, workflow)
        q = q.where(WorkflowRun.workflow_id == w.id)
    return [_run_out(session, r) for r in session.scalars(q.order_by(WorkflowRun.created_at.desc()).limit(200))]


@router.get("/workflow-runs/{run_id}")
def get_run(run_id: uuid.UUID, ctx: ViewerDep, session: SessionDep) -> RunDetailOut:
    r = session.scalar(select(WorkflowRun).where(WorkflowRun.organization_id == ctx.org.id, WorkflowRun.id == run_id))
    if r is None:
        raise error(404, "not_found", "run not found")
    out = _run_out(session, r, detail=True)
    assert isinstance(out, RunDetailOut)
    return out
