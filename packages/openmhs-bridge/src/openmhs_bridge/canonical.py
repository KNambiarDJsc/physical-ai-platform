"""Canonical JSON and digests, matching ``openmhs_events::canonical`` (RFC 0005 §3).

Keys sorted by code point, no insignificant whitespace, strings escaped as serde_json does. Numbers are the one
place Python and serde_json can disagree (exponent notation: Python ``1e-07``, serde ``1e-7``), so a float that
Python would write with an exponent is refused rather than risk a digest the engine computes differently.
"""

from __future__ import annotations

import hashlib
import json
import math
from typing import Any


def _check(value: Any, path: str) -> None:
    if isinstance(value, bool) or value is None or isinstance(value, str):
        return
    if isinstance(value, int):
        if not -(2**63) <= value < 2**64:
            raise ValueError(f"{path}: integer {value} is outside the 64-bit range the engine reads")
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError(f"{path}: non-finite number")
        if "e" in repr(value) or "E" in repr(value):
            raise ValueError(f"{path}: {value!r} would be written in exponent form; write it as a string")
        return
    if isinstance(value, dict):
        for k, v in value.items():
            if not isinstance(k, str):
                raise ValueError(f"{path}: object key {k!r} is not a string")
            _check(v, f"{path}.{k}")
        return
    if isinstance(value, list | tuple):
        for i, v in enumerate(value):
            _check(v, f"{path}[{i}]")
        return
    raise ValueError(f"{path}: {type(value).__name__} is not JSON")


def canonical_json(value: Any) -> str:
    _check(value, "$")
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def sha256_text(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def digest(value: Any) -> str:
    """``sha256:<hex>`` of the canonical JSON of ``value`` (the manifest identity in RFC 0005)."""
    return sha256_text(canonical_json(value))


def sha256_bytes(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def sha256_file(path: str, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while block := f.read(chunk):
            h.update(block)
    return "sha256:" + h.hexdigest()
