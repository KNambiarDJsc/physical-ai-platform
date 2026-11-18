from __future__ import annotations

import secrets
import uuid
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..audit import AuditEvent
from ..auth.deps import (
    SERVICE_PREFIX,
    SLUG,
    AdminDep,
    PrincipalDep,
    Role,
    ViewerDep,
    _deny,
    audit_allow,
    error,
    token_sha256,
)
from ..auth.models import User
from ..config import Settings, get_settings
from ..db import get_session, utcnow
from .models import Membership, Organization, ServiceCredential

router = APIRouter(prefix="/api/v1", tags=["organizations"])
SessionDep = Annotated[Session, Depends(get_session)]


class OrgIn(BaseModel):
    slug: str = Field(pattern=SLUG)
    name: str = Field(min_length=1, max_length=200)


class OrgOut(BaseModel):
    id: uuid.UUID
    slug: str
    name: str
    role: str


class MemberIn(BaseModel):
    issuer: str = Field(min_length=1, max_length=512)
    subject: str = Field(min_length=1, max_length=255)
    role: Role


class MemberOut(BaseModel):
    user_id: uuid.UUID
    issuer: str
    subject: str
    email: str | None
    role: str


class RoleIn(BaseModel):
    role: Role


class CredentialIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    role: Role


class CredentialOut(BaseModel):
    id: uuid.UUID
    name: str
    role: str
    token_prefix: str
    created_at: datetime
    revoked_at: datetime | None
    last_used_at: datetime | None


class CredentialCreated(CredentialOut):
    token: str = Field(description="Shown once. Only its SHA-256 is stored.")


class AuditOut(BaseModel):
    id: int
    at: datetime
    actor: str
    action: str
    resource: str
    decision: str
    detail: dict[str, Any]


@router.get("/me")
def me(principal: PrincipalDep, session: SessionDep) -> dict[str, Any]:
    if principal.kind == "service":
        org = session.get(Organization, principal.service_org_id)
        orgs = [{"slug": org.slug, "role": principal.service_role}] if org else []
        return {"kind": "service", "label": principal.label, "organizations": orgs}
    user = session.get(User, principal.id)
    assert user is not None
    rows = session.execute(
        select(Organization.slug, Membership.role)
        .join(Membership, Membership.organization_id == Organization.id)
        .where(Membership.user_id == user.id)
        .order_by(Organization.slug)
    ).all()
    return {
        "kind": "user",
        "id": str(user.id),
        "issuer": user.issuer,
        "subject": user.subject,
        "email": user.email,
        "organizations": [{"slug": s, "role": r} for s, r in rows],
    }


@router.post("/orgs", status_code=201)
def create_org(
    body: OrgIn,
    principal: PrincipalDep,
    session: SessionDep,
    settings: Annotated[Settings, Depends(get_settings)],
    request: Request,
) -> OrgOut:
    if principal.kind != "user" or not settings.allow_org_creation:
        _deny(principal, None, "POST /api/v1/orgs", f"org:{body.slug}", "org creation not allowed")
        raise error(403, "forbidden", "organization creation is not allowed for this caller")
    org = Organization(slug=body.slug, name=body.name)
    session.add(org)
    try:
        session.flush()
    except IntegrityError as e:
        session.rollback()
        raise error(409, "conflict", "organization slug is taken") from e
    session.add(Membership(organization_id=org.id, user_id=principal.id, role="admin"))
    session.add(
        AuditEvent(
            organization_id=org.id,
            actor=principal.label,
            action="org.create",
            resource=f"org:{org.slug}",
            decision="allow",
            detail={},
        )
    )
    session.commit()
    return OrgOut(id=org.id, slug=org.slug, name=org.name, role="admin")


@router.get("/orgs/{org_slug}")
def get_org(ctx: ViewerDep) -> OrgOut:
    return OrgOut(id=ctx.org.id, slug=ctx.org.slug, name=ctx.org.name, role=ctx.role)


@router.get("/orgs/{org_slug}/members")
def list_members(ctx: ViewerDep, session: SessionDep) -> list[MemberOut]:
    rows = session.execute(
        select(User, Membership.role)
        .join(Membership, Membership.user_id == User.id)
        .where(Membership.organization_id == ctx.org.id)
        .order_by(User.issuer, User.subject)
    ).all()
    return [MemberOut(user_id=u.id, issuer=u.issuer, subject=u.subject, email=u.email, role=r) for u, r in rows]


@router.put("/orgs/{org_slug}/members", status_code=200)
def put_member(body: MemberIn, ctx: AdminDep, session: SessionDep) -> MemberOut:
    """Add a user (by identity provider issuer and subject) or change their role."""
    user = session.scalar(select(User).where(User.issuer == body.issuer, User.subject == body.subject))
    if user is None:
        user = User(issuer=body.issuer, subject=body.subject)
        session.add(user)
        session.flush()
    m = session.scalar(
        select(Membership).where(Membership.organization_id == ctx.org.id, Membership.user_id == user.id)
    )
    if m is None:
        m = Membership(organization_id=ctx.org.id, user_id=user.id, role=body.role)
        session.add(m)
    else:
        _keep_an_admin(session, ctx.org.id, m, body.role)
        m.role = body.role
    audit_allow(session, ctx, "member.put", f"user:{user.id}", role=body.role)
    session.commit()
    return MemberOut(user_id=user.id, issuer=user.issuer, subject=user.subject, email=user.email, role=m.role)


@router.delete("/orgs/{org_slug}/members/{user_id}", status_code=204)
def delete_member(user_id: uuid.UUID, ctx: AdminDep, session: SessionDep) -> None:
    m = session.scalar(
        select(Membership).where(Membership.organization_id == ctx.org.id, Membership.user_id == user_id)
    )
    if m is None:
        raise error(404, "not_found", "member not found")
    _keep_an_admin(session, ctx.org.id, m, None)
    session.delete(m)
    audit_allow(session, ctx, "member.delete", f"user:{user_id}")
    session.commit()


def _keep_an_admin(session: Session, org_id: uuid.UUID, m: Membership, new_role: str | None) -> None:
    if m.role == "admin" and new_role != "admin":
        admins = session.scalar(
            select(func.count()).where(Membership.organization_id == org_id, Membership.role == "admin")
        )
        if (admins or 0) <= 1:
            raise error(409, "conflict", "an organization needs at least one admin")


@router.post("/orgs/{org_slug}/service-credentials", status_code=201)
def create_credential(body: CredentialIn, ctx: AdminDep, session: SessionDep) -> CredentialCreated:
    token = SERVICE_PREFIX + secrets.token_urlsafe(32)
    cred = ServiceCredential(
        organization_id=ctx.org.id,
        name=body.name,
        role=body.role,
        token_sha256=token_sha256(token),
        token_prefix=token[:12],
        created_by=ctx.principal.id if ctx.principal.kind == "user" else None,
    )
    session.add(cred)
    session.flush()
    audit_allow(session, ctx, "credential.create", f"credential:{cred.id}", role=body.role)
    session.commit()
    return CredentialCreated(**_cred(cred).model_dump(), token=token)


@router.get("/orgs/{org_slug}/service-credentials")
def list_credentials(ctx: AdminDep, session: SessionDep) -> list[CredentialOut]:
    rows = session.scalars(
        select(ServiceCredential)
        .where(ServiceCredential.organization_id == ctx.org.id)
        .order_by(ServiceCredential.created_at)
    )
    return [_cred(c) for c in rows]


@router.delete("/orgs/{org_slug}/service-credentials/{credential_id}", status_code=204)
def revoke_credential(credential_id: uuid.UUID, ctx: AdminDep, session: SessionDep) -> None:
    cred = session.scalar(
        select(ServiceCredential).where(
            ServiceCredential.id == credential_id, ServiceCredential.organization_id == ctx.org.id
        )
    )
    if cred is None:
        raise error(404, "not_found", "credential not found")
    if cred.revoked_at is None:
        cred.revoked_at = utcnow()
    audit_allow(session, ctx, "credential.revoke", f"credential:{cred.id}")
    session.commit()


def _cred(c: ServiceCredential) -> CredentialOut:
    return CredentialOut(
        id=c.id,
        name=c.name,
        role=c.role,
        token_prefix=c.token_prefix,
        created_at=c.created_at,
        revoked_at=c.revoked_at,
        last_used_at=c.last_used_at,
    )


@router.get("/orgs/{org_slug}/audit-events")
def list_audit(ctx: AdminDep, session: SessionDep, limit: Annotated[int, Query(ge=1, le=500)] = 100) -> list[AuditOut]:
    rows = session.scalars(
        select(AuditEvent).where(AuditEvent.organization_id == ctx.org.id).order_by(AuditEvent.id.desc()).limit(limit)
    )
    return [
        AuditOut(
            id=e.id, at=e.at, actor=e.actor, action=e.action, resource=e.resource, decision=e.decision, detail=e.detail
        )
        for e in rows
    ]
