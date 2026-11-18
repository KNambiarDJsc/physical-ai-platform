from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient


def as_user(subject: str) -> dict[str, str]:
    return {"Authorization": f"Bearer dev:{subject}"}


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def ok(r: Any, status: int = 200) -> Any:
    assert r.status_code == status, f"{r.request.method} {r.request.url} -> {r.status_code}: {r.text}"
    return r.json() if r.content else None


def make_org(client: TestClient, admin: str, slug: str, project: str | None = None) -> dict[str, Any]:
    org = ok(client.post("/api/v1/orgs", json={"slug": slug, "name": slug.title()}, headers=as_user(admin)), 201)
    out: dict[str, Any] = {"org": org}
    if project:
        out["project"] = ok(
            client.post(
                f"/api/v1/orgs/{slug}/projects", json={"slug": project, "name": project}, headers=as_user(admin)
            ),
            201,
        )
    return out


def add_member(client: TestClient, admin: str, org: str, subject: str, role: str) -> dict[str, Any]:
    body = {"issuer": "dev", "subject": subject, "role": role}
    result: dict[str, Any] = ok(client.put(f"/api/v1/orgs/{org}/members", json=body, headers=as_user(admin)))
    return result
