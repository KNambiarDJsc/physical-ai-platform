from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class Affordance(BaseModel):
    """One capability of a device: a property to read (or write) or an action to invoke."""

    kind: Literal["property", "action"]
    name: str
    title: str
    description: str = ""
    read_only: bool = True
    data_schema: dict[str, Any] = Field(default_factory=dict)  # property value schema
    input_schema: dict[str, Any] | None = None  # action input
    output_schema: dict[str, Any] | None = None  # action output
    idempotency_key: str | None = None  # input field the device deduplicates on, when the action has one


class DiscoveredDevice(BaseModel):
    key: str  # the device's name at its endpoint (LabThings: the Thing's path)
    title: str
    description: str = ""
    protocol: str
    td_sha256: str
    declares_simulated: bool  # its description has a read-only boolean property "simulated" defaulting to true
    affordances: list[Affordance]
    description_document: dict[str, Any]  # the raw device description, kept for provenance


class Invocation(BaseModel):
    status: Literal["completed", "error", "cancelled", "timeout"]
    accepted: bool = True  # False: the device refused the request (e.g. invalid input), so nothing started
    output: Any = None
    error: str | None = None
    invocation_id: str | None = None
    started_at: str | None = None
    completed_at: str | None = None
