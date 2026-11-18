"""DATA-002: uploads are size-limited, content-addressed, immutable, type-checked; filenames are never paths."""

from __future__ import annotations

import os
import stat
from pathlib import Path

import pytest
from app.evidence.storage import LocalStorage, TooLarge, key_for
from fastapi.testclient import TestClient
from helpers import as_user, make_org, ok

URL = "/api/v1/orgs/acme/projects/picking/artifacts"


@pytest.fixture
def proj(client: TestClient) -> TestClient:
    make_org(client, "alice", "acme", "picking")
    return client


def upload(c: TestClient, name: str, data: bytes, who: str = "alice") -> object:
    return c.post(URL, files={"file": (name, data, "application/octet-stream")}, headers=as_user(who))


def stored_files(tmp_path: Path) -> list[Path]:
    root = tmp_path / "artifacts" / "sha256"
    return [p for p in root.rglob("*") if p.is_file()] if root.exists() else []


def test_upload_is_content_addressed_and_deduplicated(proj: TestClient, tmp_path: Path) -> None:
    a = ok(upload(proj, "runs.csv", b"a,b\n1,2\n"), 201)
    assert a["sha256"] == "sha256:" + __import__("hashlib").sha256(b"a,b\n1,2\n").hexdigest()
    again = ok(upload(proj, "other-name.csv", b"a,b\n1,2\n"), 201)
    assert again["id"] == a["id"]
    assert len(stored_files(tmp_path)) == 1
    assert ok(proj.get(f"{URL}/{a['id']}", headers=as_user("alice")))["filename"] == "runs.csv"


def test_over_limit_is_413_and_stores_nothing(
    proj: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.config import get_settings

    monkeypatch.setenv("PAP_MAX_UPLOAD_BYTES", "1000")
    get_settings.cache_clear()
    r = upload(proj, "big.csv", b"x," * 5000)
    assert r.status_code == 413  # type: ignore[attr-defined]
    assert stored_files(tmp_path) == []
    assert list((tmp_path / "artifacts" / "tmp").iterdir()) == []  # the partial file is removed


@pytest.mark.parametrize(
    "name", ["../../../etc/passwd.csv", "..\\..\\windows\\evil.csv", "/abs/path.csv", "C:\\x\\y.csv", "a\x07b.csv"]
)
def test_filenames_never_become_paths(proj: TestClient, tmp_path: Path, name: str) -> None:
    a = ok(upload(proj, name, b"a\n1\n"), 201)
    assert "/" not in a["filename"] and "\\" not in a["filename"] and ".." not in a["filename"]
    assert all(tmp_path / "artifacts" in p.parents for p in stored_files(tmp_path))
    assert not (tmp_path / "etc").exists()


@pytest.mark.parametrize(
    ("name", "data", "code"),
    [
        ("runs.zip", b"PK\x03\x04rest", "upload.type"),
        ("runs.csv", b"PK\x03\x04disguised zip", "upload.archive"),
        ("runs.jsonl", b"\x1f\x8b\x08gzip", "upload.archive"),
        ("runs.csv", b"a,b\x00\x01\x02", "upload.binary"),
        ("runs.exe", b"MZ", "upload.type"),
        ("noext", b"a\n", "upload.type"),
    ],
)
def test_types_are_checked(proj: TestClient, name: str, data: bytes, code: str) -> None:
    r = upload(proj, name, data)
    assert r.status_code == 415, r.text  # type: ignore[attr-defined]
    assert r.json()["detail"]["code"] == code  # type: ignore[attr-defined]


def test_viewer_cannot_upload(proj: TestClient) -> None:
    from helpers import add_member

    add_member(proj, "alice", "acme", "vic", "viewer")
    assert upload(proj, "a.csv", b"a\n", who="vic").status_code == 403  # type: ignore[attr-defined]


def test_storage_never_overwrites_and_checks_digests(tmp_path: Path) -> None:
    s = LocalStorage(tmp_path / "store")
    first = s.put([b"hello"], 100)
    assert first.created
    p = s.path(first.key)
    assert not os.stat(p).st_mode & stat.S_IWUSR  # written read-only
    second = s.put([b"hello"], 100)
    assert not second.created and second.key == first.key
    assert s.get(first.key) == b"hello"
    with pytest.raises(TooLarge):
        s.put([b"x" * 50, b"y" * 60], 100)
    with pytest.raises(ValueError):
        s.path("../../outside")
    with pytest.raises(ValueError):
        key_for("sha256:../../x")
    os.chmod(p, stat.S_IWUSR | stat.S_IRUSR)
    p.write_bytes(b"tampered")
    with pytest.raises(OSError, match="does not match"):
        s.get(first.key)
