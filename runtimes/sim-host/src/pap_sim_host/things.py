"""The simulation host as a LabThings Thing (W3C WoT), so the platform's existing adapter discovers and drives it."""

from __future__ import annotations

from typing import Annotated, Any

import labthings_fastapi as lt
from labthings_fastapi.exceptions import InvocationError
from pydantic import Field

from . import CONTRACT, __version__
from .runner import Host, HostError

_HOST: Host | None = None


def configure(host: Host) -> None:
    global _HOST
    _HOST = host


def host() -> Host:
    if _HOST is None:
        raise RuntimeError("the simulation host is not configured")
    return _HOST


class ScenarioRefused(InvocationError):
    """A run the host refused or could not complete (code: message). Anticipated, so logged without a traceback."""


class SimulationHost(lt.Thing):
    """A simulation host (pap.simulation-host/1): runs the operator's scenarios of one simulator. Simulation only."""

    simulated: bool = lt.property(default=True, readonly=True)
    "Always true: this host runs simulations and has no path to physical hardware."

    contract: str = lt.property(default=CONTRACT, readonly=True)
    "The host contract this Thing implements."

    host_version: str = lt.property(default=__version__, readonly=True)
    "Version of this host software."

    @lt.property
    def simulator(self) -> dict[str, Any]:
        """The simulator behind this host: kind, name, version, what it is."""
        return host().catalog.simulator.model_dump()

    @lt.property
    def scenarios(self) -> list[dict[str, Any]]:
        """The operator's scenario catalog: parameter JSON Schemas, outputs, artifacts, maximum duration."""
        return [s.public() for s in host().catalog.scenarios]

    @lt.property
    def runs(self) -> list[dict[str, Any]]:
        """The most recent runs and their state."""
        return host().runs()

    @lt.action
    def run_scenario(
        self,
        scenario: Annotated[
            str, Field(pattern=r"^[a-z][a-z0-9_-]{0,63}$", description="A scenario id from `scenarios`.")
        ],
        scenario_version: Annotated[str, Field(min_length=1, max_length=32, description="The scenario's version.")],
        parameters: Annotated[
            dict[str, Any], Field(description="Parameters, validated against the scenario's schema.")
        ],
        request_id: Annotated[
            str,
            Field(min_length=8, max_length=64, description="Idempotency key: a repeated id returns the stored result."),
        ],
    ) -> dict[str, Any]:
        """Run one scenario to completion and return what it measured and left behind.

        Blocks until the scenario finishes (at most its catalog limit). A run that fails, times out or leaves no
        valid result is an error, never a made-up success.
        """
        try:
            return host().run(scenario, scenario_version, parameters, request_id)
        except HostError as e:
            raise ScenarioRefused(f"{e.code}: {e.message}") from None
