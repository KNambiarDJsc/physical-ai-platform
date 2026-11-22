"""What a simulation host lists now, and whether a spec still matches it. Reads only; never commands anything."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError
from pap_device_sdk import AdapterError
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import Settings
from ..hardware.models import Device, Environment
from ..hardware.service import EnvironmentUnavailable, adapter_for, catalog_entry
from ..projects.models import Project
from ..twin.models import RobotModel, RobotModelVersion
from .spec import ExperimentSpec, checksum

HOST = "simulation-host"
CONTRACT = "pap.simulation-host/1"


class SpecError(Exception):
    def __init__(self, status: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status, self.code, self.message = status, code, message


@dataclass
class Listing:
    contract: str
    simulator: dict[str, Any]
    scenarios: list[dict[str, Any]]

    def scenario(self, sid: str, version: str) -> dict[str, Any] | None:
        return next((s for s in self.scenarios if s.get("id") == sid and s.get("version") == version), None)


def scenario_digest(s: dict[str, Any]) -> str:
    return checksum(s)


def simulator_ref(sim: dict[str, Any]) -> dict[str, Any]:
    return {"kind": sim.get("kind"), "name": sim.get("name"), "version": sim.get("version")}


def host_device(session: Session, env: Environment) -> Device:
    d = session.scalar(select(Device).where(Device.environment_id == env.id, Device.key == HOST))
    if d is None or not d.present:
        raise SpecError(
            422, "experiment.no_host", f"{env.slug} has no discovered {HOST}: run discovery on the environment first"
        )
    return d


def read_listing(session: Session, env: Environment, settings: Settings) -> Listing:
    """Ask the environment's simulation host for its contract, simulator and scenario catalog."""
    cfg = catalog_entry(settings, env.config_key)
    if env.kind != "simulated" or cfg is None or cfg.kind != "simulated":
        raise SpecError(422, "experiment.not_simulated", f"{env.slug} is not a simulated environment (D-026)")
    host_device(session, env)
    try:
        adapter = adapter_for(env, settings)
        contract = adapter.read_property(HOST, "contract")
        simulated = adapter.read_property(HOST, "simulated")
        simulator = adapter.read_property(HOST, "simulator")
        scenarios = adapter.read_property(HOST, "scenarios")
    except EnvironmentUnavailable:
        raise SpecError(
            409, "experiment.environment_unavailable", "the operator no longer offers this environment"
        ) from None
    except AdapterError as e:
        raise SpecError(503, "experiment.host_unreachable", f"the simulation host did not answer: {e}") from None
    if contract != CONTRACT:
        raise SpecError(422, "experiment.host_contract", f"{HOST} implements {contract!r}, not {CONTRACT}")
    if simulated is not True:
        raise SpecError(422, "experiment.not_simulated", f"{HOST} does not report simulated=true")
    if not isinstance(simulator, dict) or not isinstance(scenarios, list):
        raise SpecError(502, "experiment.host_listing", "the host's simulator or scenarios property is malformed")
    return Listing(contract, simulator, [s for s in scenarios if isinstance(s, dict)])


def trial_parameters(spec: ExperimentSpec, arm_key: str, seed: int | None) -> dict[str, Any]:
    arm = next(a for a in spec.arms if a.key == arm_key)
    p = {**spec.initial_conditions, **arm.parameters}
    if seed is not None:
        p["seed"] = seed
    return p


def _schema_errors(schema: dict[str, Any], value: dict[str, Any]) -> list[str]:
    try:
        v = Draft202012Validator(schema)
    except SchemaError as e:
        return [f"the scenario's parameter schema is invalid: {e.message}"]
    return [
        (f"{'.'.join(map(str, e.absolute_path))}: " if e.absolute_path else "") + e.message
        for e in sorted(v.iter_errors(value), key=lambda e: list(map(str, e.absolute_path)))
    ]


def check_model(session: Session, org_id: Any, spec: ExperimentSpec) -> RobotModelVersion | None:
    if spec.model is None:
        return None
    mv = session.scalar(
        select(RobotModelVersion)
        .join(RobotModel, RobotModel.id == RobotModelVersion.model_id)
        .join(Project, Project.id == RobotModel.project_id)
        .where(
            Project.organization_id == org_id,
            Project.slug == spec.model.project,
            RobotModel.slug == spec.model.model,
            RobotModelVersion.number == spec.model.version,
        )
    )
    if mv is None:
        m = spec.model
        raise SpecError(
            422, "experiment.model", f"no model version {m.project}/{m.model} v{m.version} in this workspace"
        )
    return mv


def validate(spec: ExperimentSpec, listing: Listing) -> dict[str, Any]:
    """Every check a version must pass against the host's current listing. Returns the listed scenario."""
    host_sim = simulator_ref(listing.simulator)
    if spec.simulator.model_dump() != host_sim:
        raise SpecError(
            409,
            "experiment.simulator_changed",
            f"the spec names simulator {spec.simulator.model_dump()}, the host reports {host_sim}",
        )
    sc = listing.scenario(spec.scenario.id, spec.scenario.version)
    if sc is None:
        raise SpecError(
            422, "experiment.unknown_scenario", f"the host does not list {spec.scenario.id} v{spec.scenario.version}"
        )
    if scenario_digest(sc) != spec.scenario.definition_sha256:
        raise SpecError(
            409,
            "experiment.scenario_changed",
            f"{spec.scenario.id} v{spec.scenario.version} is listed with different content than the spec pinned "
            "(the operator changed it without a new version)",
        )
    schema = sc.get("parameters_schema") or {}
    if spec.seeds:
        seed_t = ((schema.get("properties") or {}).get("seed") or {}).get("type")
        if seed_t != "integer":
            raise SpecError(422, "experiment.seeds", f"{spec.scenario.id} has no integer `seed` parameter")
    problems: list[str] = []
    for a in spec.arms:
        seeds: list[int | None] = [*spec.seeds] if spec.seeds else [None]
        for seed in seeds:
            for msg in _schema_errors(schema, trial_parameters(spec, a.key, seed)):
                problems.append(f"arm {a.key}: {msg}")
    if problems:
        raise SpecError(422, "experiment.parameters", "; ".join(dict.fromkeys(problems)))
    outputs = {o["name"]: o for o in sc.get("outputs", [])}
    arts = {a["name"]: a for a in sc.get("artifacts", [])}
    unknown = sorted(set(spec.observations.measurements) - set(outputs))
    if unknown:
        raise SpecError(422, "experiment.observations", f"the scenario does not output {unknown}")
    unknown = sorted(set(spec.observations.artifacts) - set(arts))
    if unknown:
        raise SpecError(422, "experiment.observations", f"the scenario does not leave {unknown}")
    if spec.observations.recording and "mcap" not in str(arts[spec.observations.recording].get("media_type")):
        raise SpecError(422, "experiment.observations", f"{spec.observations.recording} is not an MCAP artifact")
    for c in spec.contract.conditions:
        if c.measurement not in outputs:
            raise SpecError(422, "experiment.contract", f"condition {c.name!r} uses {c.measurement!r}, not an output")
    if spec.trials > spec.limits.max_trials:
        raise SpecError(422, "experiment.limits", f"{spec.trials} trials exceed the limit of {spec.limits.max_trials}")
    budget = spec.trials * float(sc.get("max_duration_s") or 0)
    if budget > spec.limits.max_wall_time_s:
        raise SpecError(
            422,
            "experiment.limits",
            f"{spec.trials} trials of up to {sc.get('max_duration_s')} s each may take {budget:g} s, above the "
            f"limit of {spec.limits.max_wall_time_s} s",
        )
    return sc
