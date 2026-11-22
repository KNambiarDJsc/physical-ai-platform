"""Models for the harness. ``CappedModel`` wraps any Strands model: it refuses a call once the session's budget is
spent and records the usage each response reports. ``ScriptedModel`` replays a fixed script of turns for tests and is
labelled as such in every trace; it is never presented as a language model's answer."""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncGenerator, AsyncIterable
from typing import Any

from strands.models import Model
from strands.types.streaming import StreamEvent

from .budget import Budget
from .trace import Trace


class CappedModel(Model):
    def __init__(self, inner: Model, budget: Budget, trace: Trace) -> None:
        self.inner, self.budget, self.trace = inner, budget, trace

    def update_config(self, **model_config: Any) -> None:
        self.inner.update_config(**model_config)

    def get_config(self) -> Any:
        return self.inner.get_config()

    def structured_output(self, *args: Any, **kwargs: Any) -> Any:
        raise NotImplementedError("the harness does not use structured output")

    async def stream(self, *args: Any, **kwargs: Any) -> AsyncGenerator[StreamEvent, None]:
        self.budget.check()  # raises BudgetExceeded before any call that would go over
        inp = out = 0
        events: AsyncIterable[StreamEvent] = self.inner.stream(*args, **kwargs)
        async for ev in events:
            if "metadata" in ev:
                usage: dict[str, Any] = dict(ev["metadata"].get("usage") or {})
                inp, out = int(usage.get("inputTokens", 0)), int(usage.get("outputTokens", 0))
            yield ev
        self.budget.add(inp, out)
        self.trace.model_call(inp, out)


def _usage(inp: int, out: int) -> StreamEvent:
    return {
        "metadata": {
            "usage": {"inputTokens": inp, "outputTokens": out, "totalTokens": inp + out},
            "metrics": {"latencyMs": 0},
        }
    }


class ScriptedModel(Model):
    """Plays back turns: each is ``{"tools": [(name, input), ...]}`` or ``{"text": "..."}``, with optional ``usage``.
    For tests of the harness itself (permissions, caps, traces); it decides nothing."""

    label = "scripted (test stand-in, not a language model)"

    def __init__(self, turns: list[dict[str, Any]]) -> None:
        self.turns = list(turns)
        self.seen: list[Any] = []  # what the agent sent each turn (messages), for assertions

    def update_config(self, **model_config: Any) -> None:
        return None

    def get_config(self) -> Any:
        return {"model_id": self.label}

    def structured_output(self, *args: Any, **kwargs: Any) -> Any:
        raise NotImplementedError

    async def stream(self, messages: Any, *args: Any, **kwargs: Any) -> AsyncGenerator[StreamEvent, None]:
        self.seen.append(json.loads(json.dumps(messages, default=str)))
        turn: dict[str, Any] = self.turns.pop(0) if self.turns else {"text": "(script ended)"}
        usage: tuple[int, int] = tuple(turn.get("usage", (100, 20)))
        inp, out = int(usage[0]), int(usage[1])
        yield {"messageStart": {"role": "assistant"}}
        if "tools" in turn:
            for name, args in turn["tools"]:
                yield {"contentBlockStart": {"start": {"toolUse": {"toolUseId": uuid.uuid4().hex[:12], "name": name}}}}
                yield {"contentBlockDelta": {"delta": {"toolUse": {"input": json.dumps(args)}}}}
                yield {"contentBlockStop": {}}
            yield {"messageStop": {"stopReason": "tool_use"}}
        else:
            yield {"contentBlockDelta": {"delta": {"text": turn["text"]}}}
            yield {"contentBlockStop": {}}
            yield {"messageStop": {"stopReason": "end_turn"}}
        yield _usage(inp, out)
