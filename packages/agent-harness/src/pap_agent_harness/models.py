"""Models for the harness. ``CappedModel`` wraps any Strands model: it refuses a call once the session's budget is
spent and records the usage each response reports. ``ScriptedModel`` replays a fixed script of turns for tests and is
labelled as such in every trace; it is never presented as a language model's answer."""

from __future__ import annotations

import asyncio
import json
import threading
import time
import uuid
from collections.abc import AsyncGenerator, AsyncIterable, Callable
from typing import Any

from strands.models import Model
from strands.types.streaming import StreamEvent

from .budget import Budget
from .trace import Trace


class StopSession(RuntimeError):
    """The session must stop before the next model call (step limit, deadline, cancellation, a spent budget)."""


# A hosted provider is sometimes briefly unavailable (a 502 or 503, a rate limit, a dropped connection). A call that
# fails before the provider produced anything cost nothing and changed nothing, so it is retried after these waits.
RETRY_DELAYS_S: tuple[float, ...] = (3.0, 8.0)


def _transient(e: BaseException) -> bool:
    status = getattr(e, "status_code", None)
    return status in (429, 500, 502, 503, 504) or type(e).__name__ in ("APIConnectionError", "APITimeoutError")


class CappedModel(Model):
    """Wraps any Strands model. Before every call: the session's budget, the experiment's budget, the step limit, the
    deadline and cancellation are checked, and the call is not made if any of them says stop."""

    def __init__(
        self,
        inner: Model,
        budget: Budget,
        trace: Trace,
        *,
        max_calls: int = 12,
        deadline: float | None = None,
        cancel: threading.Event | None = None,
        before_call: Callable[[], None] | None = None,
        progress: Callable[[str], None] | None = None,
        retry_delays: tuple[float, ...] | None = None,
    ) -> None:
        self.retry_delays = retry_delays
        self.inner, self.budget, self.trace = inner, budget, trace
        self.max_calls, self.deadline, self.cancel = max_calls, deadline, cancel
        self.before_call, self.progress = before_call, progress

    def update_config(self, **model_config: Any) -> None:
        self.inner.update_config(**model_config)

    def get_config(self) -> Any:
        return self.inner.get_config()

    def structured_output(self, *args: Any, **kwargs: Any) -> Any:
        raise NotImplementedError("the harness does not use structured output")

    def _gate(self) -> None:
        if self.cancel is not None and self.cancel.is_set():
            raise StopSession("cancelled")
        if self.deadline is not None and time.monotonic() >= self.deadline:
            raise StopSession("timed out")
        if self.budget.calls >= self.max_calls:
            raise StopSession(f"step limit reached: {self.budget.calls} model calls")
        self.budget.check()
        if self.before_call:
            self.before_call()

    async def stream(self, *args: Any, **kwargs: Any) -> AsyncGenerator[StreamEvent, None]:
        self._gate()  # raises before any call that must not be made
        if self.progress:
            self.progress(f"model call {self.budget.calls + 1}")
        inp = out = 0
        delays = RETRY_DELAYS_S if self.retry_delays is None else self.retry_delays
        attempt = 0
        while True:
            started = False  # once the provider has produced anything, a failure is not retried
            try:
                events: AsyncIterable[StreamEvent] = self.inner.stream(*args, **kwargs)
                async for ev in events:
                    started = True
                    if "metadata" in ev:
                        usage: dict[str, Any] = dict(ev["metadata"].get("usage") or {})
                        inp, out = int(usage.get("inputTokens", 0)), int(usage.get("outputTokens", 0))
                    elif self.progress and "contentBlockDelta" in ev:
                        text = ev["contentBlockDelta"].get("delta", {}).get("text")
                        if text:
                            self.progress(f"text:{text}")
                    yield ev
                break
            except Exception as e:
                delay = delays[attempt] if attempt < len(delays) else None
                out_of_time = (
                    self.deadline is not None and delay is not None and time.monotonic() + delay >= self.deadline
                )
                if started or delay is None or out_of_time or not _transient(e):
                    raise
                attempt += 1
                if self.progress:
                    self.progress(f"the model provider did not answer ({type(e).__name__}); retrying in {delay:g} s")
                await asyncio.sleep(delay)
                if self.cancel is not None and self.cancel.is_set():
                    raise StopSession("cancelled") from e
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
