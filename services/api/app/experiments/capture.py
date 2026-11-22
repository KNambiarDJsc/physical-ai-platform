"""After a trial's run finishes, the worker fetches the artifacts the spec asked for from the host, checks each against
the digest the host reported, stores them content-addressed, and registers an MCAP as a Digital Twin recording linked
to the run (SIM-004).

Only the spec's listed artifacts are ever fetched. Bytes that do not match the reported digest are not stored and the
trial says so. Nothing is held in memory beyond one chunk: downloads stream to a spooled file, are hashed on the way,
and are stored and decoded from that file.
"""

from __future__ import annotations

import json
import logging
import tempfile
import uuid
from pathlib import PurePosixPath
from typing import Any

from pap_device_sdk import AdapterError, WotHttpAdapter
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import audit
from ..config import Settings, get_settings
from ..db import session_factory
from ..evidence.storage import Storage, get_storage
from ..hardware.models import Environment
from ..hardware.service import EnvironmentUnavailable, adapter_for
from ..twin.ingest import MCAP_MAGIC, SPOOL_IN_MEMORY, IngestError, Spooled, store_recording
from ..workflows.models import WorkflowRun, WorkflowStep
from .host import HOST, SpecError, check_model
from .models import Experiment, ExperimentRequest, ExperimentTrial, ExperimentVersion
from .service import FINAL
from .spec import ExperimentSpec

log = logging.getLogger("pap.experiments")
MAX_ARTIFACT_BYTES = 96 * 1024 * 1024
MAX_SUMMARY_BYTES = 2_000_000


class CaptureError(Exception):
    pass


def _download(adapter: WotHttpAdapter, run_id: str, entry: dict[str, Any], limit: int) -> Spooled:
    """Fetch one listed artifact into a spooled file and check it against what the host reported."""
    name = entry["name"]
    reported = str(entry.get("sha256") or "").removeprefix("sha256:")
    if int(entry.get("size_bytes") or 0) > limit:
        raise CaptureError(f"{name}: the host reports {entry.get('size_bytes')} bytes, above the limit of {limit}")
    f = tempfile.SpooledTemporaryFile(max_size=SPOOL_IN_MEMORY)  # noqa: SIM115 - closed by the caller
    try:
        digest, size, headers = adapter.download(HOST, f"runs/{run_id}/artifacts/{name}", f, limit)
    except AdapterError as e:
        f.close()
        raise CaptureError(f"{name}: {e}") from None
    header = headers.get("x-artifact-sha256", "").removeprefix("sha256:")
    if digest != reported or size != int(entry.get("size_bytes", -1)) or (header and header != digest):
        f.close()
        raise CaptureError(
            f"{name}: the downloaded bytes (sha256 {digest[:12]}…, {size} bytes) do not match what the host reported "
            f"(sha256 {reported[:12]}…, {entry.get('size_bytes')} bytes); not stored"
        )
    f.seek(0)
    return Spooled(f, "sha256:" + digest, size)


def _summary_json(spooled: Spooled) -> dict[str, Any]:
    if spooled.size > MAX_SUMMARY_BYTES:
        raise CaptureError("the bag summary is larger than 2 MB")
    try:
        doc = json.loads(spooled.file.read().decode("utf-8"))
    except ValueError:
        raise CaptureError("the bag summary artifact is not JSON") from None
    spooled.file.seek(0)
    if not isinstance(doc, dict):
        raise CaptureError("the bag summary artifact is not a JSON object")
    return doc


def _capture(session: Session, settings: Settings, storage: Storage, t: ExperimentTrial) -> None:
    run = session.get(WorkflowRun, t.run_id)
    req = session.get(ExperimentRequest, t.request_id)
    assert run is not None and req is not None
    v = session.get(ExperimentVersion, req.version_id)
    assert v is not None
    spec = ExperimentSpec.model_validate(v.spec)
    if run.state != "succeeded":
        t.capture_state = "none"
        t.capture_error = f"the trial {run.state.replace('_', ' ')}: the host left nothing to capture"
        return
    step = session.scalar(select(WorkflowStep).where(WorkflowStep.run_id == run.id).order_by(WorkflowStep.position))
    out = step.output if step is not None and isinstance(step.output, dict) else {}
    host_run, listed = str(out.get("run_id") or ""), {a["name"]: a for a in out.get("artifacts") or []}
    env = session.get(Environment, run.environment_id)
    assert env is not None
    try:
        adapter = adapter_for(env, settings)
    except EnvironmentUnavailable:
        raise CaptureError("the operator no longer offers this environment") from None
    if not isinstance(adapter, WotHttpAdapter):
        raise CaptureError("this environment's adapter cannot download artifacts")
    if not host_run:
        raise CaptureError("the host's answer names no run, so no artifact can be fetched")

    records: list[dict[str, Any]] = []
    recording_spool: Spooled | None = None
    summary_doc: dict[str, Any] | None = None
    errors: list[str] = []
    try:
        for name in spec.observations.artifacts:  # only what the spec lists, never the host's whole run directory
            entry = listed.get(name)
            if entry is None:
                errors.append(f"{name}: the host's result does not list this artifact")
                continue
            try:
                spooled = _download(adapter, host_run, entry, MAX_ARTIFACT_BYTES)
            except CaptureError as e:
                errors.append(str(e))
                records.append({"name": name, "state": "rejected", "error": str(e)})
                continue
            rec = {
                "name": name,
                "filename": PurePosixPath(str(entry.get("path") or name)).name,
                "media_type": entry.get("media_type"),
                "sha256": spooled.sha256,
                "size_bytes": spooled.size,
                "state": "stored",
            }
            if name == spec.observations.recording:
                head = spooled.file.read(len(MCAP_MAGIC))
                spooled.file.seek(0)
                if head != MCAP_MAGIC:
                    errors.append(f"{name}: not an MCAP file")
                    rec["state"] = "rejected"
                    rec["error"] = "not an MCAP file"
                    spooled.close()
                else:
                    recording_spool = spooled
            else:
                try:
                    if name == spec.observations.summary:
                        summary_doc = _summary_json(spooled)
                    stored = storage.put(spooled.chunks(), MAX_ARTIFACT_BYTES)
                    rec["storage_key"] = stored.key
                except CaptureError as e:
                    errors.append(f"{name}: {e}")
                    rec["state"], rec["error"] = "rejected", str(e)
                finally:
                    spooled.close()
            records.append(rec)

        if recording_spool is not None and spec.observations.recording:
            rec = next(r for r in records if r["name"] == spec.observations.recording)
            try:
                mv = check_model(session, run.organization_id, spec)
                assert mv is not None
                exp = session.get(Experiment, v.experiment_id)
                label = (
                    f"{exp.name if exp else 'experiment'} v{v.number} · {t.arm}"
                    + (f" · seed {t.seed}" if t.seed is not None else "")
                    + f" · trial {t.repetition + 1}"
                )
                filename = rec["filename"] if str(rec["filename"]).lower().endswith(".mcap") else "recording.mcap"
                recording, _ = store_recording(
                    session,
                    storage,
                    project_id=mv.project_id,
                    spooled=recording_spool,
                    label=label,
                    filename=filename,
                    max_bytes=MAX_ARTIFACT_BYTES,
                    summary=summary_doc,
                    identity=out.get("identity"),
                    model_version_id=mv.id,
                    episode_id=None,
                    workflow_run_id=run.id,
                    created_by=run.submitted_by,
                )
                rec["storage_key"] = recording.storage_key
                t.recording_id = recording.id
            except (SpecError, IngestError) as e:
                msg = e.message
                errors.append(f"{rec['name']}: not registered as a recording: {msg}")
                rec["state"], rec["error"] = "rejected", f"not registered as a recording: {msg}"
    finally:
        if recording_spool is not None:
            recording_spool.close()

    t.artifacts = records
    t.capture_state = "failed" if errors else "stored"
    t.capture_error = "; ".join(errors) or None


def capture_trial(trial_id: uuid.UUID) -> str | None:
    """Capture one finished trial. Returns the new capture state, or None when it is not ready or already done."""
    settings, storage = get_settings(), get_storage()
    with session_factory()() as s:
        t = s.scalar(
            select(ExperimentTrial)
            .where(ExperimentTrial.id == trial_id, ExperimentTrial.capture_state == "pending")
            .with_for_update(skip_locked=True)  # another worker holding it is capturing it
        )
        if t is None:
            return None
        run = s.get(WorkflowRun, t.run_id)
        if run is None or run.state not in FINAL:
            return None
        try:
            _capture(s, settings, storage, t)
        except CaptureError as e:
            t.capture_state, t.capture_error = "failed", str(e)
        except Exception as e:
            log.exception("capture of trial %s failed", trial_id)
            s.rollback()
            t = s.get(ExperimentTrial, trial_id)
            assert t is not None
            t.capture_state, t.capture_error = "failed", f"unexpected {type(e).__name__}: {e}"
        audit.record(
            s,
            actor="worker",
            action="experiment.capture",
            resource=f"experiment_trial:{t.id}",
            decision="allow",
            organization_id=t.organization_id,
            detail={
                "state": t.capture_state,
                "artifacts": [a["name"] for a in t.artifacts if a.get("state") == "stored"],
            },
        )
        s.commit()
        return t.capture_state


def capture_ready(limit: int = 5) -> int:
    """Capture trials whose runs have finished (the worker calls this after each run and when idle)."""
    with session_factory()() as s:
        ids = list(
            s.scalars(
                select(ExperimentTrial.id)
                .join(WorkflowRun, WorkflowRun.id == ExperimentTrial.run_id)
                .where(
                    ExperimentTrial.capture_state == "pending",
                    WorkflowRun.state.in_(FINAL),
                )
                .order_by(ExperimentTrial.created_at)
                .limit(limit)
            )
        )
    return sum(1 for i in ids if capture_trial(i) is not None)
