"""One evaluation, start to finish, with no database: mapping -> verifier -> events -> engine store -> comparisons.

Pure orchestration. Every judgement comes from the pinned engine: verdicts from ``outcome verify``, statistics and
the regression verdict from ``ops compare``. The only thing computed here is the per-episode outcome class, a
labelled cross-tabulation of the reported value and the verdict (ARCHITECTURE.md), which is not a statistic.
"""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from openmhs_bridge import Comparison, Engine, EngineError, EngineProvenance, conditions_of, digest

from ..contracts.episode import EpisodeContext, EvaluationConfig, OutcomeClass
from ..contracts.mapping import MappingSpec
from ..ingestion.mapping import ArtifactRejected, MappedEpisode, apply_mapping, verifier_input

VERDICT = {"SATISFIED": "satisfied", "VIOLATED": "violated", "UNKNOWN": "unknown"}
REPORTED_FAIL = {"failed", "aborted", "canceled", "timeout"}


class PipelineError(Exception):
    def __init__(self, code: str, message: str, detail: dict[str, Any] | None = None, transient: bool = False):
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message
        self.detail = detail or {}
        self.transient = transient

    def to_dict(self) -> dict[str, Any]:
        return {"code": self.code, "message": self.message, "detail": self.detail, "transient": self.transient}


@dataclass(frozen=True)
class ArtifactInput:
    sha256: str
    data: bytes
    name: str


@dataclass(frozen=True)
class ReleaseInput:
    label: str
    manifest: dict[str, Any]
    artifacts: tuple[ArtifactInput, ...]

    @property
    def digest(self) -> str:
        return digest(self.manifest)


@dataclass(frozen=True)
class PipelineInput:
    organization: str
    project: str
    baseline: ReleaseInput
    candidate: ReleaseInput
    mapping: MappingSpec
    mapping_ref: str
    config: EvaluationConfig


@dataclass
class EpisodeResult:
    mapped: MappedEpisode
    verdict: str | None = None  # satisfied | violated | unknown | None (no contract)
    reasons: list[str] = field(default_factory=list)
    report: dict[str, Any] | None = None
    outcome_class: OutcomeClass = "insufficient_evidence"


@dataclass
class PipelineOutput:
    episodes: list[EpisodeResult]
    validation: dict[str, Any]
    ingest: dict[str, Any]
    reported: Comparison
    reported_raw: str
    verified: Comparison | None
    verified_raw: str | None
    paired_raw: str | None
    incidents_raw: str
    events_path: Path
    store_path: Path
    provenance: EngineProvenance


def config_digest(config: EvaluationConfig) -> str:
    return digest(config.model_dump(mode="json", by_alias=True))


def outcome_class(reported: str, verdict: str | None, independent_evidence: bool) -> OutcomeClass:
    if verdict is None or not independent_evidence:
        return "insufficient_evidence" if reported == "unknown" else "reported_only"
    if verdict == "unknown":
        return "unknown"
    ok, failed = reported == "succeeded", reported in REPORTED_FAIL
    if verdict == "satisfied":
        return "supported_success" if ok else "contradiction" if failed else "verified_success"
    return "contradiction" if ok else "verified_failure"


def _events(inp: PipelineInput, release: ReleaseInput, results: list[EpisodeResult]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for r in results:
        ep = r.mapped.episode
        task_id = f"{release.label}/{ep.episode_key}"
        scope: dict[str, Any] = {"tenant": f"{inp.organization}/{inp.project}", "robot": ep.robot}
        if ep.site.available:
            scope["site"] = ep.site.value
        subject: dict[str, Any] = {"task_id": task_id, "task_type": ep.task_type}
        if ep.scenario.available:
            subject["scenario_id"] = ep.scenario.value
        time_end: dict[str, Any] = {"observed": ep.ended_at, "clock_domain": ep.clock_domain}
        if r.mapped.ended_uncertainty_ms is not None:
            time_end["uncertainty_ms"] = r.mapped.ended_uncertainty_ms
        base: dict[str, Any] = {
            "schema": "openmhs.event/0.1",
            "source": {"id": f"pap/{inp.mapping.name}", "kind": "import"},
            "scope": scope,
            "subject": subject,
            "deployment": {"manifest": release.digest},
            "provenance": "imported",
            "ext": {
                "pap": {
                    "artifact": ep.source.artifact_sha256,
                    "row": ep.source.row,
                    "evidence_class": ep.evidence_class,
                    "mapping": ep.mapping,
                }
            },
        }
        if ep.started_at.available:
            out.append(
                {
                    **base,
                    "event_id": f"{task_id}/task.started",
                    "type": "task.started",
                    "time": {**time_end, "observed": ep.started_at.value},
                }
            )
        ended_id = f"{task_id}/task.ended"
        out.append(
            {
                **base,
                "event_id": ended_id,
                "type": "task.ended",
                "time": time_end,
                "outcome": {"reported": {"value": ep.reported, "source": f"pap.mapping:{inp.mapping.name}"}},
            }
        )
        if r.verdict is not None and r.report is not None:
            assert inp.mapping.contract is not None
            out.append(
                {
                    **base,
                    "event_id": f"{task_id}/outcome.verified",
                    "type": "outcome.verified",
                    "time": time_end,
                    "provenance": "observed",
                    "relations": [{"type": "derived_from", "event_id": ended_id}],
                    "outcome": {
                        "verified": {
                            "value": r.verdict,
                            "contract": inp.mapping.contract.name,
                            "conditions": r.report["_conditions"],
                        }
                    },
                    "ext": {**base["ext"], "verifier": {"reasons": r.reasons}},
                }
            )
    return out


def run_pipeline(
    engine: Engine, inp: PipelineInput, workdir: Path, cancel: threading.Event | None = None
) -> PipelineOutput:
    if inp.baseline.label == inp.candidate.label:
        raise PipelineError("input.same_release", "baseline and candidate are the same release")
    workdir.mkdir(parents=True, exist_ok=True)
    validation: dict[str, Any] = {"artifacts": []}
    context = EpisodeContext(organization=inp.organization, project=inp.project, evaluation=config_digest(inp.config))
    per_release: dict[str, list[EpisodeResult]] = {}

    # 1. Mapping
    for release in (inp.baseline, inp.candidate):
        results: list[EpisodeResult] = []
        keys: dict[str, str] = {}
        for art in release.artifacts:
            try:
                mres = apply_mapping(
                    inp.mapping,
                    art.data,
                    artifact_sha256=art.sha256,
                    release=release.label,
                    mapping_ref=inp.mapping_ref,
                    context=context,
                )
            except ArtifactRejected as e:
                raise PipelineError(
                    "input.artifact_rejected", e.message, {"artifact": art.sha256, "name": art.name, "code": e.code}
                ) from e
            report = {"release": release.label, "artifact": art.sha256, "name": art.name, **mres.report()}
            kept = []
            for me in mres.episodes:
                k = me.episode.episode_key
                if k in keys:  # same episode in two artifacts of one release
                    report.setdefault("cross_artifact_duplicates", []).append({"row": me.episode.source.row, "key": k})
                    continue
                keys[k] = art.sha256
                kept.append(EpisodeResult(mapped=me))
            validation["artifacts"].append(report)
            results.extend(kept)
        per_release[release.label] = results

    # 2. Verification, one verifier run per episode
    vdir = workdir / "verifier"
    for label, results in per_release.items():
        for i, r in enumerate(results):
            vi = verifier_input(inp.mapping, r.mapped)
            if vi is not None:
                contract, evidence = vi
                res = engine.verify_outcome(contract, evidence, workdir=vdir, name=f"{label}-{i}", cancel=cancel)
                report = json.loads(res.raw)
                r.verdict = VERDICT[res.value.verdict]
                r.reasons = sorted({x.code for x in res.value.reasons})
                report["_conditions"] = conditions_of(contract, report)
                r.report = report
            r.outcome_class = outcome_class(r.mapped.episode.reported, r.verdict, bool(r.mapped.measured))

    task_types = {r.mapped.episode.task_type for rs in per_release.values() for r in rs}
    if inp.config.task_type not in task_types:
        raise PipelineError(
            "input.task_type", f"no episode has task type {inp.config.task_type!r}", {"found": sorted(task_types)}
        )

    # 3. Events, written once; the file is part of the evidence bundle
    records: list[dict[str, Any]] = [inp.baseline.manifest, inp.candidate.manifest]
    for release in (inp.baseline, inp.candidate):
        records.extend(_events(inp, release, per_release[release.label]))
    events_path = workdir / "events.jsonl"
    events_path.write_text("".join(json.dumps(r, sort_keys=True) + "\n" for r in records), encoding="utf-8")

    # 4. Engine store for this job only
    store = workdir / "ops.sqlite"
    if store.exists():
        store.unlink()
    try:
        ingest = engine.ingest(store, [events_path], cancel=cancel)
    except EngineError as e:
        raise PipelineError(e.code, e.message, e.detail, e.transient) from e

    # 5. Comparisons: reported always, verified when the mapping has a contract, paired on request
    cfg = inp.config
    kw: dict[str, Any] = {
        "task_type": cfg.task_type,
        "a": inp.baseline.label,
        "b": inp.candidate.label,
        "min_known": cfg.min_known,
        "margin": cfg.margin,
        "per_attempt": cfg.per_attempt,
        "no_strata": not cfg.stratify_by_site,
        "expect_a": {inp.baseline.digest},
        "expect_b": {inp.candidate.digest},
        "cancel": cancel,
    }
    reported = engine.compare(store, verified=False, **kw)
    verified = engine.compare(store, verified=True, **kw) if inp.mapping.contract is not None else None
    paired = None
    if cfg.paired:
        paired = engine.compare(store, verified=inp.mapping.contract is not None, paired=True, **kw)
    incidents = engine.incidents(store, cancel=cancel)

    return PipelineOutput(
        episodes=[r for rs in per_release.values() for r in rs],
        validation=validation,
        ingest=json.loads(ingest.raw),
        reported=reported.value,
        reported_raw=reported.raw,
        verified=verified.value if verified else None,
        verified_raw=verified.raw if verified else None,
        paired_raw=paired.raw if paired else None,
        incidents_raw=incidents.raw,
        events_path=events_path,
        store_path=store,
        provenance=reported.provenance,
    )
