"""TWN-001: the versioned robot model registry (URDF + meshes) with provenance.

The happy path uses the real OpenAMRobot platform model (examples/openamr-cmd-timeout/model: upstream's expanded xacro
and upstream's own meshes). The refusals use small synthetic models, because each one is a property of the upload.
"""

from __future__ import annotations

import hashlib
import json
import struct
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient
from helpers import add_member, as_user, make_org

MODEL = Path(__file__).resolve().parents[3] / "examples" / "openamr-cmd-timeout" / "model"
P = "/api/v1/orgs/lab/projects/arm/twin"
H = as_user("ada")


def sha(b: bytes) -> str:
    return "sha256:" + hashlib.sha256(b).hexdigest()


def stl(n: int = 2) -> bytes:
    return b"binary stl".ljust(80, b" ") + struct.pack("<I", n) + b"\x00" * (50 * n)


def post_model(
    client: TestClient, manifest: dict[str, Any], blobs: dict[str, bytes], headers: dict[str, str] | None = None
) -> Any:
    files = [
        ("files", (f["path"].replace("/", "_"), blobs[f["path"]], "application/octet-stream"))
        for f in manifest["files"]
    ]
    return client.post(P + "/models", data={"manifest": json.dumps(manifest)}, files=files, headers=headers or H)


def synthetic(
    urdf: str, meshes: dict[str, bytes] | None = None, urdf_path: str = "robot.urdf"
) -> tuple[dict[str, Any], dict[str, bytes]]:
    blobs = {urdf_path: urdf.encode(), **(meshes or {})}
    manifest = {
        "slug": "toy",
        "name": "Toy",
        "urdf": urdf_path,
        "files": [{"path": p, "sha256": sha(b)} for p, b in blobs.items()],
        "source": {"repository": "example/toy", "commit": "abcdef1", "license_spdx": "MIT"},
    }
    return manifest, blobs


URDF = """<robot name="toy"><link name="base"><visual><geometry><mesh filename="package://toy/meshes/a.stl"/></geometry></visual></link>
<link name="wheel"/>
<joint name="w" type="continuous"><parent link="base"/><child link="wheel"/><axis xyz="0 1 0"/></joint></robot>"""


def setup(client: TestClient) -> None:
    make_org(client, "ada", "lab", "arm")
    add_member(client, "ada", "lab", "vera", "viewer")


def real() -> tuple[dict[str, Any], dict[str, bytes]]:
    manifest = json.loads((MODEL / "manifest.json").read_text(encoding="utf-8"))
    return manifest, {f["path"]: (MODEL / f["path"]).read_bytes() for f in manifest["files"]}


def test_the_real_openamrobot_model_is_stored_byte_for_byte_with_its_provenance_and_structure(
    client: TestClient,
) -> None:
    setup(client)
    manifest, blobs = real()
    r = post_model(client, manifest, blobs)
    assert r.status_code == 201, r.text
    v = r.json()
    assert v["number"] == 1 and v["model_slug"] == "openamrobot-platform"
    assert (
        v["source"]["repository"] == "openAMRobot/openamr-platform-sw"
        and v["source"]["license_spdx"] == "CERN-OHL-P-2.0"
    )
    assert len(v["source"]["commit"]) == 40 and "NOTICE.md" in v["source"]["notice"]
    assert len(v["omitted"]) == 12 and all("not referenced" in o["reason"] for o in v["omitted"])
    st = v["structure"]
    assert st["root"] == "base_footprint" and len(st["links"]) == 25
    wheels = [j for j in st["joints"] if j["type"] == "continuous"]
    assert [j["name"] for j in wheels] == ["left_wheel_joint", "right_wheel_joint"] and wheels[0]["axis"] == [
        0.0,
        1.0,
        0.0,
    ]
    drive = [c for c in st["controllers"] if c["plugin"] == "gz-sim-diff-drive-system"]
    assert (
        drive and drive[0]["params"]["left_joint"] == "left_wheel_joint" and drive[0]["params"]["topic"] == "/cmd_vel"
    )
    assert sorted(s["type"] for s in st["sensors"]).count("gpu_lidar") == 7 and {s["link"] for s in st["sensors"]} >= {
        "lidar_link",
        "imu_link",
    }
    chassis = next(link for link in st["links"] if link["name"] == "base_link")
    first = chassis["visuals"][0]
    assert first["mesh"] == "meshes/visual/base_chassis.stl" and first["rgba"]  # named material resolved to a colour
    for f in v["files"]:  # every file comes back identical to upstream's, with the digest in the ETag
        g = client.get(f"{P}/models/openamrobot-platform/versions/1/files/{f['path']}", headers=as_user("vera"))
        assert g.status_code == 200 and g.content == blobs[f["path"]] and sha(g.content) == f["sha256"]
        assert g.headers["etag"] == f'"{f["sha256"]}"' and g.headers["x-content-type-options"] == "nosniff"
    # the same manifest again is the same version; the listing shows one version
    again = post_model(client, manifest, blobs)
    assert again.status_code == 200 and again.json()["number"] == 1
    listing = client.get(P + "/models", headers=as_user("vera")).json()
    assert [(m["slug"], len(m["versions"])) for m in listing] == [("openamrobot-platform", 1)]


def test_a_changed_file_is_a_new_version_and_the_old_one_is_untouched(client: TestClient) -> None:
    setup(client)
    manifest, blobs = real()
    assert post_model(client, manifest, blobs).status_code == 201
    blobs2 = dict(blobs)
    blobs2["meshes/visual/imu.stl"] = blobs["meshes/visual/imu.stl"][:-1] + b"\x01"
    manifest2 = {
        **manifest,
        "files": [{"path": f["path"], "sha256": sha(blobs2[f["path"]])} for f in manifest["files"]],
    }
    r = post_model(client, manifest2, blobs2)
    assert r.status_code == 201 and r.json()["number"] == 2
    old = client.get(f"{P}/models/openamrobot-platform/versions/1/files/meshes/visual/imu.stl", headers=H).content
    new = client.get(f"{P}/models/openamrobot-platform/versions/2/files/meshes/visual/imu.stl", headers=H).content
    assert old == blobs["meshes/visual/imu.stl"] and new == blobs2["meshes/visual/imu.stl"]


def test_viewers_read_engineers_write_and_other_workspaces_see_nothing(client: TestClient) -> None:
    setup(client)
    manifest, blobs = synthetic(URDF, {"meshes/a.stl": stl()})
    assert post_model(client, manifest, blobs, as_user("vera")).status_code == 403
    assert post_model(client, manifest, blobs).status_code == 201
    assert client.get(P + "/models", headers=as_user("vera")).status_code == 200
    make_org(client, "mallory", "evil", "other")
    for path in ("/models", "/models/toy/versions/1", "/models/toy/versions/1/files/robot.urdf"):
        r = client.get("/api/v1/orgs/lab/projects/arm/twin" + path, headers=as_user("mallory"))
        assert r.status_code == 404, (path, r.status_code)
    r = client.get("/api/v1/orgs/evil/projects/other/twin/models/toy/versions/1", headers=as_user("mallory"))
    assert r.status_code == 404  # her own project has no such model


def test_only_listed_files_are_served_and_never_by_path(client: TestClient) -> None:
    setup(client)
    manifest, blobs = synthetic(URDF, {"meshes/a.stl": stl()})
    assert post_model(client, manifest, blobs).status_code == 201
    # (the HTTP client itself collapses a literal "..", so the traversal forms are percent-encoded)
    forms = ("meshes%2f..%2frobot.urdf", "..%2f..%2fetc%2fpasswd", "meshes/b.stl", "%2e%2e/robot.urdf", "meshes//a.stl")
    for bad in forms:
        assert client.get(f"{P}/models/toy/versions/1/files/{bad}", headers=H).status_code == 404, bad


def refused(
    client: TestClient, manifest: dict[str, Any], blobs: dict[str, bytes], code: str, status: int = 422
) -> None:
    r = post_model(client, manifest, blobs)
    assert r.status_code == status and r.json()["detail"]["code"] == code, (r.status_code, r.text)
    assert client.get(P + "/models", headers=H).json() == []  # nothing was stored


def test_uploads_are_refused_for_unsafe_or_inconsistent_content(client: TestClient) -> None:
    setup(client)
    good = {"meshes/a.stl": stl()}
    # a path that leaves the model
    m, b = synthetic(URDF, {"../a.stl": stl()})
    refused(client, m, b, "twin.path")
    # a type that is not a model file
    m, b = synthetic(URDF, {"meshes/a.exe": b"MZ"})
    refused(client, m, b, "twin.path")
    # a mesh the URDF names but the upload lacks
    m, b = synthetic(URDF.replace("a.stl", "missing.stl"), good)
    refused(client, m, b, "twin.urdf")
    # references that are not inside the model
    for ref in ("file:///etc/passwd", "http://example.com/a.stl", "package://toy/../../a.stl"):
        m, b = synthetic(URDF.replace("package://toy/meshes/a.stl", ref), good)
        refused(client, m, b, "twin.urdf")
    # a DTD or an entity (no entity expansion, ever)
    bomb = '<?xml version="1.0"?><!DOCTYPE lolz [<!ENTITY a "aaaa">]>' + URDF
    m, b = synthetic(bomb, good)
    refused(client, m, b, "twin.urdf")
    # not a robot, or not a tree
    m, b = synthetic("<model/>", good)
    refused(client, m, b, "twin.urdf")
    two_roots = URDF.replace(
        '<joint name="w" type="continuous"><parent link="base"/><child link="wheel"/><axis xyz="0 1 0"/></joint>', ""
    )
    m, b = synthetic(two_roots, good)
    refused(client, m, b, "twin.urdf")
    # a mesh that is not an STL
    m, b = synthetic(URDF, {"meshes/a.stl": b"not a mesh at all"})
    refused(client, m, b, "twin.stl")
    # a declared digest that does not match the bytes
    m, b = synthetic(URDF, good)
    m["files"][1]["sha256"] = "sha256:" + "0" * 64
    refused(client, m, b, "twin.digest")
    # a file nothing refers to
    m, b = synthetic(URDF, {**good, "meshes/extra.stl": stl(3)})
    refused(client, m, b, "twin.unreferenced")
    # the manifest and the uploaded files must pair up
    m, b = synthetic(URDF, good)
    r = client.post(
        P + "/models", data={"manifest": json.dumps(m)}, files=[("files", ("a", b["robot.urdf"], "x"))], headers=H
    )
    assert r.status_code == 422 and r.json()["detail"]["code"] == "twin.files"
    r = client.post(
        P + "/models",
        data={"manifest": json.dumps({**m, "source": {"repository": "x"}})},
        files=[("files", ("a", b"x", "x"))] * 2,
        headers=H,
    )
    assert r.status_code == 422 and r.json()["detail"]["code"] == "twin.manifest"


def test_the_committed_model_files_match_their_manifest() -> None:
    import subprocess
    import sys

    p = subprocess.run(
        [sys.executable, str(MODEL / "build.py"), "--check"], capture_output=True, text=True, check=False
    )
    assert p.returncode == 0, p.stdout + p.stderr
