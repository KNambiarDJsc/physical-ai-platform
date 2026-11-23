"""A hosted model provider is sometimes briefly unavailable. A call that fails before the provider produced anything
cost nothing and changed nothing, so the harness retries it a bounded number of times; anything else fails as before.
Scripted stand-in model (labelled in every trace): these tests say nothing about a real provider's behaviour."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from pathlib import Path
from typing import Any

import httpx
import pytest
from pap_agent_harness import models
from pap_agent_harness.agent import Options, run_session
from pap_agent_harness.budget import Budget
from pap_agent_harness.models import ScriptedModel
from pap_agent_tools.client import PlatformClient
from strands.models import Model
from strands.types.streaming import StreamEvent


class ProviderDown(Exception):
    def __init__(self, status: int) -> None:
        super().__init__(f"Error code: {status}")
        self.status_code = status


class Flaky(Model):
    """Fails the first ``fails`` calls with ``status`` before producing anything, then acts like the scripted model."""

    def __init__(self, inner: ScriptedModel, fails: int, status: int = 502) -> None:
        self.inner, self.fails, self.status, self.attempts = inner, fails, status, 0

    def update_config(self, **model_config: Any) -> None: ...

    def get_config(self) -> Any:
        return {}

    def structured_output(self, *args: Any, **kwargs: Any) -> Any:
        raise NotImplementedError

    async def stream(self, *args: Any, **kwargs: Any) -> AsyncGenerator[StreamEvent, None]:
        self.attempts += 1
        if self.attempts <= self.fails:
            raise ProviderDown(self.status)
        async for ev in self.inner.stream(*args, **kwargs):
            yield ev


def client() -> PlatformClient:
    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.path == "/api/v1/me":
            return httpx.Response(200, json={"kind": "user", "organizations": [{"slug": "lab", "role": "viewer"}]})
        return httpx.Response(404, json={"detail": {"code": "not_found", "message": "nope"}})

    http = httpx.Client(transport=httpx.MockTransport(handler), base_url="http://platform.test")
    return PlatformClient("http://platform.test", "dev:ada", http=http)


def session(model: Model, tmp_path: Path):  # type: ignore[no-untyped-def]
    return run_session(
        question="Why?", model=model, model_label="scripted", client=client(), budget=Budget(100_000, 1.0),
        options=Options(org="lab", trace_dir=tmp_path / "t"),
    )  # fmt: skip


@pytest.fixture(autouse=True)
def no_waiting(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(models, "RETRY_DELAYS_S", (0.0, 0.0))


def test_a_brief_provider_outage_is_retried_and_costs_nothing_extra(tmp_path: Path) -> None:
    m = Flaky(ScriptedModel([{"text": "all good"}]), fails=1)
    s = session(m, tmp_path)
    assert s.trace.answer == "all good" and s.trace.stop == "answered"
    assert m.attempts == 2 and s.budget.calls == 1  # the failed attempt is not a model call and spent no tokens


def test_a_lasting_outage_fails_after_a_bounded_number_of_retries(tmp_path: Path) -> None:
    m = Flaky(ScriptedModel([{"text": "never"}]), fails=99)
    s = session(m, tmp_path)
    assert m.attempts == 3  # the first try and two retries, no more
    assert s.trace.answer is None and s.trace.stop is not None and "502" in s.trace.stop
    assert s.budget.calls == 0 and s.budget.report()["input_tokens"] == 0


def test_an_error_that_is_not_transient_is_not_retried(tmp_path: Path) -> None:
    m = Flaky(ScriptedModel([{"text": "never"}]), fails=99, status=400)
    s = session(m, tmp_path)
    assert m.attempts == 1 and s.trace.answer is None and "400" in (s.trace.stop or "")
