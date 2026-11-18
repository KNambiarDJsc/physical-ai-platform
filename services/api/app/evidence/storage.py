"""Content-addressed, write-once artifact storage.

Objects are named by the SHA-256 of their bytes (``sha256/<aa>/<hex>``); a client filename never becomes a path.
Writes stream to a temporary file with a byte limit, then move into place only if the object does not exist yet, so
stored bytes are never overwritten. The interface is what an S3-compatible adapter will implement (DATA-002).
"""

from __future__ import annotations

import hashlib
import os
import stat
import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


class TooLarge(Exception):
    pass


@dataclass(frozen=True)
class Stored:
    sha256: str
    size: int
    key: str
    created: bool


class Storage(Protocol):
    def put(self, chunks: Iterable[bytes], max_bytes: int) -> Stored: ...
    def get(self, key: str) -> bytes: ...
    def path(self, key: str) -> Path: ...


def key_for(sha256: str) -> str:
    hexd = sha256.removeprefix("sha256:")
    if len(hexd) != 64 or any(c not in "0123456789abcdef" for c in hexd):
        raise ValueError("not a sha256 digest")
    return f"sha256/{hexd[:2]}/{hexd}"


class LocalStorage:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        (self.root / "tmp").mkdir(parents=True, exist_ok=True)

    def path(self, key: str) -> Path:
        p = (self.root / key).resolve()
        if self.root not in p.parents:
            raise ValueError("key escapes the storage root")
        return p

    def put(self, chunks: Iterable[bytes], max_bytes: int) -> Stored:
        tmp = self.root / "tmp" / uuid.uuid4().hex
        h = hashlib.sha256()
        size = 0
        try:
            with open(tmp, "wb") as f:
                for chunk in chunks:
                    size += len(chunk)
                    if size > max_bytes:
                        raise TooLarge(f"larger than {max_bytes} bytes")
                    h.update(chunk)
                    f.write(chunk)
            sha = "sha256:" + h.hexdigest()
            key = key_for(sha)
            dest = self.path(key)
            if dest.exists():
                return Stored(sha, size, key, created=False)
            dest.parent.mkdir(parents=True, exist_ok=True)
            os.chmod(tmp, stat.S_IRUSR | stat.S_IRGRP)  # read-only: immutability on the filesystem as well
            # A concurrent writer of the same content may win the race; the bytes are identical by digest.
            os.replace(tmp, dest)
            return Stored(sha, size, key, created=True)
        finally:
            if tmp.exists():
                os.chmod(tmp, stat.S_IWUSR | stat.S_IRUSR)
                tmp.unlink()

    def get(self, key: str) -> bytes:
        data = self.path(key).read_bytes()
        expected = key.rsplit("/", 1)[-1]
        if hashlib.sha256(data).hexdigest() != expected:
            raise OSError(f"stored object {key} does not match its digest")
        return data


def get_storage() -> Storage:
    from ..config import get_settings

    return LocalStorage(get_settings().storage_path)
