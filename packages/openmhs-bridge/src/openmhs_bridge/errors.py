"""Structured engine errors. Every failure of the engine boundary is one of these codes, never a bare exception."""

from __future__ import annotations

from typing import Any


class EngineError(Exception):
    """A failure at the engine boundary.

    ``code`` is stable and machine-readable; ``transient`` says whether a retry could succeed (only timeouts and
    process start failures are transient; a refusal of the input is not).
    """

    CODES = frozenset(
        {
            "engine.binary_missing",
            "engine.digest_mismatch",
            "engine.interface_mismatch",
            "engine.start_failed",
            "engine.timeout",
            "engine.cancelled",
            "engine.output_too_large",
            "engine.exit",
            "engine.output_invalid",
            "engine.input_rejected",
            "engine.input_invalid",
        }
    )
    TRANSIENT = frozenset({"engine.timeout", "engine.start_failed"})

    def __init__(self, code: str, message: str, detail: dict[str, Any] | None = None) -> None:
        if code not in self.CODES:
            raise ValueError(f"unknown engine error code {code}")
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message
        self.detail = detail or {}

    @property
    def transient(self) -> bool:
        return self.code in self.TRANSIENT

    def to_dict(self) -> dict[str, Any]:
        return {"code": self.code, "message": self.message, "detail": self.detail, "transient": self.transient}
