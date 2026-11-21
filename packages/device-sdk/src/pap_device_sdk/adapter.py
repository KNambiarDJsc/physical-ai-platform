from __future__ import annotations

from typing import Any, Protocol

from .models import DiscoveredDevice, Invocation


class AdapterError(Exception):
    """The device or its endpoint did not answer as its description promised. The message is safe to show."""


class DeviceAdapter(Protocol):
    """What every adapter provides, whatever the ecosystem (WoT/LabThings, ROS 2, OPC UA, SiLA 2, ...)."""

    protocol: str

    def discover(self) -> list[DiscoveredDevice]: ...

    def read_property(self, device: str, name: str) -> Any: ...

    def invoke_action(self, device: str, name: str, payload: dict[str, Any], timeout_s: float) -> Invocation: ...
