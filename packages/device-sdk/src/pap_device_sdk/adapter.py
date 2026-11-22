from __future__ import annotations

from collections.abc import Callable
from typing import Any, Protocol

from .models import DiscoveredDevice, Invocation


class AdapterError(Exception):
    """The device or its endpoint did not answer as its description promised. The message is safe to show."""


class DeviceAdapter(Protocol):
    """What every adapter provides, whatever the ecosystem (WoT/LabThings, ROS 2, OPC UA, SiLA 2, ...)."""

    protocol: str

    def discover(self) -> list[DiscoveredDevice]: ...

    def read_property(self, device: str, name: str) -> Any: ...

    def invoke_action(
        self,
        device: str,
        name: str,
        payload: dict[str, Any],
        timeout_s: float,
        on_wait: Callable[[], None] | None = None,
        on_wait_every_s: float = 5.0,
    ) -> Invocation:
        """Invoke an action and wait. ``on_wait`` is called about every five seconds while waiting, so a caller that
        holds a lease (the worker) can renew it during a long action."""
        ...
