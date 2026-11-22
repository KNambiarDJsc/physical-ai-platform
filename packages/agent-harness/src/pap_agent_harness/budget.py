"""A hard spend cap per session. Usage comes from the model's own responses; the session stops as soon as a cap is
reached, before another model call is made."""

from __future__ import annotations

from dataclasses import dataclass


class BudgetExceeded(RuntimeError):
    pass


@dataclass
class Budget:
    max_tokens: int
    max_usd: float
    usd_per_m_input: float | None = None
    usd_per_m_output: float | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    calls: int = 0

    @property
    def usd(self) -> float | None:
        if self.usd_per_m_input is None or self.usd_per_m_output is None:
            return None
        return (self.input_tokens * self.usd_per_m_input + self.output_tokens * self.usd_per_m_output) / 1e6

    def add(self, input_tokens: int, output_tokens: int) -> None:
        self.calls += 1
        self.input_tokens += max(0, int(input_tokens))
        self.output_tokens += max(0, int(output_tokens))

    def check(self) -> None:
        """Raise before the next model call if a cap is reached."""
        total = self.input_tokens + self.output_tokens
        if total >= self.max_tokens:
            raise BudgetExceeded(f"token cap reached: {total} of {self.max_tokens} tokens used")
        usd = self.usd
        if usd is not None and usd >= self.max_usd:
            raise BudgetExceeded(f"spend cap reached: ${usd:.4f} of ${self.max_usd:.2f}")

    def report(self) -> dict[str, object]:
        usd = self.usd
        return {
            "model_calls": self.calls,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "usd": None if usd is None else round(usd, 6),
            "max_usd": self.max_usd,
            "max_tokens": self.max_tokens,
            "priced": usd is not None,
        }
