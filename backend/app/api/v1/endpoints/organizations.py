"""Organization and RBAC management endpoints."""

from __future__ import annotations

import re
from typing import Annotated, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import CurrentDSAOwnerOrSuperAdmin, CurrentSuperAdmin, CurrentUser
from app.core.security import hash_password
from app.db.database import get_db
from app.models.organization import Organization
from app.models.user import User

router = APIRouter(prefix="/organizations", tags=["organizations"])


class OrganizationCreateRequest(BaseModel):
    name: str
    slug: Optional[str] = None


class UserCreateRequest(BaseModel):
    email: EmailStr
    password: str
    full_name: str
    phone: Optional[str] = None
    role: Optional[str] = None


def _slugify(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-") or "org"


@router.get("")
async def list_organizations(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: CurrentSuperAdmin,
):
    rows = await db.execute(select(Organization).order_by(Organization.created_at.desc()))
    organizations = rows.scalars().all()
    return [
        {
            "id": str(org.id),
            "name": org.name,
            "slug": org.slug,
            "is_active": org.is_active,
            "created_at": org.created_at,
        }
        for org in organizations
    ]


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_organization(
    payload: OrganizationCreateRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: CurrentSuperAdmin,
):
    slug_base = _slugify(payload.slug or payload.name)
    slug = slug_base
    suffix = 1
    while True:
        existing = await db.execute(select(Organization).where(Organization.slug == slug))
        if not existing.scalar_one_or_none():
            break
        suffix += 1
        slug = f"{slug_base}-{suffix}"

    org = Organization(name=payload.name.strip(), slug=slug, created_by=current_user.id)
    db.add(org)
    await db.commit()
    await db.refresh(org)
    return {"id": str(org.id), "name": org.name, "slug": org.slug}


@router.post("/{organization_id}/owners", status_code=status.HTTP_201_CREATED)
async def create_dsa_owner(
    organization_id: UUID,
    payload: UserCreateRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: CurrentSuperAdmin,
):
    org = await db.get(Organization, organization_id)
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")

    existing = await db.execute(select(User).where(User.email == payload.email))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Email already registered")

    user = User(
        email=str(payload.email),
        hashed_password=hash_password(payload.password),
        full_name=payload.full_name.strip(),
        phone=payload.phone,
        role="dsa_owner",
        organization=org.name,
        organization_id=org.id,
        is_active=True,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return {"id": str(user.id), "email": user.email, "role": user.role, "organization_id": str(org.id)}


@router.post("/{organization_id}/agents", status_code=status.HTTP_201_CREATED)
async def create_agent(
    organization_id: UUID,
    payload: UserCreateRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: CurrentDSAOwnerOrSuperAdmin,
):
    org = await db.get(Organization, organization_id)
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")

    if current_user.role != "super_admin" and current_user.organization_id != org.id:
        raise HTTPException(status_code=403, detail="You can only manage users within your organization")

    existing = await db.execute(select(User).where(User.email == payload.email))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Email already registered")

    role = payload.role or "agent"
    if role not in {"agent", "dsa_owner"}:
        role = "agent"
    if current_user.role != "super_admin":
        role = "agent"

    user = User(
        email=str(payload.email),
        hashed_password=hash_password(payload.password),
        full_name=payload.full_name.strip(),
        phone=payload.phone,
        role=role,
        organization=org.name,
        organization_id=org.id,
        is_active=True,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return {"id": str(user.id), "email": user.email, "role": user.role, "organization_id": str(org.id)}


@router.get("/me/users")
async def list_my_organization_users(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: CurrentDSAOwnerOrSuperAdmin,
):
    if current_user.role == "super_admin":
        raise HTTPException(status_code=400, detail="Super admin should query /organizations and org-specific users.")
    if not current_user.organization_id:
        return []
    rows = await db.execute(
        select(User)
        .where(User.organization_id == current_user.organization_id)
        .order_by(User.created_at.desc())
    )
    users = rows.scalars().all()
    return [
        {
            "id": str(u.id),
            "email": u.email,
            "full_name": u.full_name,
            "role": u.role,
            "is_active": u.is_active,
            "created_at": u.created_at,
        }
        for u in users
    ]

