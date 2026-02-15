"""Lead CRM endpoints."""

from __future__ import annotations

from datetime import date
from typing import Literal, Optional
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.core.deps import CurrentUser
from app.db.database import get_db_session


router = APIRouter(prefix="/leads", tags=["leads"])

LeadStage = Literal[
    "new",
    "contacted",
    "qualified",
    "doc_collection",
    "converted",
    "lost",
]
ActivityType = Literal["call", "whatsapp", "email", "note", "stage_change"]


class LeadCreateRequest(BaseModel):
    customer_name: str = Field(..., min_length=2, max_length=255)
    phone: Optional[str] = Field(default=None, max_length=20)
    email: Optional[str] = Field(default=None, max_length=255)
    loan_type_interest: Optional[str] = Field(default="BL", max_length=20)
    loan_amount_approx: Optional[float] = Field(default=None, gt=0)
    city: Optional[str] = Field(default=None, max_length=100)
    pincode: Optional[str] = Field(default=None, max_length=10)
    source: Optional[str] = Field(default="manual", max_length=20)
    stage: LeadStage = "new"
    next_followup_date: Optional[date] = None


class LeadUpdateRequest(BaseModel):
    customer_name: Optional[str] = Field(default=None, min_length=2, max_length=255)
    phone: Optional[str] = Field(default=None, max_length=20)
    email: Optional[str] = Field(default=None, max_length=255)
    loan_type_interest: Optional[str] = Field(default=None, max_length=20)
    loan_amount_approx: Optional[float] = Field(default=None, gt=0)
    city: Optional[str] = Field(default=None, max_length=100)
    pincode: Optional[str] = Field(default=None, max_length=10)
    source: Optional[str] = Field(default=None, max_length=20)
    stage: Optional[LeadStage] = None
    next_followup_date: Optional[date] = None


class LeadActivityCreateRequest(BaseModel):
    activity_type: ActivityType
    notes: Optional[str] = None
    call_outcome: Optional[str] = Field(default=None, max_length=30)


@router.get("")
async def list_leads(
    current_user: CurrentUser,
    stage: Optional[LeadStage] = Query(default=None),
    q: Optional[str] = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
):
    conditions = ["(created_by = $1 OR assigned_to = $1)"]
    params = [current_user.id]

    if stage:
        conditions.append(f"stage = ${len(params) + 1}")
        params.append(stage)

    if q:
        conditions.append(f"(customer_name ILIKE ${len(params) + 1} OR phone ILIKE ${len(params) + 1} OR email ILIKE ${len(params) + 1})")
        params.append(f"%{q}%")

    where_clause = " AND ".join(conditions)

    async with get_db_session() as db:
        rows = await db.fetch(
            f"""
            SELECT
                id::text,
                customer_name,
                phone,
                email,
                loan_type_interest,
                loan_amount_approx,
                city,
                pincode,
                source,
                stage,
                case_id::text AS case_id,
                next_followup_date,
                last_activity_at,
                created_at,
                updated_at
            FROM leads
            WHERE {where_clause}
            ORDER BY updated_at DESC, created_at DESC
            LIMIT {limit}
            """,
            *params,
        )

    return {"leads": [dict(row) for row in rows]}


@router.post("")
async def create_lead(payload: LeadCreateRequest, current_user: CurrentUser):
    async with get_db_session() as db:
        row = await db.fetchrow(
            """
            INSERT INTO leads (
                assigned_to,
                customer_name,
                phone,
                email,
                loan_type_interest,
                loan_amount_approx,
                city,
                pincode,
                source,
                stage,
                next_followup_date,
                created_by,
                last_activity_at
            ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,NOW())
            RETURNING id::text, customer_name, stage, created_at
            """,
            current_user.id,
            payload.customer_name,
            payload.phone,
            payload.email,
            payload.loan_type_interest,
            payload.loan_amount_approx,
            payload.city,
            payload.pincode,
            payload.source,
            payload.stage,
            payload.next_followup_date,
            current_user.id,
        )

        await db.execute(
            """
            INSERT INTO lead_activities (lead_id, user_id, activity_type, notes, call_outcome)
            VALUES ($1, $2, 'note', 'Lead created', NULL)
            """,
            row["id"],
            current_user.id,
        )

    return {"lead": dict(row)}


@router.patch("/{lead_id}")
async def update_lead(lead_id: UUID, payload: LeadUpdateRequest, current_user: CurrentUser):
    update_values = payload.model_dump(exclude_none=True)
    if not update_values:
        raise HTTPException(status_code=400, detail="No fields to update")

    async with get_db_session() as db:
        ownership = await db.fetchrow(
            """
            SELECT id
            FROM leads
            WHERE id = $1 AND (created_by = $2 OR assigned_to = $2)
            """,
            lead_id,
            current_user.id,
        )
        if not ownership:
            raise HTTPException(status_code=404, detail="Lead not found")

        fields = list(update_values.keys())
        set_clause = ", ".join([f"{field} = ${idx + 3}" for idx, field in enumerate(fields)])
        query = f"""
            UPDATE leads
            SET {set_clause}, updated_at = NOW(), last_activity_at = NOW()
            WHERE id = $1 AND (created_by = $2 OR assigned_to = $2)
            RETURNING id::text, customer_name, stage, updated_at
        """

        params = [lead_id, current_user.id] + [update_values[field] for field in fields]
        row = await db.fetchrow(query, *params)
        if not row:
            raise HTTPException(status_code=404, detail="Lead not found")

        if "stage" in update_values:
            await db.execute(
                """
                INSERT INTO lead_activities (lead_id, user_id, activity_type, notes, call_outcome)
                VALUES ($1, $2, 'stage_change', $3, NULL)
                """,
                lead_id,
                current_user.id,
                f"Stage updated to {update_values['stage']}",
            )

    return {"lead": dict(row)}


@router.get("/{lead_id}/activities")
async def list_lead_activities(lead_id: UUID, current_user: CurrentUser):
    async with get_db_session() as db:
        ownership = await db.fetchrow(
            """
            SELECT id
            FROM leads
            WHERE id = $1 AND (created_by = $2 OR assigned_to = $2)
            """,
            lead_id,
            current_user.id,
        )
        if not ownership:
            raise HTTPException(status_code=404, detail="Lead not found")

        rows = await db.fetch(
            """
            SELECT
                id::text,
                activity_type,
                notes,
                call_outcome,
                created_at
            FROM lead_activities
            WHERE lead_id = $1
            ORDER BY created_at DESC
            """,
            lead_id,
        )

    return {"activities": [dict(row) for row in rows]}


@router.post("/{lead_id}/activities")
async def add_lead_activity(lead_id: UUID, payload: LeadActivityCreateRequest, current_user: CurrentUser):
    async with get_db_session() as db:
        ownership = await db.fetchrow(
            """
            SELECT id
            FROM leads
            WHERE id = $1 AND (created_by = $2 OR assigned_to = $2)
            """,
            lead_id,
            current_user.id,
        )
        if not ownership:
            raise HTTPException(status_code=404, detail="Lead not found")

        row = await db.fetchrow(
            """
            INSERT INTO lead_activities (lead_id, user_id, activity_type, notes, call_outcome)
            VALUES ($1, $2, $3, $4, $5)
            RETURNING id::text, activity_type, notes, call_outcome, created_at
            """,
            lead_id,
            current_user.id,
            payload.activity_type,
            payload.notes,
            payload.call_outcome,
        )

        await db.execute(
            """
            UPDATE leads
            SET last_activity_at = NOW(), updated_at = NOW()
            WHERE id = $1
            """,
            lead_id,
        )

    return {"activity": dict(row)}
