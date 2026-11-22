"""A trace of one session: every model call and tool call, in order, with what was permitted and what was refused.
Tool outputs are kept with their digest so a finding can be traced to the exact record it read. No secret is stored."""

from __future__ import annotations

import hashlib
import json
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

SCHEMA = "pap.agent-trace/1"


def digest(x: Any) -> str:
    return "sha256:" + hashlib.sha256(json.dumps(x, sort_keys=True, default=str).encode()).hexdigest()


@dataclass
class Trace:
    question: str
    model: str
    org: str
    allow_requests: bool
    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    started: float = field(default_factory=time.time)
    steps: list[dict[str, Any]] = field(default_factory=list)
    answer: str | None = None
    stop: str | None = None
    route: str = "agent"  # or "fast:<name>" when answered without a model
    grounding: dict[str, Any] | None = None
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def _t(self) -> float:
        return round(time.time() - self.started, 3)

    def tool(
        self, name: str, args: dict[str, Any], *, permitted: bool, output: Any = None, error: str | None = None
    ) -> None:
        with self._lock:
            self._append_tool(name, args, permitted, output, error)

    def _append_tool(self, name: str, args: dict[str, Any], permitted: bool, output: Any, error: str | None) -> None:
        self.steps.append(
            {
                "n": len(self.steps) + 1,
                "kind": "tool",
                "tool": name,
                "input": args,
                "permitted": permitted,
                "output_sha256": None if output is None else digest(output),
                "output": output,
                "error": error,
                "t": self._t(),
            }
        )

    def model_call(self, input_tokens: int, output_tokens: int) -> None:
        self.steps.append(
            {"n": len(self.steps) + 1, "kind": "model", "input_tokens": input_tokens, "output_tokens": output_tokens,
             "t": self._t()}
        )  # fmt: skip

    def document(self, usage: dict[str, Any]) -> dict[str, Any]:
        return {
            "schema": SCHEMA,
            "id": self.id,
            "org": self.org,
            "model": self.model,
            "question": self.question,
            "allow_requests": self.allow_requests,
            "steps": self.steps,
            "answer": self.answer,
            "stop": self.stop,
            "route": self.route,
            "grounding": self.grounding,
            "usage": usage,
            "duration_s": self._t(),
        }

    def write(self, directory: Path, usage: dict[str, Any]) -> Path:
        directory.mkdir(parents=True, exist_ok=True)
        p = directory / f"{self.id}.json"
        p.write_text(json.dumps(self.document(usage), indent=1, sort_keys=True, default=str), encoding="utf-8")
        return p
