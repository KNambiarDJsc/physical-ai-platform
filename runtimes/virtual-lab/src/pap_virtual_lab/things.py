"""The instruments, as LabThings Things. Each one says it is simulated, in its description and in a property."""

from __future__ import annotations

import time
from typing import Annotated

import labthings_fastapi as lt
from pydantic import Field

from .bench import BENCH, FAULTS

STEP_S = 0.3  # simulated mechanical time, so a run has observable duration


class SyringePump(lt.Thing):
    """Simulated syringe pump (virtual laboratory). Open loop: it reports the volume it was commanded."""

    simulated: bool = lt.property(default=True, readonly=True)
    "Always true: this instrument exists only in the virtual laboratory."

    max_volume_ul: float = lt.property(default=1000.0, readonly=True)
    "Largest volume one dispense command accepts, in µL."

    @lt.property
    def reservoir_ul(self) -> float:
        """Liquid left in the reservoir, in µL, as the simulation tracks it."""
        return round(BENCH.reservoir_ul, 3)

    @lt.action
    def dispense(
        self,
        volume_ul: Annotated[float, Field(gt=0, le=1000, description="Volume to dispense, in µL.")],
        request_id: Annotated[
            str,
            Field(min_length=8, max_length=64, description="Idempotency key: a repeated id dispenses nothing."),
        ],
    ) -> dict[str, float | str]:
        """Dispense water into the vessel.

        Returns what the pump reports: the volume it was commanded. A repeated request id dispenses nothing.
        """
        time.sleep(STEP_S)
        return BENCH.dispense(volume_ul, request_id)


class Balance(lt.Thing):
    """Simulated analytical balance (virtual laboratory), readability 0.1 mg. Measures the vessel independently."""

    simulated: bool = lt.property(default=True, readonly=True)
    "Always true: this instrument exists only in the virtual laboratory."

    readability_g: float = lt.property(default=0.0001, readonly=True)
    "Smallest mass step the balance displays, in g."

    @lt.property
    def mass_g(self) -> float:
        """Current net reading in g (gross minus tare), with the balance's repeatability noise."""
        return BENCH.read_mass_g()

    @lt.action
    def tare(self) -> None:
        """Zero the balance.

        Zeroes with the vessel and its current contents on it.
        """
        time.sleep(STEP_S)
        BENCH.tare()

    @lt.action
    def weigh(self) -> dict[str, float]:
        """Take one stable reading.

        Returns the net mass in g.
        """
        time.sleep(STEP_S)
        return {"mass_g": BENCH.read_mass_g()}


class SimulationControl(lt.Thing):
    """Controls of the virtual laboratory itself: reset and fault injection. Not an instrument."""

    simulated: bool = lt.property(default=True, readonly=True)
    "Always true."

    @lt.property
    def fault(self) -> str:
        """The fault currently injected into the pump's line."""
        return BENCH.fault

    @lt.property
    def available_faults(self) -> dict[str, str]:
        """Faults that can be injected, with what each one does physically."""
        return {k: v[1] for k, v in FAULTS.items()}

    @lt.action
    def set_fault(self, fault: Annotated[str, Field(description="One of available_faults.")]) -> str:
        """Inject a fault into the pump's line.

        Use "none" to clear it. Returns the fault now in effect.
        """
        if fault not in FAULTS:
            raise ValueError(f"unknown fault {fault!r}; one of {sorted(FAULTS)}")
        BENCH.fault = fault
        return BENCH.fault

    @lt.action
    def reset(self) -> None:
        """Reset the virtual laboratory.

        Empties the vessel, refills the reservoir, clears tare and faults, restarts the noise sequence.
        """
        BENCH.reset()
