"""Adapter SDK: the platform side of talking to devices.

An adapter discovers the devices behind one operator-configured endpoint and describes their capabilities
(properties to read, actions to invoke) in one model, whatever the ecosystem. The first adapter speaks the W3C Web of
Things Thing Description over HTTP, as LabThings serves it. Adapters never decide whether a write is allowed; the
executor does (D-026).
"""

from .adapter import AdapterError, DeviceAdapter
from .models import Affordance, DiscoveredDevice, Invocation
from .wot import WotHttpAdapter, td_digest

__all__ = [
    "AdapterError",
    "Affordance",
    "DeviceAdapter",
    "DiscoveredDevice",
    "Invocation",
    "WotHttpAdapter",
    "td_digest",
]
