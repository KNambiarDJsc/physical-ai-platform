"""Workflow runs: submission, claiming with a lease, heartbeat, recovery. Same pattern as evaluation jobs."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select, text, update
from sqlalchemy.orm import Session

from ..db import utcnow
from ..hardware.models import Capability, Device, Environment
from .definition import WorkflowDef
from .models import Workflow, WorkflowRun, WorkflowStep


class WorkflowError(Exception):
    def __init__(self, status: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status, self.code, self.message = status, code, message


def check_against_devices(session: Session, env: Environment, wf: WorkflowDef) -> dict[str, Device]:
    """Every step names a present device of the environment and an action that device has."""
    devices = {d.key: d for d in session.scalars(select(Device).where(Device.environment_id == env.id))}
    for s in wf.steps:
        d = devices.get(s.device)
        if d is None or not d.present:
            raise WorkflowError(422, "workflow.unknown_device", f"step {s.id}: no device {s.device!r} in {env.slug}")
        cap = session.scalar(
            select(Capability).where(
                Capability.device_id == d.id, Capability.kind == "action", Capability.name == s.action
            )
        )
        if cap is None:
            raise WorkflowError(422, "workflow.unknown_action", f"step {s.id}: {s.device} has no action {s.action!r}")
        required = set((cap.input_schema or {}).get("required", [])) - {cap.idempotency_key}
        missing = required - set(s.input)
        if missing:
            raise WorkflowError(
                422, "workflow.missing_input", f"step {s.id}: {s.device}.{s.action} needs {sorted(missing)}"
            )
    return devices


def submit_run(session: Session, workflow: Workflow, submitted_by: str) -> WorkflowRun:
    env = session.get(Environment, workflow.environment_id)
    assert env is not None
    wf = WorkflowDef.model_validate(workflow.definition)
    devices = check_against_devices(session, env, wf)  # devices may have changed since the workflow was saved
    run = WorkflowRun(
        id=uuid.uuid4(),
        organization_id=workflow.organization_id,
        workflow_id=workflow.id,
        environment_id=env.id,
        definition=workflow.definition,
        state="queued",
        submitted_by=submitted_by,
    )
    session.add(run)
    for i, s in enumerate(wf.steps):
        d = devices[s.device]
        cap = session.scalar(
            select(Capability).where(
                Capability.device_id == d.id, Capability.kind == "action", Capability.name == s.action
            )
        )
        assert cap is not None
        session.add(
            WorkflowStep(
                run_id=run.id,
                position=i,
                step_key=s.id,
                device_id=d.id,
                device_key=d.key,
                action=s.action,
                input=s.input,
                request_id=f"{run.id.hex}-{i}",
                idempotent=cap.idempotency_key == "request_id",
                state="pending",
            )
        )
    session.flush()
    return run


def claim(session: Session, worker: str, lease_s: int) -> uuid.UUID | None:
    row = session.execute(
        text(
            """
            UPDATE workflow_runs
               SET state = 'running', lease_owner = :worker, lease_expires_at = now() + make_interval(secs => :lease),
                   attempts = attempts + 1, started_at = coalesce(started_at, now()), updated_at = now()
             WHERE id = (SELECT id FROM workflow_runs WHERE state = 'queued'
                          ORDER BY created_at FOR UPDATE SKIP LOCKED LIMIT 1)
            RETURNING id
            """
        ),
        {"worker": worker, "lease": lease_s},
    ).first()
    session.commit()
    return row[0] if row else None


def heartbeat(session: Session, run_id: uuid.UUID, worker: str, lease_s: int) -> bool:
    row = session.execute(
        text(
            """
            UPDATE workflow_runs SET lease_expires_at = now() + make_interval(secs => :lease), updated_at = now()
             WHERE id = :id AND state = 'running' AND lease_owner = :worker
            RETURNING id
            """
        ),
        {"id": run_id, "worker": worker, "lease": lease_s},
    ).first()
    session.commit()
    return row is not None


def recover_expired(session: Session) -> int:
    """Runs whose worker stopped renewing its lease go back to the queue (the executor resumes from the journal),
    or fail when out of attempts."""
    rows = session.execute(
        text(
            """
            UPDATE workflow_runs
               SET state = CASE WHEN attempts >= max_attempts THEN 'failed' ELSE 'queued' END,
                   finished_at = CASE WHEN attempts >= max_attempts THEN now() END,
                   error = jsonb_build_object('code', 'worker.lost', 'message',
                           'the worker stopped renewing its lease', 'worker', lease_owner, 'attempt', attempts),
                   lease_owner = NULL, lease_expires_at = NULL, updated_at = now()
             WHERE state = 'running' AND lease_expires_at < now()
            RETURNING id
            """
        )
    ).all()
    session.commit()
    return len(rows)


def finish(session: Session, run_id: uuid.UUID, worker: str, state: str, **values: Any) -> bool:
    res = session.execute(
        update(WorkflowRun)
        .where(WorkflowRun.id == run_id, WorkflowRun.lease_owner == worker, WorkflowRun.state == "running")
        .values(
            state=state, finished_at=utcnow(), updated_at=utcnow(), lease_owner=None, lease_expires_at=None, **values
        )
    )
    session.commit()
    return bool(getattr(res, "rowcount", 0) == 1)


def requeue(session: Session, run_id: uuid.UUID, worker: str, error: dict[str, Any]) -> None:
    session.execute(
        update(WorkflowRun)
        .where(WorkflowRun.id == run_id, WorkflowRun.lease_owner == worker, WorkflowRun.state == "running")
        .values(state="queued", error=error, lease_owner=None, lease_expires_at=None, updated_at=utcnow())
    )
    session.commit()
