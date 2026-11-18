"""DATA-004: one storage interface, two adapters; the S3 adapter against a real S3-compatible server (SeaweedFS).

The server binary comes from PAP_WEED_BIN, .tools/seaweedfs (scripts/get-seaweedfs.sh) or PATH. Without it the S3
tests skip, and fail instead with PAP_REQUIRE_S3=1.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import time
import uuid
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[3]
ACCESS, SECRET = "pap-test-access", "pap-test-secret-not-a-real-credential"
PORTS = {"master": 19533, "volume": 19580, "filer": 19888, "s3": 19433}


def weed_binary() -> str | None:
    for candidate in (
        os.environ.get("PAP_WEED_BIN"),
        str(ROOT / ".tools" / "seaweedfs" / "weed.exe"),
        str(ROOT / ".tools" / "seaweedfs" / "weed"),
        shutil.which("weed"),
    ):
        if candidate and Path(candidate).is_file():
            return candidate
    return None


@pytest.fixture(scope="session")
def s3_endpoint(tmp_path_factory: pytest.TempPathFactory) -> Iterator[str]:
    binary = weed_binary()
    if binary is None:
        if os.environ.get("PAP_REQUIRE_S3") == "1":
            pytest.fail("SeaweedFS not found (PAP_WEED_BIN or bash scripts/get-seaweedfs.sh) and PAP_REQUIRE_S3=1")
        pytest.skip("no S3-compatible server binary (bash scripts/get-seaweedfs.sh)")
    data = tmp_path_factory.mktemp("seaweedfs")
    config = data / "s3.json"
    config.write_text(
        json.dumps(
            {
                "identities": [
                    {
                        "name": "pap",
                        "credentials": [{"accessKey": ACCESS, "secretKey": SECRET}],
                        "actions": ["Admin", "Read", "Write", "List", "Tagging"],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    log = (data / "weed.log").open("wb")
    argv = [binary, "server", f"-dir={data}", "-ip=127.0.0.1", "-ip.bind=127.0.0.1", "-s3",
            f"-s3.port={PORTS['s3']}", f"-s3.config={config}", f"-master.port={PORTS['master']}",
            f"-volume.port={PORTS['volume']}", f"-filer.port={PORTS['filer']}", "-master.volumeSizeLimitMB=64",
            "-volume.max=200"]  # one collection per test bucket  # fmt: skip
    proc = subprocess.Popen(argv, stdout=log, stderr=subprocess.STDOUT)
    endpoint = f"http://127.0.0.1:{PORTS['s3']}"
    try:
        client = make_client(endpoint)
        deadline = time.monotonic() + 90
        while True:
            try:
                client.list_buckets()
                break
            except Exception:  # noqa: BLE001  still starting; any error means not ready yet
                if proc.poll() is not None or time.monotonic() > deadline:
                    raise RuntimeError(f"SeaweedFS did not start; see {data / 'weed.log'}") from None
                time.sleep(0.5)
        yield endpoint
    finally:
        proc.terminate()
        proc.wait(timeout=30)
        log.close()


def make_client(endpoint: str) -> Any:
    import boto3
    from botocore.config import Config

    return boto3.client(
        "s3",
        endpoint_url=endpoint,
        region_name="us-east-1",
        aws_access_key_id=ACCESS,
        aws_secret_access_key=SECRET,
        config=Config(s3={"addressing_style": "path"}, retries={"max_attempts": 3}),
    )


@pytest.fixture
def bucket(s3_endpoint: str) -> str:
    name = f"pap-test-{uuid.uuid4().hex[:12]}"
    make_client(s3_endpoint).create_bucket(Bucket=name)
    return name


@pytest.fixture(params=["local", "s3"])
def storage(request: pytest.FixtureRequest, tmp_path: Path) -> Any:
    from app.evidence.storage import LocalStorage, S3Storage

    if request.param == "local":
        return LocalStorage(tmp_path / "store")
    endpoint = request.getfixturevalue("s3_endpoint")
    bucket = request.getfixturevalue("bucket")
    return S3Storage(make_client(endpoint), bucket, prefix="artifacts")


def chunks(data: bytes, size: int = 7) -> Iterator[bytes]:
    for i in range(0, len(data), size):
        yield data[i : i + size]


def test_one_interface_two_adapters(storage: Any) -> None:
    """Content addressing, write-once, digest-checked reads, byte limits: identical behaviour for both adapters."""
    from app.evidence.storage import TooLarge

    data = b"episode_id,robot_status\nbase-0001,success\n" * 50
    sha = "sha256:" + hashlib.sha256(data).hexdigest()
    first = storage.put(chunks(data), max_bytes=10_000)
    assert first.sha256 == sha and first.size == len(data) and first.created
    assert first.key == f"sha256/{sha[7:9]}/{sha[7:]}"
    again = storage.put(chunks(data, 3), max_bytes=10_000)
    assert again.key == first.key and not again.created  # write-once: same content, not written again
    assert storage.get(first.key) == data
    with pytest.raises(TooLarge):
        storage.put(chunks(b"x" * 101), max_bytes=100)
    with pytest.raises(ValueError):
        storage.get("sha256/../../etc/passwd")
    empty = storage.put(iter([]), max_bytes=10)
    assert storage.get(empty.key) == b"" and empty.size == 0


def test_s3_object_changed_behind_our_back_is_refused(s3_endpoint: str, bucket: str) -> None:
    from app.evidence.storage import S3Storage

    client = make_client(s3_endpoint)
    store = S3Storage(client, bucket)
    stored = store.put(iter([b"original evidence"]), max_bytes=1000)
    client.put_object(Bucket=bucket, Key=stored.key, Body=b"tampered evidence")
    with pytest.raises(OSError, match="does not match its digest"):
        store.get(stored.key)


def test_s3_too_large_upload_leaves_nothing(s3_endpoint: str, bucket: str) -> None:
    from app.evidence.storage import S3Storage, TooLarge

    client = make_client(s3_endpoint)
    with pytest.raises(TooLarge):
        S3Storage(client, bucket).put(chunks(b"y" * 5000, 100), max_bytes=1000)
    assert client.list_objects_v2(Bucket=bucket).get("KeyCount", 0) == 0


@pytest.mark.engine
def test_full_evaluation_with_s3_storage(
    s3_endpoint: str, bucket: str, client: TestClient, monkeypatch: pytest.MonkeyPatch, omhs: Any
) -> None:
    """Upload through the API, run the real engine from objects read back from S3, store the bundle in S3.

    ``client`` is requested for its teardown (the per-test database reset); the test builds its own app with S3."""
    from app.config import get_settings
    from app.evidence import storage as storage_mod
    from app.main import create_app
    from conftest import DEMO
    from helpers import as_user, make_org, ok
    from test_jobs import P, work_once

    monkeypatch.setenv("PAP_STORAGE_BACKEND", "s3")
    monkeypatch.setenv("PAP_S3_BUCKET", bucket)
    monkeypatch.setenv("PAP_S3_PREFIX", "pap")
    monkeypatch.setenv("PAP_S3_ENDPOINT_URL", s3_endpoint)
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", ACCESS)
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", SECRET)
    get_settings.cache_clear()
    storage_mod._s3.cache_clear()
    try:
        api = TestClient(create_app())
        make_org(api, "alice", "acme", "picking")
        h = as_user("alice")
        ids: dict[str, str] = {}
        for key, label in (("baseline", "2.14.0"), ("candidate", "2.15.0-rc1")):
            comp = [{"kind": "software", "name": "pick-stack", "version": label}]
            body = {"label": label, "kind": "software", "components": comp}
            ids[key] = ok(api.post(f"{P}/releases", json=body, headers=h), 201)["id"]
            data = (DEMO / "data" / f"{key}.csv").read_bytes()
            art = ok(api.post(f"{P}/artifacts", files={"file": (f"{key}.csv", data)}, headers=h), 201)
            ids[f"{key}_art"] = art["id"]
            expected = f"pap/sha256/{art['sha256'][7:9]}/{art['sha256'][7:]}"
            head = make_client(s3_endpoint).head_object(Bucket=bucket, Key=expected)
            assert head["ContentLength"] == len(data)
        spec = json.loads((DEMO / "mapping.json").read_text(encoding="utf-8"))
        mapping = ok(api.post(f"{P}/mappings", json=spec, headers=h), 201)["id"]
        job = ok(
            api.post(
                f"{P}/evaluations",
                json={
                    "baseline_release_id": ids["baseline"],
                    "candidate_release_id": ids["candidate"],
                    "mapping_id": mapping,
                    "baseline_artifact_ids": [ids["baseline_art"]],
                    "candidate_artifact_ids": [ids["candidate_art"]],
                    "config": {"task_type": "pick_place"},
                },
                headers=h,
            ),
            201,
        )
        assert work_once() == "succeeded"
        done = ok(api.get(f"{P}/evaluations/{job['id']}", headers=h))
        assert done["summary"]["verdict_reported"] == "improvement"
        assert done["summary"]["verdict_verified"] == "insufficient_evidence"
        # The evidence bundle (events file and engine store) went to S3 too.
        keys = {o["Key"] for o in make_client(s3_endpoint).list_objects_v2(Bucket=bucket)["Contents"]}
        for digest in done["provenance"]["bundle"].values():
            assert f"pap/sha256/{digest[7:9]}/{digest[7:]}" in keys
    finally:
        get_settings.cache_clear()
        storage_mod._s3.cache_clear()
