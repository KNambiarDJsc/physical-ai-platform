"""Tenant isolation over EVERY organization-scoped route, enumerated from the application (not hand-listed).

An outsider (a user in another organization, and that organization's service credential) calls each route with
the victim's real slugs and ids. Every call must be 404 and the response must contain nothing of the victim's.
"""

from __future__ import annotations

import re
from typing import Any

import pytest
from fastapi.testclient import TestClient
from helpers import as_user, bearer, make_org, ok

# Valid bodies, so a 404 cannot be masked by a 422. A new route with a body needs an entry here.
BODIES: dict[tuple[str, str], dict[str, Any]] = {
    ("PUT", "/api/v1/orgs/{org_slug}/members"): {"issuer": "dev", "subject": "mallory", "role": "admin"},
    ("POST", "/api/v1/orgs/{org_slug}/service-credentials"): {"name": "x", "role": "admin"},
    ("POST", "/api/v1/orgs/{org_slug}/projects"): {"slug": "planted", "name": "planted"},
}


def org_routes() -> list[tuple[str, str]]:
    """Every (method, path) with an organization in its path, from the generated OpenAPI document.

    FastAPI 0.163 includes routers lazily, so ``app.routes`` does not list them; the OpenAPI document is the
    complete public contract (no route uses include_in_schema=False; test_no_hidden_routes checks that).
    """
    from app.routes import register  # the same registration create_app() uses
    from fastapi import FastAPI

    app = FastAPI()
    register(app)
    out = []
    for path, ops in app.openapi()["paths"].items():
        if "{org_slug}" in path:
            out.extend((m.upper(), path) for m in sorted(ops) if m in ("get", "post", "put", "patch", "delete"))
    return out


def test_no_hidden_routes() -> None:
    import ast
    from pathlib import Path

    app_dir = Path(__file__).resolve().parents[1] / "app"
    for f in app_dir.rglob("*.py"):
        for node in ast.walk(ast.parse(f.read_text(encoding="utf-8"))):
            if isinstance(node, ast.keyword) and node.arg == "include_in_schema":
                raise AssertionError(f"{f}: include_in_schema hides a route from the isolation test")


def test_every_org_route_is_listed() -> None:
    routes = org_routes()
    assert len(routes) >= 10  # sanity: the enumeration found the routers
    body_routes = {(m, p) for m, p in routes if m in ("POST", "PUT", "PATCH")}
    missing = body_routes - set(BODIES)
    assert not missing, f"add a valid body for {missing} so isolation is tested, not validation"


@pytest.fixture
def world(client: TestClient) -> dict[str, Any]:
    victim = make_org(client, "alice", "victim-co", "secret-proj")
    me = ok(client.get("/api/v1/me", headers=as_user("alice")))
    cred = ok(
        client.post(
            "/api/v1/orgs/victim-co/service-credentials",
            json={"name": "victim-ci", "role": "admin"},
            headers=as_user("alice"),
        ),
        201,
    )
    make_org(client, "mallory", "mallory-co", "mallory-proj")
    mcred = ok(
        client.post(
            "/api/v1/orgs/mallory-co/service-credentials",
            json={"name": "m-ci", "role": "admin"},
            headers=as_user("mallory"),
        ),
        201,
    )
    secrets = {
        victim["org"]["id"],
        victim["project"]["id"],
        me["id"],
        cred["id"],
        "Victim-Co",
        "secret-proj",
        "victim-ci",
    }
    ids = {"org_slug": "victim-co", "project_slug": "secret-proj", "user_id": me["id"], "credential_id": cred["id"]}
    return {"ids": ids, "secrets": secrets, "outsiders": [as_user("mallory"), bearer(mcred["token"])]}


@pytest.mark.parametrize(("method", "path"), org_routes())
def test_outsiders_get_404_and_nothing_else(client: TestClient, world: dict[str, Any], method: str, path: str) -> None:
    params = set(re.findall(r"{(\w+)}", path))
    unknown = params - set(world["ids"])
    assert not unknown, f"isolation test needs a victim value for {unknown}"
    url = path.format(**world["ids"])
    for headers in world["outsiders"]:
        r = client.request(method, url, headers=headers, json=BODIES.get((method, path)))
        assert r.status_code == 404, f"{method} {url} as outsider -> {r.status_code} {r.text}"
        for s in world["secrets"]:
            assert s not in r.text
    # and the victim's data is unchanged: no planted project, no new member
    projects = ok(client.get("/api/v1/orgs/victim-co/projects", headers=as_user("alice")))
    assert [p["slug"] for p in projects] == ["secret-proj"]
    members = ok(client.get("/api/v1/orgs/victim-co/members", headers=as_user("alice")))
    assert [m["subject"] for m in members] == ["alice"]


def test_me_lists_only_own_organizations(client: TestClient, world: dict[str, Any]) -> None:
    me = ok(client.get("/api/v1/me", headers=as_user("mallory")))
    assert [o["slug"] for o in me["organizations"]] == ["mallory-co"]
