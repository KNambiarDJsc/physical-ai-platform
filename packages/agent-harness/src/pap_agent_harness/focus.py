"""Investigation contexts narrow the evidence tools available to one session."""

from __future__ import annotations

from enum import Enum


class Focus(str, Enum):
    general = "general"
    robotics = "robotics"
    laboratory = "laboratory"
    release = "release"


COMMON = {"list_experiments", "get_experiment_run", "list_release_verdicts", "list_experiment_proposals"}
DRAFT = {"request_experiment_run", "propose_experiment"}
TOOLS_BY_FOCUS = {
    Focus.robotics: COMMON
    | DRAFT
    | {
        "list_recordings",
        "get_recording",
        "explain_recording_event",
        "observation_health",
        "list_simulation_environments",
        "list_workflows",
        "get_workflow_run",
    },
    Focus.laboratory: COMMON
    | DRAFT
    | {
        "list_environments",
        "list_devices",
        "read_observation",
        "list_workflows",
        "list_workflow_runs",
        "get_workflow_run",
        "investigate_run",
    },
    Focus.release: COMMON | {"list_evaluations", "get_comparison"},
}
INSTRUCTIONS = {
    Focus.general: "",
    Focus.robotics: "Use the recording clock and source topics. Cite the selected event and trial contract.",
    Focus.laboratory: "Compare the instrument report with the independent observation, including units and tolerance.",
    Focus.release: "Use the stored comparison. Report the known counts, uncertainty, verdict and engine reasons.",
}
