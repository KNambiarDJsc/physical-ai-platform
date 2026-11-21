"""The platform API as the CALLER sees it: every request carries the caller's own credential, so tenant isolation and
roles apply unchanged. The tool layer has no database access and no other way in."""

from __future__ import annotations

from typing import Any

import httpx

CHANNEL_HEADER = "X-PAP-Channel"
CHANNEL = "agent-tools"


class ToolError(Exception):
    """A failure to show the assistant as text: what was refused or missing, never a stack trace or a credential."""


class PlatformClient:
    def __init__(self, base_url: str, token: str, *, http: httpx.Client | None = None, timeout_s: float = 20.0) -> None:
        if not token:
            raise ToolError("no credential: set PAP_API_TOKEN (a viewer credential is enough to read and propose)")
        self._http = http or httpx.Client(base_url=base_url.rstrip("/"), timeout=timeout_s)
        self._headers = {"Authorization": f"Bearer {token}", CHANNEL_HEADER: CHANNEL}

    def _call(self, method: str, path: str, **kw: Any) -> Any:
        try:
            r = self._http.request(method, path, headers=self._headers, **kw)
        except httpx.HTTPError as e:
            raise ToolError(f"the platform did not answer ({type(e).__name__})") from None
        if r.status_code >= 400:
            try:
                d = r.json().get("detail")
            except ValueError:
                d = None
            msg = d.get("message") if isinstance(d, dict) else (str(d)[:200] if d else r.reason_phrase)
            raise ToolError(f"{method} {path.split('?')[0]} was refused: HTTP {r.status_code}, {msg}")
        return r.json() if r.content else None

    def get(self, path: str, **params: Any) -> Any:
        return self._call("GET", path, params={k: v for k, v in params.items() if v is not None})

    def post(self, path: str, body: dict[str, Any]) -> Any:
        return self._call("POST", path, json=body)
