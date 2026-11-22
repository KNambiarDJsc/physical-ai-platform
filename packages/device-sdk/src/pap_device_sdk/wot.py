"""W3C Web of Things Thing Descriptions over HTTP, as LabThings-FastAPI serves them.

Discovery reads the LabThings directory (``GET /thing_descriptions/``) or, failing that, a single Thing Description
at the endpoint. Actions are invoked with ``POST`` to the action's form; LabThings answers with an invocation resource
that is polled until it completes. Every URL taken from a description must stay on the endpoint's origin: a
description cannot send the server anywhere the operator did not configure.
"""

from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Callable
from typing import Any, Protocol
from urllib.parse import urljoin, urlsplit

import httpx

from .adapter import AdapterError
from .models import Affordance, DiscoveredDevice, Invocation

_FINAL = {"completed", "error", "cancelled"}
_SCHEMA_SKIP = {"forms", "title", "description", "readOnly", "writeOnly", "observable", "titles", "descriptions"}


def td_digest(td: dict[str, Any]) -> str:
    """sha256 of the description without ``base`` (which echoes the host the request came in on)."""
    body = {k: v for k, v in td.items() if k != "base"}
    return hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _forms_href(aff: dict[str, Any], op: str) -> str | None:
    for f in aff.get("forms", []) or []:
        ops = f.get("op", [])
        ops = [ops] if isinstance(ops, str) else ops
        if op in ops and isinstance(f.get("href"), str):
            return str(f["href"])
    return None


def parse_td(key: str, td: dict[str, Any], protocol: str = "wot-http") -> DiscoveredDevice:
    if not isinstance(td, dict) or not isinstance(td.get("title"), str):
        raise AdapterError(f"{key}: not a Thing Description (no title)")
    affs: list[Affordance] = []
    for name, p in (td.get("properties") or {}).items():
        affs.append(
            Affordance(
                kind="property",
                name=name,
                title=str(p.get("title") or name),
                description=str(p.get("description") or ""),
                read_only=bool(p.get("readOnly", False)),
                data_schema={k: v for k, v in p.items() if k not in _SCHEMA_SKIP},
            )
        )
    for name, a in (td.get("actions") or {}).items():
        inp = a.get("input") if isinstance(a.get("input"), dict) else None
        props = (inp or {}).get("properties") or {}
        idem = (
            "request_id"
            if isinstance(props.get("request_id"), dict) and props["request_id"].get("type") == "string"
            else None
        )
        affs.append(
            Affordance(
                kind="action",
                name=name,
                title=str(a.get("title") or name),
                description=str(a.get("description") or ""),
                read_only=False,
                input_schema=inp,
                output_schema=a.get("output") if isinstance(a.get("output"), dict) else None,
                idempotency_key=idem,
            )
        )
    sim = (td.get("properties") or {}).get("simulated") or {}
    declares_simulated = bool(sim.get("type") == "boolean" and sim.get("readOnly") and sim.get("default") is True)
    return DiscoveredDevice(
        key=key,
        title=td["title"],
        description=str(td.get("description") or ""),
        protocol=protocol,
        td_sha256=td_digest(td),
        declares_simulated=declares_simulated,
        affordances=affs,
        description_document=td,
    )


class Writable(Protocol):
    def write(self, data: bytes, /) -> Any: ...


class WotHttpAdapter:
    protocol = "wot-http"

    def __init__(self, endpoint: str, *, client: httpx.Client | None = None, timeout_s: float = 10.0) -> None:
        if not endpoint.startswith(("http://", "https://")):
            raise AdapterError("the endpoint must be an http(s) URL")
        self.endpoint = endpoint.rstrip("/") + "/"
        self._origin = urlsplit(self.endpoint)[:2]
        self._client = client or httpx.Client(timeout=timeout_s, follow_redirects=False)
        self._tds: dict[str, dict[str, Any]] = {}

    # -- helpers ---------------------------------------------------------------------------------------------------
    def _url(self, href: str) -> str:
        url = urljoin(self.endpoint, href)
        if urlsplit(url)[:2] != self._origin:
            raise AdapterError(f"refusing a link outside the configured endpoint: {href}")
        return url

    def _get(self, href: str) -> httpx.Response:
        try:
            return self._client.get(self._url(href))
        except httpx.HTTPError as e:
            raise AdapterError(f"cannot reach {self.endpoint}: {type(e).__name__}") from None

    def _td(self, device: str) -> dict[str, Any]:
        if device not in self._tds:
            self.discover()
        if device not in self._tds:
            raise AdapterError(f"no device {device!r} at {self.endpoint}")
        return self._tds[device]

    # -- DeviceAdapter -------------------------------------------------------------------------------------------
    def discover(self) -> list[DiscoveredDevice]:
        r = self._get("thing_descriptions/")
        found: dict[str, dict[str, Any]]
        if r.status_code == 200 and isinstance(r.json(), dict) and all(isinstance(v, dict) for v in r.json().values()):
            found = dict(r.json())
        else:
            single = self._get("")
            if single.status_code != 200:
                raise AdapterError(f"no Thing Description at {self.endpoint} (HTTP {single.status_code})")
            td = single.json()
            found = {urlsplit(self.endpoint).path.strip("/").split("/")[-1] or "thing": td}
        self._tds = found
        return [parse_td(k, v) for k, v in sorted(found.items())]

    def read_property(self, device: str, name: str) -> Any:
        prop = (self._td(device).get("properties") or {}).get(name)
        href = _forms_href(prop or {}, "readproperty")
        if not href:
            raise AdapterError(f"{device}.{name} is not a readable property")
        r = self._get(href)
        if r.status_code != 200:
            raise AdapterError(f"reading {device}.{name} failed (HTTP {r.status_code})")
        return r.json()

    def invoke_action(
        self,
        device: str,
        name: str,
        payload: dict[str, Any],
        timeout_s: float = 60.0,
        on_wait: Callable[[], None] | None = None,
        on_wait_every_s: float = 5.0,
    ) -> Invocation:
        act = (self._td(device).get("actions") or {}).get(name)
        href = _forms_href(act or {}, "invokeaction")
        if not href:
            raise AdapterError(f"{device}.{name} is not an action")
        try:
            r = self._client.post(self._url(href), json=payload)
        except httpx.HTTPError as e:
            # The request may or may not have reached the device: the caller must treat the outcome as unknown.
            raise AdapterError(f"no answer from {device}.{name}: {type(e).__name__}") from None
        if r.status_code in (400, 404, 405, 409, 422):
            return Invocation(status="error", accepted=False, error=_problem(r))
        if r.status_code not in (200, 201):
            raise AdapterError(f"{device}.{name} answered HTTP {r.status_code}")
        inv = r.json()
        deadline = time.monotonic() + timeout_s
        next_wait = time.monotonic() + on_wait_every_s
        while inv.get("status") not in _FINAL:
            if on_wait is not None and time.monotonic() >= next_wait:
                on_wait()
                next_wait = time.monotonic() + on_wait_every_s
            if time.monotonic() > deadline:
                return Invocation(status="timeout", invocation_id=str(inv.get("id")), started_at=inv.get("timeStarted"))
            time.sleep(0.15)
            poll = self._get(str(inv.get("href")))
            if poll.status_code != 200:
                raise AdapterError(f"lost the invocation of {device}.{name} (HTTP {poll.status_code})")
            inv = poll.json()
        err = inv.get("error")
        return Invocation(
            status=inv["status"],
            output=inv.get("output"),
            error=(err.get("detail") or err.get("title")) if isinstance(err, dict) else None,
            invocation_id=str(inv.get("id")),
            started_at=inv.get("timeStarted"),
            completed_at=inv.get("timeCompleted"),
        )

    def fetch_bytes(
        self, device: str, path: str, max_bytes: int, timeout_s: float = 120.0
    ) -> tuple[bytes, dict[str, str]]:
        """GET a path under a Thing (an artifact), on the configured origin only, bounded in size. Returns the body and
        the response headers. The caller must check the bytes against the digest the device reported."""
        url = self._url(urljoin(self.endpoint.rstrip("/") + "/", f"{device}/{path.lstrip(chr(47))}"))
        try:
            with self._client.stream("GET", url, timeout=timeout_s) as r:
                if r.status_code != 200:
                    raise AdapterError(f"{device}: {path} answered HTTP {r.status_code}")
                body = bytearray()
                for chunk in r.iter_bytes():
                    body += chunk
                    if len(body) > max_bytes:
                        raise AdapterError(f"{device}: {path} is larger than {max_bytes} bytes")
                return bytes(body), dict(r.headers)
        except httpx.HTTPError as e:
            raise AdapterError(f"cannot fetch {path} from {device}: {type(e).__name__}") from None

    def download(
        self, device: str, path: str, dest: Writable, max_bytes: int, timeout_s: float = 300.0
    ) -> tuple[str, int, dict[str, str]]:
        """Stream a path under a Thing (an artifact) into ``dest``, bounded in size and in memory: one chunk at a time.
        Returns the sha256 (hex) and size of the bytes written and the response headers. As for ``fetch_bytes``, the
        caller must check the digest against what the device reported."""
        url = self._url(urljoin(self.endpoint.rstrip("/") + "/", f"{device}/{path.lstrip(chr(47))}"))
        h = hashlib.sha256()
        size = 0
        try:
            with self._client.stream("GET", url, timeout=timeout_s) as r:
                if r.status_code != 200:
                    raise AdapterError(f"{device}: {path} answered HTTP {r.status_code}")
                for chunk in r.iter_bytes(1024 * 1024):
                    size += len(chunk)
                    if size > max_bytes:
                        raise AdapterError(f"{device}: {path} is larger than {max_bytes} bytes")
                    h.update(chunk)
                    dest.write(chunk)
                return h.hexdigest(), size, dict(r.headers)
        except httpx.HTTPError as e:
            raise AdapterError(f"cannot fetch {path} from {device}: {type(e).__name__}") from None


def _problem(r: httpx.Response) -> str:
    try:
        body = r.json()
    except ValueError:
        return f"HTTP {r.status_code}"
    detail = body.get("detail") if isinstance(body, dict) else None
    if isinstance(detail, list):
        return "; ".join(
            f"{'.'.join(map(str, d.get('loc', [])[1:]))}: {d.get('msg')}" for d in detail if isinstance(d, dict)
        )
    return str(detail or body)[:300]
