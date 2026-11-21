"""Runs a workflow in the worker. Never in the API.

Per step, in order: renew the lease; check that a command is allowed at all (D-026); journal the step as
``dispatching``; send; journal the answer. On resume after a crash, a step left ``dispatching`` is re-sent only if the
device deduplicates it (its action takes a ``request_id``), otherwise the run stops as ``outcome_unknown`` (D-028).
When every step is done, the engine verifies the instrument's claim against the independent evidence.
"""

from __future__ import annotations

import hashlib
import json
import logging
import uuid
from datetime import datetime
from typing import Any

from openmhs_bridge import EngineError
from pap_device_sdk import AdapterError, DeviceAdapter
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import Settings, get_settings
from ..db import session_factory, utcnow
from ..engine import get_engine
from ..evaluations.pipeline import outcome_class
from ..hardware.models import Environment
from ..hardware.service import EnvironmentUnavailable, adapter_for, catalog_entry
from . import service
from .definition import VerificationDef, WorkflowDef
from .models import WorkflowRun, WorkflowStep

log = logging.getLogger("pap.workflows")
CLOCK = "pap-worker"  # every timestamp in a run's evidence is taken by the worker when the device answered
CLOCK_UNCERTAINTY_MS = 50


def safety_check(env: Environment, settings: Settings, adapter: DeviceAdapter, device: str) -> str | None:
    """Why a command to this device must not be sent, or None. Both the operator and the device must agree."""
    cfg = catalog_entry(settings, env.config_key)
    if env.kind != "simulated" or cfg is None or cfg.kind != "simulated":
        return "the environment is not configured as simulated; the platform sends commands only to simulated devices"
    try:
        declared = adapter.read_property(device, "simulated")
    except AdapterError as e:
        return f"{device} did not confirm that it is simulated ({e})"
    if declared is not True:
        return f"{device} does not report simulated=true"
    return None


def _iso(t: datetime | None) -> str | None:
    return t.isoformat().replace("+00:00", "Z") if t else None


def build_verifier_input(
    run: WorkflowRun, env: Environment, steps: list[WorkflowStep], v: VerificationDef
) -> tuple[dict[str, Any], list[dict[str, Any]], str]:
    """The RFC 0004 contract and evidence records for one run, and the instrument's reported outcome."""
    by_key = {s.step_key: s for s in steps}
    claim = by_key[v.claim_step]
    reported = "succeeded" if claim.state == "completed" else "failed"
    items: dict[str, Any] = {"claim": {"signal": "task.reported", "kind": "controller", "device": claim.device_key}}
    for e in v.evidence:
        items[e.name] = {"signal": e.signal, "kind": e.kind, "device": by_key[e.step].device_key}
    contract = {
        "contract": v.contract,
        "version": v.version,
        "binding": {"episode": str(run.id)},
        "timing": {
            "anchor": "claim",
            "default_window_ms": list(v.window_ms),
            "max_clock_uncertainty_ms": v.max_clock_uncertainty_ms,
        },
        "evidence": items,
        "conditions": [c.model_dump(exclude_none=True) for c in v.conditions],
    }
    src = {"system": env.slug, "provenance": "simulator"}
    records: list[dict[str, Any]] = [
        {
            "id": "claim",
            "signal": "task.reported",
            "value": reported,
            "source": {**src, "kind": "controller", "device": claim.device_key},
            "time": {"source": _iso(claim.finished_at), "clock_domain": CLOCK, "uncertainty_ms": CLOCK_UNCERTAINTY_MS},
            "refs": {"episode": str(run.id)},
        }
    ]
    for e in v.evidence:
        st = by_key[e.step]
        out = st.output if isinstance(st.output, dict) else {}
        if st.state != "completed" or e.output_field not in out:
            continue  # no record: the engine reports evidence.missing, which is the honest answer
        value: Any = out[e.output_field]
        records.append(
            {
                "id": e.name,
                "signal": e.signal,
                "value": {"value": value, "unit": e.unit} if e.unit else value,
                "source": {**src, "kind": e.kind, "device": st.device_key},
                "time": {"source": _iso(st.finished_at), "clock_domain": CLOCK, "uncertainty_ms": CLOCK_UNCERTAINTY_MS},
                "refs": {"episode": str(run.id)},
            }
        )
    return contract, records, reported


def _digest(x: Any) -> str:
    return hashlib.sha256(json.dumps(x, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _save_step(s: Session, step: WorkflowStep, **values: Any) -> None:
    for k, val in values.items():
        setattr(step, k, val)
    s.add(step)
    s.commit()


def execute_run(run_id: uuid.UUID, worker: str) -> str:
    settings = get_settings()
    with session_factory()() as s:
        run = s.get(WorkflowRun, run_id)
        assert run is not None
        env = s.get(Environment, run.environment_id)
        assert env is not None
        steps = list(
            s.scalars(select(WorkflowStep).where(WorkflowStep.run_id == run_id).order_by(WorkflowStep.position))
        )
        wf = WorkflowDef.model_validate(run.definition)

        def stop(state: str, code: str, message: str, **values: Any) -> str:
            service.finish(s, run_id, worker, state, error={"code": code, "message": message}, **values)
            log.info("run %s: %s (%s)", run_id, state, code)
            return state

        try:
            adapter = adapter_for(env, settings)
        except EnvironmentUnavailable:
            return stop("failed", "environment_unavailable", "the operator no longer offers this environment")

        for step in steps:
            if not service.heartbeat(s, run_id, worker, settings.worker_lease_s):
                return "lease_lost"
            if step.state == "completed":
                continue
            if step.state == "dispatching" and not step.idempotent:
                _save_step(
                    s,
                    step,
                    state="outcome_unknown",
                    finished_at=utcnow(),
                    error="in flight when the previous worker stopped; not idempotent, so not sent again",
                )
                return stop(
                    "outcome_unknown",
                    "step.outcome_unknown",
                    f"step {step.step_key} may or may not have run on {step.device_key}; a person must check "
                    "the instrument before running again",
                )
            reason = safety_check(env, settings, adapter, step.device_key)
            if reason:
                _save_step(s, step, state="refused", error=reason, finished_at=utcnow())
                return stop("failed", "safety.not_simulated", reason)
            _save_step(
                s, step, state="dispatching", dispatches=step.dispatches + 1, started_at=step.started_at or utcnow()
            )
            payload = dict(step.input)
            if step.idempotent:
                payload["request_id"] = step.request_id
            try:
                inv = adapter.invoke_action(
                    step.device_key, step.action, payload, timeout_s=settings.workflow_step_timeout_s
                )
            except AdapterError as e:
                # Unknown whether the command arrived. The step stays `dispatching`; the next attempt decides.
                if run.attempts >= run.max_attempts:
                    return stop("outcome_unknown" if not step.idempotent else "failed", "device.unreachable", str(e))
                service.requeue(s, run_id, worker, {"code": "device.unreachable", "message": str(e)})
                return "requeued"
            if inv.status == "completed":
                _save_step(
                    s,
                    step,
                    state="completed",
                    output=inv.output,
                    invocation_id=inv.invocation_id,
                    finished_at=utcnow(),
                    error=None,
                )
                continue
            if inv.status == "timeout":
                _save_step(
                    s,
                    step,
                    state="outcome_unknown",
                    invocation_id=inv.invocation_id,
                    finished_at=utcnow(),
                    error=f"no answer within {settings.workflow_step_timeout_s:g} s; it may still be running",
                )
                return stop("outcome_unknown", "step.timeout", f"step {step.step_key} did not finish in time")
            state = "refused" if not inv.accepted else "failed"
            _save_step(
                s,
                step,
                state=state,
                output=inv.output,
                invocation_id=inv.invocation_id,
                finished_at=utcnow(),
                error=inv.error or inv.status,
            )
            claim_report: dict[str, Any] | None = None
            if wf.verification and step.step_key == wf.verification.claim_step:
                claim_report = {"value": "failed", "step": step.step_key, "device": step.device_key, "error": inv.error}
            return stop(
                "failed",
                f"step.{state}",
                f"{step.device_key}.{step.action}: {inv.error or inv.status}",
                reported=claim_report,
            )

        # Every step completed. The verdict, if the workflow asks for one, is the engine's.
        values: dict[str, Any] = {"error": None}
        if wf.verification:
            contract, records, reported = build_verifier_input(run, env, steps, wf.verification)
            claim = next(x for x in steps if x.step_key == wf.verification.claim_step)
            values["reported"] = {
                "value": reported,
                "step": claim.step_key,
                "device": claim.device_key,
                "output": claim.output,
            }
            try:
                res = get_engine().verify_outcome(
                    contract, records, workdir=settings.work_path / "workflows" / str(run_id), name="run"
                )
            except EngineError as e:
                return stop("failed", e.code, e.message, reported=values["reported"])
            report = res.value.model_dump(mode="json")
            values["verification"] = {
                "verdict": res.value.verdict,
                "report": report,
                "contract": contract,
                "evidence": records,
            }
            values["outcome_class"] = outcome_class(reported, res.value.verdict.lower(), independent_evidence=True)
            values["provenance"] = {
                "engine": res.provenance.model_dump(mode="json"),
                "contract_sha256": _digest(contract),
                "evidence_sha256": _digest(records),
                "definition_sha256": _digest(run.definition),
                "environment": {"slug": env.slug, "kind": env.kind, "config_key": env.config_key},
                "evidence_class": "simulated",
            }
        service.finish(s, run_id, worker, "succeeded", **values)
        log.info("run %s succeeded (%s)", run_id, values.get("outcome_class"))
        return "succeeded"
