"""Authentication and authorization dependencies. Every protected route goes through these.

Organization access: a caller who is not a member of the organization named in the path gets 404, exactly as if
it did not exist, and the attempt is audited. A member whose role is too low gets 403 (they already know the
organization exists). Project access is always resolved inside the caller's organization.
"""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass
from typing import Annotated, Literal

from fastapi import Depends, HTTPException, Path, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import audit
from ..config import Settings, get_settings
from ..db import get_session, session_factory, utcnow
from ..organizations.models import Membership, Organization, ServiceCredential
from ..projects.models import Project
from .models import User
from .oidc import TokenInvalid, verifier

Role = Literal["admin", "engineer", "viewer"]
RANK: dict[str, int] = {"viewer": 1, "engineer": 2, "admin": 3}
SERVICE_PREFIX = "pap_sc_"
SLUG = r"^[a-z0-9][a-z0-9-]{0,62}$"


def error(status: int, code: str, message: str) -> HTTPException:
    return HTTPException(status_code=status, detail={"code": code, "message": message})


def unauthorized(message: str = "authentication required") -> HTTPException:
    e = error(401, "auth.unauthenticated", message)
    e.headers = {"WWW-Authenticate": "Bearer"}
    return e


@dataclass(frozen=True)
class Principal:
    kind: Literal["user", "service"]
    id: uuid.UUID
    label: str
    service_org_id: uuid.UUID | None = None
    service_role: str | None = None


def token_sha256(token: str) -> str:
    return "sha256:" + hashlib.sha256(token.encode("utf-8")).hexdigest()


def _upsert_user(session: Session, issuer: str, subject: str, email: str | None, name: str | None) -> User:
    user = session.scalar(select(User).where(User.issuer == issuer, User.subject == subject))
    if user is None:
        user = User(issuer=issuer, subject=subject, email=email, display_name=name)
        session.add(user)
        session.flush()
    elif (email and user.email != email) or (name and user.display_name != name):
        user.email = email or user.email
        user.display_name = name or user.display_name
    return user


def get_principal(
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> Principal:
    header = request.headers.get("authorization", "")
    scheme, _, token = header.partition(" ")
    token = token.strip()
    if scheme.lower() != "bearer" or not token or len(token) > 8192:
        raise unauthorized()

    if token.startswith(SERVICE_PREFIX):
        cred = session.scalar(select(ServiceCredential).where(ServiceCredential.token_sha256 == token_sha256(token)))
        if cred is None or cred.revoked_at is not None:
            raise unauthorized("invalid or revoked service credential")
        cred.last_used_at = utcnow()
        session.commit()
        return Principal("service", cred.id, f"service:{cred.name}", cred.organization_id, cred.role)

    if settings.auth_mode == "dev":
        if settings.env == "production":  # also refused at start; checked again here on purpose
            raise unauthorized()
        if not token.startswith("dev:") or len(token) < 5:
            raise unauthorized("dev mode expects 'Bearer dev:<subject>'")
        subject = token[4:]
        user = _upsert_user(session, "dev", subject, f"{subject}@dev.invalid", subject)
        session.commit()
        return Principal("user", user.id, f"user:dev|{subject}")

    assert settings.oidc_issuer and settings.oidc_audience  # guaranteed by Settings validation
    v = verifier(settings.oidc_issuer, settings.oidc_audience, settings.oidc_jwks_url, tuple(settings.oidc_algorithms))
    try:
        claims = v.verify(token)
    except TokenInvalid as e:
        raise unauthorized("invalid token") from e
    user = _upsert_user(session, claims["iss"], claims["sub"], claims.get("email"), claims.get("name"))
    session.commit()
    return Principal("user", user.id, f"user:{claims['iss']}|{claims['sub']}")


PrincipalDep = Annotated[Principal, Depends(get_principal)]


@dataclass(frozen=True)
class OrgContext:
    org: Organization
    role: str
    principal: Principal


def _deny(principal: Principal, org_id: uuid.UUID | None, action: str, resource: str, reason: str) -> None:
    """Record a denial in its own transaction so it survives the failed request."""
    with session_factory()() as s:
        audit.record(
            s,
            actor=principal.label,
            action=action,
            resource=resource,
            decision="deny",
            organization_id=org_id,
            detail={"reason": reason},
        )
        s.commit()


def org_context(
    request: Request,
    org_slug: Annotated[str, Path(pattern=SLUG)],
    principal: PrincipalDep,
    session: Annotated[Session, Depends(get_session)],
) -> OrgContext:
    org = session.scalar(select(Organization).where(Organization.slug == org_slug))
    role: str | None = None
    if org is not None:
        if principal.kind == "service":
            role = principal.service_role if principal.service_org_id == org.id else None
        else:
            role = session.scalar(
                select(Membership.role).where(Membership.organization_id == org.id, Membership.user_id == principal.id)
            )
    if org is None or role is None:
        _deny(principal, None, f"{request.method} {request.url.path}", f"org:{org_slug}", "not a member")
        raise error(404, "not_found", "organization not found")
    return OrgContext(org, role, principal)


OrgDep = Annotated[OrgContext, Depends(org_context)]


def require_role(ctx: OrgContext, minimum: Role, request: Request) -> None:
    if RANK[ctx.role] < RANK[minimum]:
        _deny(ctx.principal, ctx.org.id, f"{request.method} {request.url.path}", f"org:{ctx.org.slug}", "role")
        raise error(403, "forbidden", f"requires role {minimum}")


def role_at_least(minimum: Role):  # type: ignore[no-untyped-def]
    def dep(ctx: OrgDep, request: Request) -> OrgContext:
        require_role(ctx, minimum, request)
        return ctx

    return dep


ViewerDep = Annotated[OrgContext, Depends(role_at_least("viewer"))]
EngineerDep = Annotated[OrgContext, Depends(role_at_least("engineer"))]
AdminDep = Annotated[OrgContext, Depends(role_at_least("admin"))]


@dataclass(frozen=True)
class ProjectContext:
    org: Organization
    role: str
    principal: Principal
    project: Project


def _project(ctx: OrgContext, project_slug: str, session: Session) -> ProjectContext:
    project = session.scalar(select(Project).where(Project.organization_id == ctx.org.id, Project.slug == project_slug))
    if project is None:
        raise error(404, "not_found", "project not found")
    return ProjectContext(ctx.org, ctx.role, ctx.principal, project)


def project_viewer(
    ctx: ViewerDep,
    project_slug: Annotated[str, Path(pattern=SLUG)],
    session: Annotated[Session, Depends(get_session)],
) -> ProjectContext:
    return _project(ctx, project_slug, session)


def project_engineer(
    ctx: EngineerDep,
    project_slug: Annotated[str, Path(pattern=SLUG)],
    session: Annotated[Session, Depends(get_session)],
) -> ProjectContext:
    return _project(ctx, project_slug, session)


ProjectViewer = Annotated[ProjectContext, Depends(project_viewer)]
ProjectEngineer = Annotated[ProjectContext, Depends(project_engineer)]


def audit_allow(
    session: Session, ctx: OrgContext | ProjectContext, action: str, resource: str, **detail: object
) -> None:
    audit.record(
        session,
        actor=ctx.principal.label,
        action=action,
        resource=resource,
        decision="allow",
        organization_id=ctx.org.id,
        detail=dict(detail),
    )
