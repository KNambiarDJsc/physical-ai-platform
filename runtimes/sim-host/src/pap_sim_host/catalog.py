"""The operator's scenario catalog: the only thing a host will ever run.

A scenario is a fixed argument list (never a shell string) with placeholders, a JSON Schema for its parameters, the
measurements it outputs and the artifacts it leaves. The catalog is read once, at start-up, from a file the operator
owns; nothing a caller sends can add to it or change a command.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

ID = r"^[a-z][a-z0-9_-]{0,63}$"
NAME = r"^[A-Za-z][A-Za-z0-9_.-]{0,63}$"
PLACEHOLDER = re.compile(r"\{([a-z_]+(?:\.[A-Za-z0-9_]+)?)\}")
FIXED = {"run_dir", "params_file", "catalog_dir", "python"}


class CatalogError(ValueError):
    pass


class Output(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(pattern=NAME)
    unit: str | None = Field(default=None, max_length=24)
    description: str = Field(default="", max_length=300)


class ArtifactDef(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(pattern=NAME)
    media_type: str = Field(max_length=100)
    description: str = Field(default="", max_length=300)
    optional: bool = False


class Scenario(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(pattern=ID)
    version: str = Field(min_length=1, max_length=32)
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=2000)
    parameters: dict[str, Any]
    outputs: list[Output] = Field(default_factory=list)
    artifacts: list[ArtifactDef] = Field(default_factory=list)
    max_duration_s: float = Field(gt=0, le=7200)
    command: list[str] = Field(min_length=1, max_length=64)
    result_file: str = Field(default="result.json", pattern=r"^[A-Za-z0-9_.-]{1,64}$")

    @field_validator("parameters")
    @classmethod
    def _schema(cls, v: dict[str, Any]) -> dict[str, Any]:
        try:
            Draft202012Validator.check_schema(v)
        except Exception as e:  # noqa: BLE001
            raise ValueError(f"parameters is not a valid JSON Schema: {e}") from None
        if v.get("type") != "object" or v.get("additionalProperties") is not False:
            raise ValueError("parameters must be an object schema with additionalProperties: false")
        return v

    @model_validator(mode="after")
    def _command(self) -> Scenario:
        props = set((self.parameters.get("properties") or {}).keys())
        for arg in self.command:
            for m in PLACEHOLDER.findall(arg):
                if m in FIXED:
                    continue
                kind, _, name = m.partition(".")
                if kind != "param" or name not in props:
                    raise ValueError(
                        f"command placeholder {{{m}}} is not run_dir, params_file, catalog_dir, python "
                        "or a declared parameter"
                    )
        names = [o.name for o in self.outputs]
        if len(set(names)) != len(names) or len({a.name for a in self.artifacts}) != len(self.artifacts):
            raise ValueError("output and artifact names must be unique")
        return self

    def public(self) -> dict[str, Any]:
        """What a caller may see: everything except the command."""
        d = self.model_dump(exclude={"command", "result_file"})
        d["parameters_schema"] = d.pop("parameters")
        return d


class Simulator(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: str = Field(pattern=ID)
    name: str = Field(min_length=1, max_length=120)
    version: str | None = Field(default=None, max_length=64)
    description: str = Field(default="", max_length=1000)


class Catalog(BaseModel):
    model_config = ConfigDict(extra="forbid")
    simulator: Simulator
    scenarios: list[Scenario] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def _unique(self) -> Catalog:
        keys = [(s.id, s.version) for s in self.scenarios]
        if len(set(keys)) != len(keys):
            raise ValueError("scenario id and version pairs must be unique")
        return self

    def find(self, scenario: str, version: str | None = None) -> Scenario | None:
        found = [s for s in self.scenarios if s.id == scenario and (version is None or s.version == version)]
        return found[-1] if found else None


def load_catalog(path: Path) -> Catalog:
    try:
        return Catalog.model_validate(json.loads(path.read_text(encoding="utf-8")))
    except (OSError, ValueError) as e:
        raise CatalogError(f"{path}: {e}") from None
