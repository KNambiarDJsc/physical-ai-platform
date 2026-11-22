"""The tools. Each has a typed input model (its JSON Schema is what the assistant sees), runs as the caller through
PlatformClient, and is either read-only or one of two writes that only record something for a person to decide:
`propose_experiment` (a proposal to run an existing workflow) and `request_experiment_run` (a request to run one exact
experiment version). There is deliberately no tool to approve, to create or edit a workflow or an experiment, to start
a run, or to command a device: an engineer approves, and only simulated environments ever run."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from .client import PlatformClient
from .investigate import investigate
from .twin import explain_event

SLUG = r"^[a-z0-9][a-z0-9-]{0,62}$"
READ_ONLY = (
    "list_workspaces",
    "list_environments",
    "list_devices",
    "read_observation",
    "observation_health",
    "list_workflows",
    "list_workflow_runs",
    "get_workflow_run",
    "investigate_run",
    "list_evaluations",
    "get_comparison",
    "list_experiment_proposals",
    "list_recordings",
    "get_recording",
    "explain_recording_event",
    "list_simulation_environments",
    "list_experiments",
    "get_experiment_run",
    "list_release_verdicts",
)
WRITES = ("propose_experiment", "request_experiment_run")
ALLOWLIST = frozenset(READ_ONLY + WRITES)


class Org(BaseModel):
    org: str = Field(pattern=SLUG, description="Workspace (organization) slug.")


class NoInput(BaseModel):
    pass


class ReadObservation(Org):
    device_id: UUID = Field(description="Device id from list_devices.")
    property: str = Field(pattern=r"^[A-Za-z0-9_.-]{1,128}$", description="A readable property of that device.")


class RunsIn(Org):
    workflow: str | None = Field(default=None, pattern=SLUG, description="Only runs of this workflow.")


class RunIn(Org):
    run_id: UUID = Field(description="Workflow run id.")


class ProjectIn(Org):
    project: str = Field(pattern=SLUG, description="Project slug.")


class ComparisonIn(ProjectIn):
    evaluation_id: UUID = Field(description="Evaluation id from list_evaluations.")


class RecordingIn(ProjectIn):
    recording_id: UUID = Field(description="Recording id from list_recordings.")


class EventIn(RecordingIn):
    event_id: str = Field(pattern=r"^ev-[0-9]{1,4}$", description="An event id from get_recording, e.g. ev-3.")


class ProposalsIn(Org):
    state: str | None = Field(default=None, pattern=r"^(proposed|approved|rejected)$")


class ProposeIn(Org):
    workflow: str = Field(
        pattern=SLUG, description="An EXISTING workflow in this workspace. A proposal cannot change it."
    )
    rationale: str = Field(min_length=10, max_length=2000, description="Why run it, in plain words.")
    evidence_ids: list[str] = Field(
        default_factory=list,
        max_length=20,
        description="Ids of the evidence the rationale rests on, e.g. run:<id>, step:<id>/<n>.",
    )


class ExperimentIn(Org):
    experiment: str = Field(pattern=SLUG, description="Experiment slug from list_experiments.")


class ExperimentRunIn(Org):
    request_id: UUID = Field(description="A run (request) id from list_experiments.")


class RequestRunIn(ExperimentIn):
    version: int = Field(ge=1, description="The exact version to run. Approval applies to this version only.")
    rationale: str = Field(min_length=10, max_length=2000, description="Why run it, in plain words, for the approver.")


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    model: type[BaseModel]
    fn: Callable[[PlatformClient, Any], Any]

    @property
    def writes(self) -> bool:
        return self.name in WRITES


def _o(a: Org) -> str:
    return f"/api/v1/orgs/{a.org}"


def _devices(c: PlatformClient, a: Org) -> Any:
    out = []
    for d in c.get(f"{_o(a)}/devices"):
        caps = d["capabilities"]
        out.append(
            {
                "id": d["id"],
                "key": d["key"],
                "title": d["title"],
                "environment": d["environment"],
                "environment_kind": d["environment_kind"],
                "present": d["present"],
                "properties": [x["name"] for x in caps if x["kind"] == "property"],
                "actions": [x["name"] for x in caps if x["kind"] == "action"],
            }
        )
    return out


def _health(c: PlatformClient, a: Org) -> Any:
    """For every read-only observer device (a `summary` property, no action): its summary and its expected topics."""
    out = []
    for d in c.get(f"{_o(a)}/devices"):
        names = {x["name"] for x in d["capabilities"] if x["kind"] == "property"}
        if "summary" not in names or any(x["kind"] == "action" for x in d["capabilities"]) or not d["present"]:
            continue
        base = f"{_o(a)}/devices/{d['id']}/properties"
        entry: dict[str, Any] = {
            "device_id": d["id"],
            "environment": d["environment"],
            "summary": c.get(f"{base}/summary")["value"],
        }
        if "expected_topics" in names:
            entry["expected_topics"] = c.get(f"{base}/expected_topics")["value"]
        out.append(entry)
    return out


def _rec(a: ProjectIn) -> str:
    return f"{_o(a)}/projects/{a.project}/twin/recordings"


def _recording(c: PlatformClient, a: RecordingIn) -> Any:
    """The recording without its bulky summary: events, counts, model and the linked episode with the verdict."""
    d = c.get(f"{_rec(a)}/{a.recording_id}")
    return {k: v for k, v in d.items() if k not in ("summary",)}


def _explain(c: PlatformClient, a: EventIn) -> Any:
    rec = c.get(f"{_rec(a)}/{a.recording_id}")
    episode = None
    if rec.get("episode"):
        link = rec["episode"]
        episode = c.get(f"{_o(a)}/projects/{a.project}/evaluations/{link['evaluation_id']}/episodes/{link['id']}")
    run = None
    if episode is None and rec.get("run"):
        run = c.get(f"{_o(a)}/workflow-runs/{rec['run']['id']}")
    try:
        return explain_event(rec, a.event_id, episode, run)
    except LookupError as e:
        from .client import ToolError

        raise ToolError(str(e)) from None


def _experiments(c: PlatformClient, a: Org) -> Any:
    """Experiments with their versions (scenario, setups, contract) and runs, without the bulky host listing."""
    out = []
    for e in c.get(f"{_o(a)}/experiments"):
        out.append(
            {
                "slug": e["slug"],
                "name": e["name"],
                "description": e["description"],
                "versions": [
                    {k: v[k] for k in ("number", "spec", "spec_sha256", "environment", "created_by", "created_at")}
                    for v in e["versions"]
                ],
                "runs": e["requests"],
            }
        )
    return out


def _request_run(c: PlatformClient, a: RequestRunIn) -> Any:
    return c.post(f"{_o(a)}/experiments/{a.experiment}/versions/{a.version}/requests", {"note": a.rationale})


def _propose(c: PlatformClient, a: ProposeIn) -> Any:
    return c.post(
        f"{_o(a)}/experiment-proposals",
        {"workflow": a.workflow, "rationale": a.rationale, "evidence_ids": a.evidence_ids},
    )


TOOLS: dict[str, Tool] = {
    t.name: t
    for t in [
        Tool(
            "list_workspaces",
            "List the workspaces you belong to, with your role in each.",
            NoInput,
            lambda c, a: c.get("/api/v1/me")["organizations"],
        ),
        Tool(
            "list_environments",
            "List the environments connected to a workspace (kind simulated or physical).",
            Org,
            lambda c, a: c.get(f"{_o(a)}/environments"),
        ),
        Tool("list_devices", "List discovered devices with their readable properties and actions.", Org, _devices),
        Tool(
            "read_observation",
            "Read one property of a device live (read-only observation).",
            ReadObservation,
            lambda c, a: c.get(f"{_o(a)}/devices/{a.device_id}/properties/{a.property}"),
        ),
        Tool(
            "observation_health",
            "Health of every read-only observer in a workspace (ROS graphs): topic freshness counts and "
            "required topics that are missing or stale.",
            Org,
            _health,
        ),
        Tool(
            "list_workflows",
            "List the workflows in a workspace.",
            Org,
            lambda c, a: [
                {k: w[k] for k in ("slug", "name", "environment", "template", "definition_sha256")}
                for w in c.get(f"{_o(a)}/workflows")
            ],
        ),
        Tool(
            "list_workflow_runs",
            "List recent workflow runs with their reported and engine-verified outcomes.",
            RunsIn,
            lambda c, a: c.get(f"{_o(a)}/workflow-runs", workflow=a.workflow),
        ),
        Tool(
            "get_workflow_run",
            "One run in full: steps, the instrument's report, the engine's verdict and provenance.",
            RunIn,
            lambda c, a: c.get(f"{_o(a)}/workflow-runs/{a.run_id}"),
        ),
        Tool(
            "investigate_run",
            "Rule-based findings for a run, each citing stored evidence ids, plus suggested experiments "
            "(suggestions are not proposals).",
            RunIn,
            lambda c, a: investigate(c.get(f"{_o(a)}/workflow-runs/{a.run_id}")),
        ),
        Tool(
            "list_evaluations",
            "List release-comparison evaluations of a project.",
            ProjectIn,
            lambda c, a: c.get(f"{_o(a)}/projects/{a.project}/evaluations"),
        ),
        Tool(
            "get_comparison",
            "The engine's comparison (reported and verified) of one evaluation.",
            ComparisonIn,
            lambda c, a: c.get(f"{_o(a)}/projects/{a.project}/evaluations/{a.evaluation_id}/comparison"),
        ),
        Tool(
            "list_recordings",
            "List the MCAP recordings in a project: label, clock, duration, robot model and the linked episode with "
            "the engine's verdict.",
            ProjectIn,
            lambda c, a: c.get(_rec(a)),
        ),
        Tool(
            "get_recording",
            "One recording: run identity, message counts, the evidence events found in it (each with its rule and "
            "source topics) and the linked episode's engine verdict.",
            RecordingIn,
            _recording,
        ),
        Tool(
            "explain_recording_event",
            "Explain one event of a recording by citing the stored evidence behind it: the event's rule, the run "
            "identity, data-quality events, and the engine's verdict and contract for the linked episode. States what "
            "is not known. Rule-based, no language model.",
            EventIn,
            _explain,
        ),
        Tool(
            "list_experiment_proposals",
            "List experiment proposals and their state.",
            ProposalsIn,
            lambda c, a: c.get(f"{_o(a)}/experiment-proposals", state=a.state),
        ),
        Tool(
            "list_simulation_environments",
            "Simulated environments with a simulation host, what each host lists now (simulator, scenarios with their "
            "parameter schemas, measurements and artifacts) and whether it is reachable.",
            Org,
            lambda c, a: c.get(f"{_o(a)}/simulation-environments"),
        ),
        Tool(
            "list_experiments",
            "Experiments: their immutable versions (scenario, setups, contract, checksum) and their runs with states.",
            Org,
            _experiments,
        ),
        Tool(
            "get_experiment_run",
            "One experiment run: every trial's measurements, the engine's verdict per trial, captured artifacts with "
            "digests, the recording ids for the Digital twin, and raw values and verdict counts per setup.",
            ExperimentRunIn,
            lambda c, a: c.get(f"{_o(a)}/experiment-requests/{a.request_id}"),
        ),
        Tool(
            "list_release_verdicts",
            "The engine's release verdicts for an experiment's setups (regression, improvement, no change or "
            "insufficient evidence) with its reasons. A violated trial is not a release regression.",
            ExperimentIn,
            lambda c, a: c.get(f"{_o(a)}/experiments/{a.experiment}/release-evaluations"),
        ),
        Tool(
            "request_experiment_run",
            "Record a REQUEST to run one exact experiment version. Nothing runs: an engineer other than the requester "
            "must approve that exact version, and only simulated environments can run.",
            RequestRunIn,
            _request_run,
        ),
        Tool(
            "propose_experiment",
            "Record a PROPOSAL to run an existing workflow. Nothing runs: an engineer must approve it, and "
            "only simulated environments can be approved.",
            ProposeIn,
            _propose,
        ),
    ]
}
assert set(TOOLS) == ALLOWLIST
