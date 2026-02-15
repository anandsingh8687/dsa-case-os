"""Lender submission tracker endpoints."""

from __future__ import annotations

from datetime import date
from typing import Literal, Optional
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.core.deps import CurrentUser
from app.db.database import get_db_session


router = APIRouter(prefix="/submissions", tags=["submissions"])

SubmissionStage = Literal[
    "submitted",
    "query_raised",
    "sanctioned",
    "disbursed",
    "rejected",
    "dropped",
]
QueryStatus = Literal["open", "resolved", "ignored"]


class SubmissionCreateRequest(BaseModel):
    lender_name: str = Field(..., min_length=2, max_length=255)
    product_type: Optional[str] = Field(default=None, max_length=20)
    stage: SubmissionStage = "submitted"
    submitted_date: Optional[date] = None
    sanctioned_amount: Optional[float] = Field(default=None, ge=0)
    disbursed_amount: Optional[float] = Field(default=None, ge=0)
    disbursement_date: Optional[date] = None
    rejection_reason: Optional[str] = Field(default=None, max_length=255)
    notes: Optional[str] = None


class SubmissionUpdateRequest(BaseModel):
    stage: Optional[SubmissionStage] = None
    sanctioned_amount: Optional[float] = Field(default=None, ge=0)
    disbursed_amount: Optional[float] = Field(default=None, ge=0)
    disbursement_date: Optional[date] = None
    rejection_reason: Optional[str] = Field(default=None, max_length=255)
    notes: Optional[str] = None


class SubmissionQueryCreateRequest(BaseModel):
    query_text: str
    response_text: Optional[str] = None
    raised_date: Optional[date] = None
    resolved_date: Optional[date] = None
    status: QueryStatus = "open"


class SubmissionQueryUpdateRequest(BaseModel):
    response_text: Optional[str] = None
    resolved_date: Optional[date] = None
    status: Optional[QueryStatus] = None


async def _resolve_case_uuid(case_id: str, user_id: UUID) -> UUID:
    async with get_db_session() as db:
        row = await db.fetchrow(
            """
            SELECT id
            FROM cases
            WHERE case_id = $1 AND user_id = $2
            LIMIT 1
            """,
            case_id,
            user_id,
        )
    if not row:
        raise HTTPException(status_code=404, detail=f"Case {case_id} not found")
    return row["id"]


@router.get("/case/{case_id}")
async def list_case_submissions(case_id: str, current_user: CurrentUser):
    case_uuid = await _resolve_case_uuid(case_id, current_user.id)

    async with get_db_session() as db:
        submissions = await db.fetch(
            """
            SELECT
                id::text,
                lender_name,
                product_type,
                stage,
                submitted_date,
                sanctioned_amount,
                disbursed_amount,
                disbursement_date,
                rejection_reason,
                notes,
                created_at,
                updated_at
            FROM lender_submissions
            WHERE case_id = $1
            ORDER BY updated_at DESC, created_at DESC
            """,
            case_uuid,
        )

        queries = await db.fetch(
            """
            SELECT
                sq.id::text,
                sq.submission_id::text,
                sq.query_text,
                sq.response_text,
                sq.raised_date,
                sq.resolved_date,
                sq.status,
                sq.created_at
            FROM submission_queries sq
            INNER JOIN lender_submissions ls ON sq.submission_id = ls.id
            WHERE ls.case_id = $1
            ORDER BY sq.created_at DESC
            """,
            case_uuid,
        )

    return {
        "submissions": [dict(row) for row in submissions],
        "queries": [dict(row) for row in queries],
    }


@router.post("/case/{case_id}")
async def create_submission(case_id: str, payload: SubmissionCreateRequest, current_user: CurrentUser):
    case_uuid = await _resolve_case_uuid(case_id, current_user.id)

    async with get_db_session() as db:
        row = await db.fetchrow(
            """
            INSERT INTO lender_submissions (
                case_id,
                lender_name,
                product_type,
                stage,
                submitted_date,
                sanctioned_amount,
                disbursed_amount,
                disbursement_date,
                rejection_reason,
                notes
            ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)
            RETURNING id::text, lender_name, product_type, stage, submitted_date, created_at
            """,
            case_uuid,
            payload.lender_name,
            payload.product_type,
            payload.stage,
            payload.submitted_date,
            payload.sanctioned_amount,
            payload.disbursed_amount,
            payload.disbursement_date,
            payload.rejection_reason,
            payload.notes,
        )

    return {"submission": dict(row)}


@router.patch("/{submission_id}")
async def update_submission(submission_id: UUID, payload: SubmissionUpdateRequest, current_user: CurrentUser):
    update_values = payload.model_dump(exclude_none=True)
    if not update_values:
        raise HTTPException(status_code=400, detail="No fields to update")

    async with get_db_session() as db:
        own = await db.fetchrow(
            """
            SELECT ls.id
            FROM lender_submissions ls
            INNER JOIN cases c ON ls.case_id = c.id
            WHERE ls.id = $1 AND c.user_id = $2
            """,
            submission_id,
            current_user.id,
        )
        if not own:
            raise HTTPException(status_code=404, detail="Submission not found")

        fields = list(update_values.keys())
        set_clause = ", ".join([f"{field} = ${idx + 2}" for idx, field in enumerate(fields)])
        query = f"""
            UPDATE lender_submissions
            SET {set_clause}, updated_at = NOW()
            WHERE id = $1
            RETURNING id::text, lender_name, stage, sanctioned_amount, disbursed_amount, updated_at
        """
        params = [submission_id] + [update_values[field] for field in fields]
        row = await db.fetchrow(query, *params)

    return {"submission": dict(row)}


@router.post("/{submission_id}/queries")
async def add_submission_query(submission_id: UUID, payload: SubmissionQueryCreateRequest, current_user: CurrentUser):
    async with get_db_session() as db:
        own = await db.fetchrow(
            """
            SELECT ls.id
            FROM lender_submissions ls
            INNER JOIN cases c ON ls.case_id = c.id
            WHERE ls.id = $1 AND c.user_id = $2
            """,
            submission_id,
            current_user.id,
        )
        if not own:
            raise HTTPException(status_code=404, detail="Submission not found")

        row = await db.fetchrow(
            """
            INSERT INTO submission_queries (
                submission_id,
                query_text,
                response_text,
                raised_date,
                resolved_date,
                status
            ) VALUES ($1,$2,$3,$4,$5,$6)
            RETURNING id::text, submission_id::text, query_text, response_text, raised_date, resolved_date, status, created_at
            """,
            submission_id,
            payload.query_text,
            payload.response_text,
            payload.raised_date,
            payload.resolved_date,
            payload.status,
        )

        await db.execute(
            """
            UPDATE lender_submissions
            SET stage = CASE WHEN $2 = 'open' THEN 'query_raised' ELSE stage END,
                updated_at = NOW()
            WHERE id = $1
            """,
            submission_id,
            payload.status,
        )

    return {"query": dict(row)}


@router.patch("/queries/{query_id}")
async def update_submission_query(query_id: UUID, payload: SubmissionQueryUpdateRequest, current_user: CurrentUser):
    update_values = payload.model_dump(exclude_none=True)
    if not update_values:
        raise HTTPException(status_code=400, detail="No fields to update")

    async with get_db_session() as db:
        own = await db.fetchrow(
            """
            SELECT sq.id, sq.submission_id
            FROM submission_queries sq
            INNER JOIN lender_submissions ls ON sq.submission_id = ls.id
            INNER JOIN cases c ON ls.case_id = c.id
            WHERE sq.id = $1 AND c.user_id = $2
            """,
            query_id,
            current_user.id,
        )
        if not own:
            raise HTTPException(status_code=404, detail="Query not found")

        fields = list(update_values.keys())
        set_clause = ", ".join([f"{field} = ${idx + 2}" for idx, field in enumerate(fields)])
        query = f"""
            UPDATE submission_queries
            SET {set_clause}
            WHERE id = $1
            RETURNING id::text, submission_id::text, query_text, response_text, raised_date, resolved_date, status, created_at
        """
        params = [query_id] + [update_values[field] for field in fields]
        row = await db.fetchrow(query, *params)

    return {"query": dict(row)}


@router.get("")
async def list_all_submissions(
    current_user: CurrentUser,
    stage: Optional[SubmissionStage] = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
):
    conditions = ["c.user_id = $1"]
    params = [current_user.id]
    if stage:
        conditions.append(f"ls.stage = ${len(params) + 1}")
        params.append(stage)

    where_clause = " AND ".join(conditions)

    async with get_db_session() as db:
        rows = await db.fetch(
            f"""
            SELECT
                ls.id::text,
                c.case_id,
                c.borrower_name,
                ls.lender_name,
                ls.product_type,
                ls.stage,
                ls.sanctioned_amount,
                ls.disbursed_amount,
                ls.submitted_date,
                ls.updated_at
            FROM lender_submissions ls
            INNER JOIN cases c ON ls.case_id = c.id
            WHERE {where_clause}
            ORDER BY ls.updated_at DESC
            LIMIT {limit}
            """,
            *params,
        )

    return {"submissions": [dict(row) for row in rows]}
