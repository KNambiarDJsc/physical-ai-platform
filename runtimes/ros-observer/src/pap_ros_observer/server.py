"""A small read-only HTTP server for the observer's Things (stdlib only; GET and HEAD, nothing else).

    GET /thing_descriptions/        every Thing Description, keyed by Thing
    GET /<thing>/                   one Thing Description
    GET /<thing>/<property>         the property's current value

Any other method is refused with 405. Binds to 127.0.0.1 unless told otherwise.
"""

from __future__ import annotations

import json
import math
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from .things import Thing


def clean(v: Any) -> Any:
    """Replace NaN and infinities (not valid JSON) by null, recursively."""
    if isinstance(v, float):
        return v if math.isfinite(v) else None
    if isinstance(v, dict):
        return {k: clean(x) for k, x in v.items()}
    if isinstance(v, list | tuple):
        return [clean(x) for x in v]
    return v


def make_handler(things: dict[str, Thing]) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        server_version = "pap-ros-observer/1"

        def _send(self, status: int, body: Any) -> None:
            data = json.dumps(clean(body), sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(data)

        def do_GET(self) -> None:
            parts = [p for p in self.path.split("?")[0].split("/") if p]
            if parts == ["thing_descriptions"]:
                return self._send(HTTPStatus.OK, {k: t.td() for k, t in things.items()})
            thing = things.get(parts[0]) if parts else None
            if thing is None:
                return self._send(HTTPStatus.NOT_FOUND, {"detail": "no such thing"})
            if len(parts) == 1:
                return self._send(HTTPStatus.OK, thing.td())
            prop = thing.properties.get(parts[1]) if len(parts) == 2 else None
            if prop is None:
                return self._send(HTTPStatus.NOT_FOUND, {"detail": "no such property"})
            try:
                return self._send(HTTPStatus.OK, prop.read())
            except Exception as e:  # a failing reader must answer, not hang the connection  # noqa: BLE001
                return self._send(HTTPStatus.INTERNAL_SERVER_ERROR, {"detail": f"{type(e).__name__}: {e}"})

        do_HEAD = do_GET

        def _refuse(self) -> None:
            self._send(HTTPStatus.METHOD_NOT_ALLOWED, {"detail": "this observer is read-only: GET only"})

        do_POST = do_PUT = do_PATCH = do_DELETE = _refuse

        def log_message(self, format: str, *args: Any) -> None:
            pass  # quiet: the platform polls every second

    return Handler


def serve(things: dict[str, Thing], host: str, port: int) -> ThreadingHTTPServer:
    return ThreadingHTTPServer((host, port), make_handler(things))
