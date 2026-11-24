"""Experiment proposals. Anyone in the workspace may PROPOSE running an existing workflow (the tool layer does, with a
viewer credential); only an engineer may APPROVE, and approval queues the run through the unchanged executor, which
still refuses anything but a simulated environment. A proposal cannot change a workflow, only point at one."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth.deps import SLUG, EngineerDep, ViewerDep, audit_allow, error
from ..db import get_session, utcnow
from ..hardware.models import Environment
from ..workflows.models import Workflow
from ..workflows.service import WorkflowError, submit_run
from .models import ExperimentProposal

router = APIRouter(prefix="/api/v1/orgs/{org_slug}", tags=["agent"])
SessionDep = Annotated[Session, Depends(get_session)]
CHANNEL = "x-pap-channel"


class ProposalIn(BaseModel):
    workflow: str = Field(pattern=SLUG)
    rationale: str = Field(min_length=10, max_length=2000)
    evidence_ids: list[Annotated[str, Field(min_length=1, max_length=200)]] = Field(default_factory=list, max_length=20)


class DecisionIn(BaseModel):
    note: str | None = Field(default=None, max_length=1000)


class ProposalOut(BaseModel):
    id: uuid.UUID
    workflow: str
    environment: str
    environment_kind: str
    rationale: str
    evidence_ids: list[Any]
    state: str
    proposed_by: str
    channel: str
    decided_by: str | None
    decided_at: datetime | None
    decision_note: str | None
    run_id: uuid.UUID | None
    created_at: datetime


def _out(session: Session, p: ExperimentProposal) -> ProposalOut:
    w = session.get(Workflow, p.workflow_id)
    assert w is not None
    env = session.get(Environment, w.environment_id)
    assert env is not None
    return ProposalOut(
        id=p.id,
        workflow=w.slug,
        environment=env.slug,
        environment_kind=env.kind,
        rationale=p.rationale,
        evidence_ids=list(p.evidence_ids or []),
        state=p.state,
        proposed_by=p.proposed_by,
        channel=p.channel,
        decided_by=p.decided_by,
        decided_at=p.decided_at,
        decision_note=p.decision_note,
        run_id=p.run_id,
        created_at=p.created_at,
    )


def _get(session: Session, org_id: uuid.UUID, pid: uuid.UUID, *, decision: bool = False) -> ExperimentProposal:
    query = select(ExperimentProposal).where(ExperimentProposal.organization_id == org_id, ExperimentProposal.id == pid)
    p = session.scalar(query.with_for_update() if decision else query)
    if p is None:
        raise error(404, "not_found", "proposal not found")
    return p


@router.post("/experiment-proposals", status_code=201)
def propose(
    body: ProposalIn, ctx: ViewerDep, session: SessionDep, channel: Annotated[str | None, Header(alias=CHANNEL)] = None
) -> ProposalOut:
    """Record a suggestion. Nothing runs: the state is `proposed` until an engineer decides."""
    w = session.scalar(select(Workflow).where(Workflow.organization_id == ctx.org.id, Workflow.slug == body.workflow))
    if w is None:
        raise error(404, "not_found", "workflow not found")
    p = ExperimentProposal(
        organization_id=ctx.org.id,
        workflow_id=w.id,
        rationale=body.rationale,
        evidence_ids=body.evidence_ids,
        state="proposed",
        proposed_by=ctx.principal.label,
        channel="agent-tools" if channel == "agent-tools" else "api",
    )
    session.add(p)
    session.flush()
    audit_allow(session, ctx, "experiment.propose", f"experiment_proposal:{p.id}", workflow=w.slug, channel=p.channel)
    session.commit()
    return _out(session, p)


@router.get("/experiment-proposals")
def list_proposals(ctx: ViewerDep, session: SessionDep, state: str | None = None) -> list[ProposalOut]:
    q = select(ExperimentProposal).where(ExperimentProposal.organization_id == ctx.org.id)
    if state:
        q = q.where(ExperimentProposal.state == state)
    return [_out(session, p) for p in session.scalars(q.order_by(ExperimentProposal.created_at.desc()).limit(200))]


@router.get("/experiment-proposals/{proposal_id}")
def get_proposal(proposal_id: uuid.UUID, ctx: ViewerDep, session: SessionDep) -> ProposalOut:
    return _out(session, _get(session, ctx.org.id, proposal_id))


@router.post("/experiment-proposals/{proposal_id}/approve")
def approve(proposal_id: uuid.UUID, ctx: EngineerDep, session: SessionDep) -> ProposalOut:
    """An engineer approves: the workflow is queued as an ordinary run (the executor's simulated-only checks apply)."""
    p = _get(session, ctx.org.id, proposal_id, decision=True)
    if p.state != "proposed":
        raise error(409, "conflict", f"this proposal is already {p.state}")
    if p.proposed_by == ctx.principal.label:  # two people: the one who asks is never the one who approves (as D-037)
        raise error(
            403, "separation_of_duties", "A proposal must be approved by someone other than whoever proposed it."
        )
    w = session.get(Workflow, p.workflow_id)
    assert w is not None
    env = session.get(Environment, w.environment_id)
    assert env is not None
    if env.kind != "simulated":
        raise error(409, "not_simulated", "only experiments in a simulated environment can be approved")
    try:
        run = submit_run(session, w, ctx.principal.label)
    except WorkflowError as e:
        raise error(e.status, e.code, e.message) from e
    p.state, p.decided_by, p.decided_at, p.run_id = "approved", ctx.principal.label, utcnow(), run.id
    audit_allow(session, ctx, "experiment.approve", f"experiment_proposal:{p.id}", workflow=w.slug, run=str(run.id))
    session.commit()
    return _out(session, p)


@router.post("/experiment-proposals/{proposal_id}/reject")
def reject(proposal_id: uuid.UUID, body: DecisionIn, ctx: EngineerDep, session: SessionDep) -> ProposalOut:
    p = _get(session, ctx.org.id, proposal_id, decision=True)
    if p.state != "proposed":
        raise error(409, "conflict", f"this proposal is already {p.state}")
    p.state, p.decided_by, p.decided_at, p.decision_note = "rejected", ctx.principal.label, utcnow(), body.note
    audit_allow(session, ctx, "experiment.reject", f"experiment_proposal:{p.id}")
    session.commit()
    return _out(session, p)
