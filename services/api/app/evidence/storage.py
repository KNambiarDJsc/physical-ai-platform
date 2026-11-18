"""Content-addressed, write-once artifact storage.

Objects are named by the SHA-256 of their bytes (``sha256/<aa>/<hex>``); a client filename never becomes a path.
Writes stream to a temporary file with a byte limit and are stored only if the object does not exist yet, so stored
bytes are never overwritten; every read checks the bytes against the digest in the key.

Two adapters implement ``Storage``: ``LocalStorage`` (a directory, or a mounted volume in Compose) and ``S3Storage``
(any S3-compatible service; tested against SeaweedFS, DATA-004).
"""

from __future__ import annotations

import base64
import hashlib
import os
import stat
import tempfile
import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Protocol


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


def _verified(key: str, data: bytes) -> bytes:
    if hashlib.sha256(data).hexdigest() != key.rsplit("/", 1)[-1]:
        raise OSError(f"stored object {key} does not match its digest")
    return data


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
        return _verified(key, self.path(key).read_bytes())


class S3Storage:
    """Content-addressed objects in an S3-compatible bucket.

    The upload is spooled to a temporary file first (memory up to 8 MiB, then disk) so the size limit and the digest
    are known before anything is sent; the object is then written only if its key does not exist yet, with the
    SHA-256 checksum for the server to verify. Credentials come from the standard AWS variables or instance role,
    never from this code.
    """

    def __init__(self, client: Any, bucket: str, prefix: str = "") -> None:
        self.client = client
        self.bucket = bucket
        self.prefix = prefix.strip("/") + "/" if prefix.strip("/") else ""

    def _name(self, key: str) -> str:
        key_for("sha256:" + key.rsplit("/", 1)[-1])  # only well-formed content keys reach the bucket
        return self.prefix + key

    def _exists(self, name: str) -> bool:
        from botocore.exceptions import ClientError

        try:
            self.client.head_object(Bucket=self.bucket, Key=name)
            return True
        except ClientError as e:
            if e.response.get("Error", {}).get("Code") in ("404", "NoSuchKey", "NotFound"):
                return False
            raise

    def put(self, chunks: Iterable[bytes], max_bytes: int) -> Stored:
        h = hashlib.sha256()
        size = 0
        with tempfile.SpooledTemporaryFile(max_size=8 * 1024 * 1024) as f:
            for chunk in chunks:
                size += len(chunk)
                if size > max_bytes:
                    raise TooLarge(f"larger than {max_bytes} bytes")
                h.update(chunk)
                f.write(chunk)
            sha = "sha256:" + h.hexdigest()
            key = key_for(sha)
            name = self._name(key)
            if self._exists(name):
                return Stored(sha, size, key, created=False)
            f.seek(0)
            self.client.put_object(
                Bucket=self.bucket,
                Key=name,
                Body=f,
                ContentLength=size,
                ContentType="application/octet-stream",
                ChecksumSHA256=base64.b64encode(h.digest()).decode("ascii"),
            )
            # A concurrent writer of the same content may have written first; the bytes are identical by digest.
            return Stored(sha, size, key, created=True)

    def get(self, key: str) -> bytes:
        obj = self.client.get_object(Bucket=self.bucket, Key=self._name(key))
        return _verified(key, obj["Body"].read())


@lru_cache(maxsize=4)
def _s3(bucket: str, prefix: str, endpoint: str | None, region: str, path_style: bool) -> S3Storage:
    import boto3
    from botocore.config import Config

    client = boto3.client(
        "s3",
        endpoint_url=endpoint,
        region_name=region,
        config=Config(
            s3={"addressing_style": "path" if path_style else "auto"},
            retries={"max_attempts": 5, "mode": "standard"},
            connect_timeout=10,
            read_timeout=60,
        ),
    )
    return S3Storage(client, bucket, prefix)


def get_storage() -> Storage:
    from ..config import get_settings

    s = get_settings()
    if s.storage_backend == "s3":
        assert s.s3_bucket is not None  # checked by Settings
        return _s3(s.s3_bucket, s.s3_prefix, s.s3_endpoint_url, s.s3_region, s.s3_path_style)
    return LocalStorage(s.storage_path)
