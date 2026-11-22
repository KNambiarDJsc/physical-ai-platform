"""Evidence grounding. An answer's citations must be ids that a permitted tool actually returned in this session; ids
the answer cites that no tool output contains are flagged as unsupported, and an answer after tool use that cites
nothing is flagged as uncited. This checks the citations, not the reasoning."""

from __future__ import annotations

import json
import re
from typing import Any

UUID = re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b")
DIGEST = re.compile(r"\bsha256:[0-9a-f]{8,64}\b")


def ids_in(text: str) -> set[str]:
    return set(UUID.findall(text)) | set(DIGEST.findall(text))


def check(answer: str | None, steps: list[dict[str, Any]]) -> dict[str, Any]:
    outputs = " ".join(
        json.dumps(s.get("output"), default=str) for s in steps if s.get("kind") == "tool" and s.get("permitted")
    )
    used_tools = any(s.get("kind") == "tool" and s.get("permitted") for s in steps)
    cited = sorted(ids_in(answer or ""))
    unsupported = [i for i in cited if i not in outputs and not any(i.startswith(o) for o in ids_in(outputs))]
    return {
        "cited": cited,
        "unsupported": unsupported,
        "uncited": bool(used_tools and answer and not cited),
        "grounded": bool(cited) and not unsupported,
    }
