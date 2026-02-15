"""Commission calculator and payout tracking endpoints."""

from datetime import date
from typing import Literal, Optional
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.core.deps import CurrentUser
from app.db.database import get_db_session


router = APIRouter(prefix="/commission", tags=["commission"])

LoanType = Literal["BL", "PL", "HL", "LAP"]
PayoutStatus = Literal["pending", "received", "overdue"]


class CommissionRateUpsertRequest(BaseModel):
    lender_name: str = Field(..., min_length=2, max_length=255)
    loan_type: LoanType
    commission_pct: float = Field(..., gt=0, le=100)
    notes: Optional[str] = Field(default=None, max_length=255)


class CommissionCalculationRequest(BaseModel):
    lender_name: str = Field(..., min_length=2, max_length=255)
    loan_type: LoanType
    disbursed_amount: float = Field(..., gt=0)
    commission_pct: Optional[float] = Field(default=None, gt=0, le=100)


class CommissionPayoutUpsertRequest(BaseModel):
    case_id: str = Field(..., min_length=5, max_length=40)
    lender_name: str = Field(..., min_length=2, max_length=255)
    loan_type: LoanType
    disbursed_amount: float = Field(..., gt=0)
    disbursement_date: date
    expected_payout_date: Optional[date] = None
    actual_payout_date: Optional[date] = None
    payout_status: PayoutStatus = "pending"
    commission_pct: Optional[float] = Field(default=None, gt=0, le=100)


async def _resolve_commission_pct(
    user_id: UUID,
    lender_name: str,
    loan_type: LoanType,
    explicit_pct: Optional[float] = None,
) -> float:
    if explicit_pct is not None:
        return float(explicit_pct)

    async with get_db_session() as db:
        pct = await db.fetchval(
            """
            SELECT commission_pct
            FROM dsa_commission_rates
            WHERE user_id = $1
              AND LOWER(lender_name) = LOWER($2)
              AND loan_type = $3
            LIMIT 1
            """,
            user_id,
            lender_name,
            loan_type,
        )

    if pct is None:
        raise HTTPException(
            status_code=400,
            detail=(
                f"No commission rate set for {lender_name} ({loan_type}). "
                "Add a rate first or provide commission_pct in request."
            ),
        )

    return float(pct)


@router.get("/rates")
async def list_commission_rates(current_user: CurrentUser):
    async with get_db_session() as db:
        rows = await db.fetch(
            """
            SELECT id::text, lender_name, loan_type, commission_pct, notes, updated_at
            FROM dsa_commission_rates
            WHERE user_id = $1
            ORDER BY lender_name ASC, loan_type ASC
            """,
            current_user.id,
        )

    return {"rates": [dict(row) for row in rows]}


@router.post("/rates")
async def upsert_commission_rate(payload: CommissionRateUpsertRequest, current_user: CurrentUser):
    async with get_db_session() as db:
        row = await db.fetchrow(
            """
            INSERT INTO dsa_commission_rates (user_id, lender_name, loan_type, commission_pct, notes)
            VALUES ($1, $2, $3, $4, $5)
            ON CONFLICT (user_id, lender_name, loan_type)
            DO UPDATE SET
                commission_pct = EXCLUDED.commission_pct,
                notes = EXCLUDED.notes,
                updated_at = NOW()
            RETURNING id::text, lender_name, loan_type, commission_pct, notes, updated_at
            """,
            current_user.id,
            payload.lender_name.strip(),
            payload.loan_type,
            float(payload.commission_pct),
            payload.notes,
        )

    return {"rate": dict(row)}


@router.delete("/rates/{rate_id}")
async def delete_commission_rate(rate_id: UUID, current_user: CurrentUser):
    async with get_db_session() as db:
        deleted = await db.execute(
            """
            DELETE FROM dsa_commission_rates
            WHERE id = $1 AND user_id = $2
            """,
            rate_id,
            current_user.id,
        )

    if deleted == "DELETE 0":
        raise HTTPException(status_code=404, detail="Commission rate not found")

    return {"deleted": True}


@router.post("/calculate")
async def calculate_commission(payload: CommissionCalculationRequest, current_user: CurrentUser):
    pct = await _resolve_commission_pct(
        user_id=current_user.id,
        lender_name=payload.lender_name,
        loan_type=payload.loan_type,
        explicit_pct=payload.commission_pct,
    )

    commission_amount = round(float(payload.disbursed_amount) * pct / 100.0, 2)
    return {
        "lender_name": payload.lender_name,
        "loan_type": payload.loan_type,
        "disbursed_amount": float(payload.disbursed_amount),
        "commission_pct": pct,
        "commission_amount": commission_amount,
    }


@router.post("/payouts")
async def upsert_commission_payout(payload: CommissionPayoutUpsertRequest, current_user: CurrentUser):
    pct = await _resolve_commission_pct(
        user_id=current_user.id,
        lender_name=payload.lender_name,
        loan_type=payload.loan_type,
        explicit_pct=payload.commission_pct,
    )
    commission_amount = round(float(payload.disbursed_amount) * pct / 100.0, 2)

    async with get_db_session() as db:
        case_row = await db.fetchrow(
            """
            SELECT id
            FROM cases
            WHERE case_id = $1 AND user_id = $2
            LIMIT 1
            """,
            payload.case_id,
            current_user.id,
        )
        if not case_row:
            raise HTTPException(status_code=404, detail=f"Case {payload.case_id} not found")

        case_uuid = case_row["id"]

        existing = await db.fetchrow(
            """
            SELECT id
            FROM commission_payouts
            WHERE case_id = $1
              AND user_id = $2
              AND LOWER(COALESCE(lender_name, '')) = LOWER($3)
            LIMIT 1
            """,
            case_uuid,
            current_user.id,
            payload.lender_name,
        )

        if existing:
            row = await db.fetchrow(
                """
                UPDATE commission_payouts
                SET
                    lender_name = $2,
                    disbursed_amount = $3,
                    commission_pct = $4,
                    commission_amount = $5,
                    disbursement_date = $6,
                    expected_payout_date = $7,
                    actual_payout_date = $8,
                    payout_status = $9
                WHERE id = $1
                RETURNING id::text, lender_name, disbursed_amount, commission_pct,
                          commission_amount, disbursement_date, expected_payout_date,
                          actual_payout_date, payout_status, created_at
                """,
                existing["id"],
                payload.lender_name,
                float(payload.disbursed_amount),
                pct,
                commission_amount,
                payload.disbursement_date,
                payload.expected_payout_date,
                payload.actual_payout_date,
                payload.payout_status,
            )
        else:
            row = await db.fetchrow(
                """
                INSERT INTO commission_payouts (
                    case_id,
                    user_id,
                    lender_name,
                    disbursed_amount,
                    commission_pct,
                    commission_amount,
                    disbursement_date,
                    expected_payout_date,
                    actual_payout_date,
                    payout_status
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
                RETURNING id::text, lender_name, disbursed_amount, commission_pct,
                          commission_amount, disbursement_date, expected_payout_date,
                          actual_payout_date, payout_status, created_at
                """,
                case_uuid,
                current_user.id,
                payload.lender_name,
                float(payload.disbursed_amount),
                pct,
                commission_amount,
                payload.disbursement_date,
                payload.expected_payout_date,
                payload.actual_payout_date,
                payload.payout_status,
            )

    return {
        "case_id": payload.case_id,
        "loan_type": payload.loan_type,
        "payout": dict(row),
    }


@router.get("/payouts")
async def list_commission_payouts(
    current_user: CurrentUser,
    status: Optional[PayoutStatus] = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
):
    conditions = ["cp.user_id = $1"]
    params = [current_user.id]
    if status:
        conditions.append(f"cp.payout_status = ${len(params) + 1}")
        params.append(status)

    where_clause = " AND ".join(conditions)

    async with get_db_session() as db:
        rows = await db.fetch(
            f"""
            SELECT
                cp.id::text,
                c.case_id,
                c.borrower_name,
                c.program_type,
                cp.lender_name,
                cp.disbursed_amount,
                cp.commission_pct,
                cp.commission_amount,
                cp.disbursement_date,
                cp.expected_payout_date,
                cp.actual_payout_date,
                cp.payout_status,
                cp.created_at
            FROM commission_payouts cp
            INNER JOIN cases c ON cp.case_id = c.id
            WHERE {where_clause}
            ORDER BY cp.created_at DESC
            LIMIT {limit}
            """,
            *params,
        )

    return {"payouts": [dict(row) for row in rows]}


@router.get("/overview")
async def commission_overview(current_user: CurrentUser):
    async with get_db_session() as db:
        summary_row = await db.fetchrow(
            """
            SELECT
                COUNT(*) AS total_records,
                COALESCE(SUM(CASE WHEN payout_status = 'received' THEN commission_amount ELSE 0 END), 0) AS total_received,
                COALESCE(SUM(CASE WHEN payout_status = 'pending' THEN commission_amount ELSE 0 END), 0) AS pending_amount,
                COALESCE(SUM(CASE WHEN payout_status = 'overdue' THEN commission_amount ELSE 0 END), 0) AS overdue_amount,
                COALESCE(SUM(commission_amount), 0) AS projected_total
            FROM commission_payouts
            WHERE user_id = $1
            """,
            current_user.id,
        )

        monthly_rows = await db.fetch(
            """
            SELECT
                TO_CHAR(DATE_TRUNC('month', COALESCE(actual_payout_date::timestamp, disbursement_date::timestamp, created_at)), 'YYYY-MM') AS month,
                COALESCE(SUM(commission_amount), 0) AS amount
            FROM commission_payouts
            WHERE user_id = $1
            GROUP BY 1
            ORDER BY 1 DESC
            LIMIT 6
            """,
            current_user.id,
        )

        rate_count = await db.fetchval(
            """
            SELECT COUNT(*)
            FROM dsa_commission_rates
            WHERE user_id = $1
            """,
            current_user.id,
        )

    return {
        "summary": dict(summary_row) if summary_row else {},
        "rate_count": int(rate_count or 0),
        "monthly_trend": [dict(row) for row in monthly_rows],
    }
