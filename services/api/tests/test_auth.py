"""AUTH-001: OIDC validation against a real (local) JWKS endpoint, roles, service credentials, audit."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import threading
import time
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from helpers import add_member, as_user, bearer, make_org, ok
from sqlalchemy import select

ISSUER = "http://127.0.0.1:{port}/realms/pap"
AUDIENCE = "pap-api"


class _Keys:
    def __init__(self) -> None:
        self.private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        self.other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(self.private.public_key()))
        jwk.update({"kid": "k1", "use": "sig", "alg": "RS256"})
        self.jwks = {"keys": [jwk]}


@pytest.fixture(scope="module")
def idp() -> Iterator[dict[str, Any]]:
    """A local HTTP server publishing OIDC discovery and a JWKS, so the real fetch path is exercised."""
    keys = _Keys()
    state: dict[str, Any] = {}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            if self.path.endswith("/.well-known/openid-configuration"):
                body = {"issuer": state["issuer"], "jwks_uri": state["issuer"] + "/certs"}
            elif self.path.endswith("/certs"):
                body = keys.jwks
            else:
                self.send_response(404)
                self.end_headers()
                return
            data = json.dumps(body).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *args: Any) -> None:
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    state["issuer"] = ISSUER.format(port=server.server_address[1])
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    yield {"issuer": state["issuer"], "keys": keys}
    server.shutdown()


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def hs256_confusion(idp: dict[str, Any]) -> str:
    """Built by hand: PyJWT itself refuses to sign with a public key as an HMAC secret."""
    from cryptography.hazmat.primitives import serialization

    pem = (
        idp["keys"]
        .private.public_key()
        .public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
    )
    header = _b64(json.dumps({"alg": "HS256", "typ": "JWT", "kid": "k1"}).encode())
    claims = {"iss": idp["issuer"], "aud": AUDIENCE, "sub": "x", "exp": int(time.time()) + 60}
    payload = _b64(json.dumps(claims).encode())
    sig = hmac.new(pem, f"{header}.{payload}".encode(), hashlib.sha256).digest()
    return f"{header}.{payload}.{_b64(sig)}"


def token(idp: dict[str, Any], *, key: Any = None, kid: str = "k1", alg: str = "RS256", **claims: Any) -> str:
    now = int(time.time())
    body = {"iss": idp["issuer"], "aud": AUDIENCE, "sub": "alice-sub", "iat": now, "exp": now + 300, **claims}
    body = {k: v for k, v in body.items() if v is not None}
    return jwt.encode(body, key or idp["keys"].private, algorithm=alg, headers={"kid": kid})


@pytest.fixture
def oidc_client(idp: dict[str, Any], client: TestClient, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    from app.auth.oidc import verifier
    from app.config import get_settings

    monkeypatch.setenv("PAP_AUTH_MODE", "oidc")
    monkeypatch.setenv("PAP_OIDC_ISSUER", idp["issuer"])
    monkeypatch.setenv("PAP_OIDC_AUDIENCE", AUDIENCE)
    get_settings.cache_clear()
    verifier.cache_clear()
    return client


def test_valid_oidc_token_creates_the_user(oidc_client: TestClient, idp: dict[str, Any]) -> None:
    me = ok(oidc_client.get("/api/v1/me", headers=bearer(token(idp, email="alice@example.com"))))
    assert me["issuer"] == idp["issuer"] and me["subject"] == "alice-sub" and me["email"] == "alice@example.com"


@pytest.mark.parametrize(
    "case",
    ["wrong_audience", "wrong_issuer", "expired", "other_key", "no_sub", "unknown_kid", "garbage", "alg_none", "hs256"],
)
def test_invalid_oidc_tokens_are_refused(oidc_client: TestClient, idp: dict[str, Any], case: str) -> None:
    keys = idp["keys"]
    if case == "wrong_audience":
        t = token(idp, aud="someone-else")
    elif case == "wrong_issuer":
        t = token(idp, iss="https://evil.example/realms/pap")
    elif case == "expired":
        t = token(idp, exp=int(time.time()) - 3600, iat=int(time.time()) - 7200)
    elif case == "other_key":
        t = token(idp, key=keys.other)
    elif case == "no_sub":
        t = token(idp, sub=None)
    elif case == "unknown_kid":
        t = token(idp, kid="nope")
    elif case == "garbage":
        t = "not.a.jwt"
    elif case == "alg_none":
        t = jwt.encode(
            {"iss": idp["issuer"], "aud": AUDIENCE, "sub": "x", "exp": int(time.time()) + 60},
            None,
            algorithm="none",
            headers={"kid": "k1"},
        )
    else:  # HS256 signed with the public key as the HMAC secret: the classic algorithm confusion
        t = hs256_confusion(idp)
    r = oidc_client.get("/api/v1/me", headers=bearer(t))
    assert r.status_code == 401, r.text
    assert r.headers.get("www-authenticate") == "Bearer"


def test_dev_tokens_are_refused_in_oidc_mode(oidc_client: TestClient) -> None:
    assert oidc_client.get("/api/v1/me", headers=as_user("alice")).status_code == 401


def test_no_token(client: TestClient) -> None:
    assert client.get("/api/v1/me").status_code == 401
    assert client.get("/api/v1/me", headers={"Authorization": "Basic abc"}).status_code == 401


def test_roles(client: TestClient) -> None:
    make_org(client, "alice", "acme", "picking")
    add_member(client, "alice", "acme", "vic", "viewer")
    add_member(client, "alice", "acme", "eve", "engineer")
    # viewer reads, cannot write
    ok(client.get("/api/v1/orgs/acme/projects/picking", headers=as_user("vic")))
    r = client.post("/api/v1/orgs/acme/projects", json={"slug": "x", "name": "x"}, headers=as_user("vic"))
    assert r.status_code == 403
    # engineer cannot manage members or credentials or projects
    body = {"issuer": "dev", "subject": "zed", "role": "admin"}
    assert client.put("/api/v1/orgs/acme/members", json=body, headers=as_user("eve")).status_code == 403
    assert (
        client.post(
            "/api/v1/orgs/acme/service-credentials", json={"name": "ci", "role": "viewer"}, headers=as_user("eve")
        ).status_code
        == 403
    )
    # admin can
    ok(client.put("/api/v1/orgs/acme/members", json=body, headers=as_user("alice")))
    ok(client.post("/api/v1/orgs/acme/projects", json={"slug": "x", "name": "x"}, headers=as_user("alice")), 201)


def test_last_admin_cannot_be_removed_or_demoted(client: TestClient) -> None:
    make_org(client, "alice", "acme")
    me = ok(client.get("/api/v1/me", headers=as_user("alice")))
    r = client.put(
        "/api/v1/orgs/acme/members",
        json={"issuer": "dev", "subject": "alice", "role": "viewer"},
        headers=as_user("alice"),
    )
    assert r.status_code == 409
    assert client.delete(f"/api/v1/orgs/acme/members/{me['id']}", headers=as_user("alice")).status_code == 409


def test_service_credentials_hashed_scoped_revocable(client: TestClient, database_url: str) -> None:
    from app.db import session_factory
    from app.organizations.models import ServiceCredential

    make_org(client, "alice", "acme", "picking")
    make_org(client, "mallory", "other", "theirs")
    cred = ok(
        client.post(
            "/api/v1/orgs/acme/service-credentials", json={"name": "ci", "role": "engineer"}, headers=as_user("alice")
        ),
        201,
    )
    tok = cred["token"]
    with session_factory()() as s:
        row = s.scalar(select(ServiceCredential).where(ServiceCredential.id == cred["id"]))
        assert row is not None
        assert tok not in (row.token_sha256, row.token_prefix) and row.token_sha256.startswith("sha256:")
    assert "token" not in client.get("/api/v1/orgs/acme/service-credentials", headers=as_user("alice")).json()[0]
    ok(client.get("/api/v1/orgs/acme/projects/picking", headers=bearer(tok)))
    assert client.get("/api/v1/orgs/other/projects/theirs", headers=bearer(tok)).status_code == 404
    assert client.post("/api/v1/orgs", json={"slug": "new", "name": "n"}, headers=bearer(tok)).status_code == 403
    ok(client.delete(f"/api/v1/orgs/acme/service-credentials/{cred['id']}", headers=as_user("alice")), 204)
    assert client.get("/api/v1/orgs/acme/projects/picking", headers=bearer(tok)).status_code == 401
    assert client.get("/api/v1/me", headers=bearer("pap_sc_forged")).status_code == 401


def test_decisions_are_audited(client: TestClient) -> None:
    from app.audit import AuditEvent
    from app.db import session_factory

    make_org(client, "alice", "acme", "picking")
    make_org(client, "mallory", "other")
    add_member(client, "alice", "acme", "vic", "viewer")
    client.post("/api/v1/orgs/acme/projects", json={"slug": "y", "name": "y"}, headers=as_user("vic"))  # 403
    client.get("/api/v1/orgs/acme/projects", headers=as_user("mallory"))  # 404 to an outsider
    with session_factory()() as s:
        rows = s.scalars(select(AuditEvent).order_by(AuditEvent.id)).all()
    actions = [(e.actor, e.action, e.decision) for e in rows]
    assert ("user:dev|alice", "project.create", "allow") in actions
    assert ("user:dev|alice", "member.put", "allow") in actions
    assert any(a == "user:dev|vic" and d == "deny" and "projects" in act for a, act, d in actions)
    outsider = [e for e in rows if e.actor == "user:dev|mallory" and e.decision == "deny"]
    assert outsider and outsider[0].organization_id is None  # nothing about acme is attached to mallory's attempt
    log = ok(client.get("/api/v1/orgs/acme/audit-events", headers=as_user("alice")))
    assert all(e["decision"] in ("allow", "deny") for e in log)
