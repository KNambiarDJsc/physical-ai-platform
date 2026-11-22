"""Recording ingest in bounded memory: a file is spooled in fixed-size chunks (hashed as it goes), decoded from the
file and stored from the file. Used by the upload route and by experiment capture, so the same checks apply to both.

Why chunks: ``f.read(limit + 1)`` on a file that has rolled over to disk reserves ``limit + 1`` bytes before reading
anything, so every recording upload, even a 20 KB one, asked the allocator for 96 MiB at once; under memory pressure
that raised ``MemoryError`` (the 2026-11-22 gate). Nothing here allocates more than one chunk at a time.
"""

from __future__ import annotations

import hashlib
import tempfile
import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any, BinaryIO

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..evidence.storage import Storage
from .models import Recording
from .track import build_track, track_sha256

CHUNK = 1024 * 1024
SPOOL_IN_MEMORY = 8 * 1024 * 1024  # above this a spool lives on disk
MCAP_MAGIC = b"\x89MCAP0\r\n"


class IngestError(Exception):
    def __init__(self, status: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status, self.code, self.message = status, code, message


@dataclass
class Spooled:
    file: Any  # a seekable binary file positioned at 0
    sha256: str  # "sha256:<hex>"
    size: int

    def chunks(self) -> Iterator[bytes]:
        self.file.seek(0)
        while chunk := self.file.read(CHUNK):
            yield chunk
        self.file.seek(0)

    def close(self) -> None:
        self.file.close()


def spool(source: BinaryIO, limit: int, *, magic: bytes | None = None) -> Spooled:
    """Copy ``source`` into a spooled temporary file one chunk at a time, hashing it. Refuses more than ``limit``
    bytes (413) and, when ``magic`` is given, a file that does not start with it (415)."""
    out = tempfile.SpooledTemporaryFile(max_size=SPOOL_IN_MEMORY)  # noqa: SIM115 - closed by the caller
    h = hashlib.sha256()
    size = 0
    try:
        while chunk := source.read(CHUNK):
            if size == 0 and magic is not None and not chunk.startswith(magic):
                raise IngestError(415, "twin.type", "the file is not an MCAP file")
            size += len(chunk)
            if size > limit:
                raise IngestError(413, "twin.too_large", f"a file is larger than {limit} bytes")
            h.update(chunk)
            out.write(chunk)
        if magic is not None and size < len(magic):
            raise IngestError(415, "twin.type", "the file is not an MCAP file")
        out.seek(0)
    except BaseException:
        out.close()
        raise
    return Spooled(out, "sha256:" + h.hexdigest(), size)


def check_summary(sha: str, summary: dict[str, Any] | None) -> None:
    if summary is None:
        return
    listed = {f.get("sha256") for f in summary.get("files", []) if str(f.get("name", "")).endswith(".mcap")}
    if sha.removeprefix("sha256:") not in listed and sha not in listed:
        raise IngestError(422, "twin.summary", "the summary does not describe this file (its sha256 is not listed)")


def decode(spooled: Spooled, summary: dict[str, Any] | None) -> dict[str, Any]:
    from .track import RecordingError

    try:
        return build_track(spooled.file, summary)
    except RecordingError as e:
        raise IngestError(422, "twin.recording", str(e)) from None
    finally:
        spooled.file.seek(0)


def store_recording(
    session: Session,
    storage: Storage,
    *,
    project_id: uuid.UUID,
    spooled: Spooled,
    label: str,
    filename: str,
    max_bytes: int,
    summary: dict[str, Any] | None,
    identity: dict[str, Any] | None,
    model_version_id: uuid.UUID | None,
    episode_id: uuid.UUID | None,
    workflow_run_id: uuid.UUID | None,
    created_by: str,
) -> tuple[Recording, bool]:
    """Decode and store a spooled MCAP as a Recording of the project. Returns it and whether it is new: the same
    bytes are one recording per project, so a second trial that left identical bytes shares it."""
    existing = session.scalar(
        select(Recording).where(Recording.project_id == project_id, Recording.sha256 == spooled.sha256)
    )
    if existing is not None:
        return existing, False
    track = decode(spooled, summary)
    stored = storage.put(spooled.chunks(), max_bytes)
    r = Recording(
        project_id=project_id,
        label=label,
        filename=filename,
        sha256=spooled.sha256,
        size_bytes=stored.size,
        storage_key=stored.key,
        summary=summary,
        identity=identity,
        model_version_id=model_version_id,
        episode_id=episode_id,
        workflow_run_id=workflow_run_id,
        track=track,
        track_sha256=track_sha256(track),
        created_by=created_by,
    )
    session.add(r)
    session.flush()
    return r, True
