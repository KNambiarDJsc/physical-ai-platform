"""Read a URDF for the robot model registry: validate it, resolve its mesh references against the uploaded files, and
extract the structure (links, joints, controller plugins, sensors) the Workbench inspects.

Uploads are untrusted. The URDF is refused if it declares a DTD or entities (no entity expansion), and mesh references
may only name a file inside the same version (``package://<pkg>/<path>`` or a relative path): never ``file://``, a URL,
an absolute path or ``..``. Nothing here reads the file system.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Any

PATH_RE = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.\-]*(/[A-Za-z0-9_][A-Za-z0-9_.\-]*)*$")
ALLOWED_EXT = {".urdf": "application/xml", ".stl": "model/stl"}
MAX_URDF_BYTES = 2 * 1024 * 1024
MAX_MESH_BYTES = 16 * 1024 * 1024


class ModelError(ValueError):
    """A reason the upload is refused, written for the uploader."""


def check_path(path: str) -> str:
    if not PATH_RE.match(path) or ".." in path.split("/"):
        raise ModelError(f"unsafe file path {path!r}: use relative paths of letters, digits, _ . - and /")
    ext = "." + path.rsplit(".", 1)[-1].lower() if "." in path else ""
    if ext not in ALLOWED_EXT:
        raise ModelError(f"{path!r}: accepted file types are {', '.join(sorted(ALLOWED_EXT))}")
    return ext


def check_stl(path: str, data: bytes) -> None:
    """Binary STL: an 80-byte header, a uint32 triangle count, 50 bytes per triangle. ASCII STL: starts with 'solid'."""
    if len(data) >= 84:
        n = int.from_bytes(data[80:84], "little")
        if len(data) == 84 + 50 * n and n > 0:
            return
    if data.lstrip()[:5] == b"solid" and b"facet" in data[:4096] and b"endsolid" in data[-512:]:
        return
    raise ModelError(f"{path!r} is not a valid STL file")


@dataclass(frozen=True)
class Parsed:
    name: str
    structure: dict[str, Any]
    mesh_refs: list[str]  # resolved to version file paths, sorted, unique


def _floats(s: str | None, n: int, default: float = 0.0) -> list[float]:
    parts = (s or "").split()
    try:
        vals = [float(x) for x in parts]
    except ValueError:
        raise ModelError(f"not a list of numbers: {s!r}") from None
    return (vals + [default] * n)[:n]


def _num(e: ET.Element | None, key: str) -> float | None:
    if e is None or e.get(key) is None:
        return None
    try:
        return float(str(e.get(key)))
    except ValueError:
        raise ModelError(f"{e.tag}@{key} is not a number") from None


def resolve_mesh(ref: str, files: set[str]) -> str:
    if "://" in ref and not ref.startswith("package://"):
        raise ModelError(f"mesh reference {ref!r}: only package:// and relative paths are accepted")
    rest = ref.removeprefix("package://")
    if ref.startswith("package://"):
        _, _, rest = rest.partition("/")  # drop the package name
    if rest.startswith("/") or ".." in rest.split("/"):
        raise ModelError(f"mesh reference {ref!r} leaves the model")
    if rest not in files:
        raise ModelError(f"mesh reference {ref!r} names {rest!r}, which is not among the uploaded files")
    return rest


def parse_urdf(data: bytes, files: set[str]) -> Parsed:
    if len(data) > MAX_URDF_BYTES:
        raise ModelError("the URDF is larger than 2 MiB")
    low = data[:65536].lower()
    if b"<!doctype" in low or b"<!entity" in low:
        raise ModelError("the URDF declares a DTD or entities, which are not accepted")
    try:
        root = ET.fromstring(data)  # noqa: S314 - DTDs and entities were refused above
    except ET.ParseError as e:
        raise ModelError(f"the URDF is not well-formed XML: {e}") from None
    if root.tag != "robot":
        raise ModelError("the root element of a URDF must be <robot>")
    links: dict[str, dict[str, Any]] = {}
    refs: set[str] = set()
    materials = {
        m.get("name") or "": col_el for m in root.findall("material") if (col_el := m.find("color")) is not None
    }
    for el in root.findall("link"):
        name = el.get("name")
        if not name:
            raise ModelError("a link has no name")
        visuals = []
        for v in el.findall("visual"):
            geo = v.find("geometry")
            org = v.find("origin")
            entry: dict[str, Any] = {
                "xyz": _floats(org.get("xyz") if org is not None else None, 3),
                "rpy": _floats(org.get("rpy") if org is not None else None, 3),
            }
            mesh = geo.find("mesh") if geo is not None else None
            if mesh is not None:
                path = resolve_mesh(mesh.get("filename") or "", files)
                refs.add(path)
                entry["mesh"] = path
                sc = mesh.get("scale")
                entry["scale"] = _floats(sc, 3, 1.0) if sc else [1.0, 1.0, 1.0]
            elif geo is not None and len(geo):
                shape = geo[0]
                entry["primitive"] = shape.tag
                entry["size"] = {k: v for k, v in shape.attrib.items()}
            mat = v.find("material")
            col = mat.find("color") if mat is not None else None
            if col is None and mat is not None:
                col = materials.get(mat.get("name") or "")  # a reference to a robot-level material
            if col is not None and col.get("rgba"):
                entry["rgba"] = _floats(col.get("rgba"), 4, 1.0)
            visuals.append(entry)
        links[name] = {"name": name, "visuals": visuals}
    joints: list[dict[str, Any]] = []
    for el in root.findall("joint"):
        name, kind = el.get("name"), el.get("type")
        parent, child = el.find("parent"), el.find("child")
        if not name or not kind or parent is None or child is None:
            raise ModelError("a joint lacks a name, a type, a parent or a child")
        p, c = parent.get("link") or "", child.get("link") or ""
        if p not in links or c not in links:
            raise ModelError(f"joint {name!r} refers to a link that does not exist")
        org, ax, lim = el.find("origin"), el.find("axis"), el.find("limit")
        joints.append(
            {
                "name": name,
                "type": kind,
                "parent": p,
                "child": c,
                "xyz": _floats(org.get("xyz") if org is not None else None, 3),
                "rpy": _floats(org.get("rpy") if org is not None else None, 3),
                "axis": _floats(ax.get("xyz"), 3) if ax is not None and ax.get("xyz") else None,
                "limit": {k: _num(lim, k) for k in ("lower", "upper", "effort", "velocity")}
                if lim is not None
                else None,
            }
        )
    children = {j["child"] for j in joints}
    roots = [n for n in links if n not in children]
    if len(roots) != 1:
        raise ModelError(f"the links must form one tree; roots found: {roots}")
    sensors: list[dict[str, Any]] = []
    controllers: list[dict[str, Any]] = []
    for g in root.findall("gazebo"):
        ref = g.get("reference")
        for s in g.iter("sensor"):
            sensors.append(
                {
                    "name": s.get("name"),
                    "type": s.get("type"),
                    "link": ref,
                    "topic": (s.findtext("topic") or "").strip() or None,
                    "frame": (s.findtext("gz_frame_id") or "").strip() or None,
                    "update_rate_hz": _float_or_none(s.findtext("update_rate")),
                }
            )
        for pl in g.iter("plugin"):
            params: dict[str, Any] = {}
            for ch in pl:
                if ch.tag in params:  # repeated tags (joint_name)
                    prev = params[ch.tag]
                    params[ch.tag] = (
                        [*prev, (ch.text or "").strip()] if isinstance(prev, list) else [prev, (ch.text or "").strip()]
                    )
                else:
                    params[ch.tag] = (ch.text or "").strip()
            controllers.append({"name": pl.get("name"), "plugin": pl.get("filename"), "params": params})
    for rc in root.iter("ros2_control"):
        controllers.append(
            {
                "name": rc.get("name"),
                "plugin": "ros2_control",
                "params": {"joints": [j.get("name") for j in rc.findall("joint")], "type": rc.get("type")},
            }
        )
    return Parsed(
        name=root.get("name") or "robot",
        structure={
            "root": roots[0],
            "links": list(links.values()),
            "joints": joints,
            "sensors": sensors,
            "controllers": controllers,
        },
        mesh_refs=sorted(refs),
    )


def _float_or_none(s: str | None) -> float | None:
    try:
        return float((s or "").strip())
    except ValueError:
        return None
