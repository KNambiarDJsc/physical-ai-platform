"""The simulated physical state shared by the instruments on one bench.

A syringe pump dispenses water into a vessel that stands on an analytical balance. The pump is open loop: it
reports the volume it was commanded, whatever actually left the syringe. The balance measures the vessel
independently. Faults change what physically happens, never what the pump reports, which is exactly the gap
between a reported and a verified outcome.
"""

from __future__ import annotations

import os
import random
import threading
from dataclasses import dataclass, field

WATER_G_PER_UL = 0.0009982  # density of water at 20 °C, in g per µL
VESSEL_MASS_G = 12.3456  # empty vessel
BALANCE_RESOLUTION_G = 0.0001  # d = 0.1 mg
BALANCE_NOISE_SD_G = 0.00008  # repeatability of a 0.1 mg analytical balance
PUMP_CV = 0.004  # 0.4 % coefficient of variation of the delivered volume when healthy

FAULTS: dict[str, tuple[float, str]] = {
    "none": (1.0, "Healthy pump: delivers the commanded volume within its 0.4 % CV."),
    "partial_blockage": (0.62, "Partially blocked line: about 62 % of the commanded volume arrives."),
    "air_in_line": (0.9, "Air bubble in the line: about 90 % arrives."),
    "blocked": (0.0, "Fully blocked line: nothing arrives, the pump still reports success."),
}


@dataclass
class Bench:
    seed: int
    liquid_g: float = 0.0
    reservoir_ul: float = 10_000.0
    tare_g: float = 0.0
    fault: str = "none"
    dispensed: dict[str, dict[str, float | str]] = field(default_factory=dict)
    lock: threading.Lock = field(default_factory=threading.Lock)
    rng: random.Random = field(init=False)

    def __post_init__(self) -> None:
        self.rng = random.Random(self.seed)  # simulation noise, not cryptography

    def reset(self) -> None:
        with self.lock:
            self.liquid_g = 0.0
            self.reservoir_ul = 10_000.0
            self.tare_g = 0.0
            self.fault = "none"
            self.dispensed.clear()
            self.rng = random.Random(self.seed)

    def dispense(self, volume_ul: float, request_id: str) -> dict[str, float | str]:
        """Physically move liquid. Idempotent per request id: a repeated id changes nothing."""
        with self.lock:
            if request_id in self.dispensed:
                return {**self.dispensed[request_id], "repeated": "true"}
            efficiency, _ = FAULTS[self.fault]
            actual_ul = max(0.0, volume_ul * efficiency * self.rng.gauss(1.0, PUMP_CV)) if efficiency else 0.0
            actual_ul = min(actual_ul, self.reservoir_ul)
            self.reservoir_ul -= actual_ul
            self.liquid_g += actual_ul * WATER_G_PER_UL
            # What the pump knows: the volume it was asked for. It cannot see the line or the vessel.
            report: dict[str, float | str] = {"request_id": request_id, "reported_dispensed_ul": volume_ul}
            self.dispensed[request_id] = report
            return dict(report)

    def tare(self) -> None:
        with self.lock:
            self.tare_g = VESSEL_MASS_G + self.liquid_g

    def read_mass_g(self) -> float:
        with self.lock:
            gross = VESSEL_MASS_G + self.liquid_g + self.rng.gauss(0.0, BALANCE_NOISE_SD_G)
            return round(round((gross - self.tare_g) / BALANCE_RESOLUTION_G) * BALANCE_RESOLUTION_G, 4)


BENCH = Bench(seed=int(os.environ.get("PAP_VLAB_SEED", "7")))
