"""Per-experiment cost limits across sessions. A session scoped to an experiment adds its usage to that experiment's
ledger entry; a session is refused before it starts, and stopped before a model call, once the experiment's cap is
spent. The ledger holds numbers only (tokens, dollars, session ids), never a key or a prompt."""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any

from .budget import BudgetExceeded

_LOCK = threading.Lock()


class Ledger:
    def __init__(self, path: Path) -> None:
        self.path = path

    def _read(self) -> dict[str, Any]:
        try:
            return dict(json.loads(self.path.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            return {}

    def entry(self, key: str) -> dict[str, Any]:
        return dict(self._read().get(key, {"tokens": 0, "usd": 0.0, "sessions": []}))

    def check(self, key: str, max_tokens: int | None, max_usd: float | None, pending_tokens: int = 0,
              pending_usd: float = 0.0) -> None:  # fmt: skip
        e = self.entry(key)
        if max_tokens is not None and e["tokens"] + pending_tokens >= max_tokens:
            raise BudgetExceeded(
                f"experiment {key} has used its token budget ({e['tokens'] + pending_tokens} of {max_tokens})"
            )
        if max_usd is not None and e["usd"] + pending_usd >= max_usd:
            raise BudgetExceeded(
                f"experiment {key} has used its spend budget (${e['usd'] + pending_usd:.4f} of ${max_usd:.2f})"
            )

    def add(self, key: str, session_id: str, tokens: int, usd: float | None) -> None:
        with _LOCK:
            d = self._read()
            e = d.get(key, {"tokens": 0, "usd": 0.0, "sessions": []})
            e["tokens"] += int(tokens)
            e["usd"] = round(e["usd"] + (usd or 0.0), 6)
            if session_id not in e["sessions"]:
                e["sessions"].append(session_id)
            d[key] = e
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(d, indent=1, sort_keys=True), encoding="utf-8")
            tmp.replace(self.path)
