"""Model settings from the environment. The API key is read once and never written, logged or put in a trace."""

from __future__ import annotations

import os
from dataclasses import dataclass, field


class NotConfigured(RuntimeError):
    pass


@dataclass(frozen=True)
class LLMSettings:
    base_url: str
    model: str
    api_key: str = field(repr=False)
    max_usd: float = 0.50  # hard cap per session, when prices are known
    max_tokens: int = 200_000  # hard cap per session, whatever the price
    usd_per_m_input: float | None = None  # price per million input tokens, when known
    usd_per_m_output: float | None = None
    # How hard a reasoning model thinks before answering: "low", "medium" or "high". Unset: the provider's default.
    # Lower is faster and cheaper; it is a speed setting, not a safety one (the harness checks answers either way).
    reasoning_effort: str | None = None

    @classmethod
    def from_env(cls, max_usd: float | None = None) -> LLMSettings:
        key = os.environ.get("PAP_LLM_API_KEY", "")
        base = os.environ.get("PAP_LLM_BASE_URL", "")
        model = os.environ.get("PAP_LLM_MODEL", "")
        names = (("PAP_LLM_API_KEY", key), ("PAP_LLM_BASE_URL", base), ("PAP_LLM_MODEL", model))
        missing = [n for n, v in names if not v]
        if missing:
            raise NotConfigured(f"set {', '.join(missing)} in the environment (never in a file)")

        def num(name: str) -> float | None:
            v = os.environ.get(name)
            return float(v) if v else None

        effort = os.environ.get("PAP_LLM_REASONING_EFFORT") or None
        if effort not in (None, "low", "medium", "high"):
            raise NotConfigured("PAP_LLM_REASONING_EFFORT must be low, medium or high")
        return cls(
            reasoning_effort=effort,
            base_url=base,
            model=model,
            api_key=key,
            max_usd=max_usd if max_usd is not None else (num("PAP_LLM_MAX_USD") or 0.50),
            max_tokens=int(os.environ.get("PAP_LLM_MAX_TOKENS", "200000")),
            usd_per_m_input=num("PAP_LLM_USD_PER_M_INPUT"),
            usd_per_m_output=num("PAP_LLM_USD_PER_M_OUTPUT"),
        )
