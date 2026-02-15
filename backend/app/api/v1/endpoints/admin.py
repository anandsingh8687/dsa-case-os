"""Admin endpoints for platform operations dashboard."""

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import httpx
from fastapi import APIRouter, Query
from pydantic import BaseModel

from app.core.config import settings
from app.core.deps import CurrentAdmin
from app.db.database import get_db_session


router = APIRouter(prefix="/admin", tags=["admin"])


class PlatformStats(BaseModel):
    users_total: int
    users_active: int
    users_created_7d: int
    cases_total: int
    cases_created_7d: int
    cases_created_24h: int
    documents_total: int
    reports_generated: int
    eligibility_runs: int
    avg_case_completeness: float
    status_distribution: Dict[str, int]


class UserOpsRow(BaseModel):
    id: str
    email: str
    full_name: str
    role: str
    organization: Optional[str] = None
    is_active: bool
    created_at: datetime
    case_count: int
    latest_case_at: Optional[datetime] = None


class CaseOpsRow(BaseModel):
    id: str
    case_id: str
    borrower_name: Optional[str] = None
    status: str
    program_type: Optional[str] = None
    completeness_score: float
    user_email: str
    created_at: datetime
    updated_at: datetime


class AdminHealthStatus(BaseModel):
    database_ok: bool
    llm_configured: bool
    whatsapp_service_ok: bool
    whatsapp_service_status: Optional[int] = None
    checked_at: datetime


@router.get("/stats", response_model=PlatformStats)
async def get_platform_stats(current_user: CurrentAdmin):
    """Aggregated platform metrics for admin dashboard."""
    now = datetime.now(timezone.utc)
    seven_days_ago = now - timedelta(days=7)
    one_day_ago = now - timedelta(hours=24)

    async with get_db_session() as db:
        users_total = await db.fetchval("SELECT COUNT(*) FROM users")
        users_active = await db.fetchval("SELECT COUNT(*) FROM users WHERE is_active = TRUE")
        users_created_7d = await db.fetchval(
            "SELECT COUNT(*) FROM users WHERE created_at >= $1",
            seven_days_ago,
        )

        cases_total = await db.fetchval("SELECT COUNT(*) FROM cases")
        cases_created_7d = await db.fetchval(
            "SELECT COUNT(*) FROM cases WHERE created_at >= $1",
            seven_days_ago,
        )
        cases_created_24h = await db.fetchval(
            "SELECT COUNT(*) FROM cases WHERE created_at >= $1",
            one_day_ago,
        )

        documents_total = await db.fetchval("SELECT COUNT(*) FROM documents")
        reports_generated = await db.fetchval(
            "SELECT COUNT(*) FROM cases WHERE status = 'report_generated'"
        )
        eligibility_runs = await db.fetchval(
            "SELECT COUNT(DISTINCT case_id) FROM eligibility_results"
        )
        avg_case_completeness = await db.fetchval(
            "SELECT COALESCE(AVG(completeness_score), 0) FROM cases"
        )

        status_rows = await db.fetch(
            """
            SELECT status, COUNT(*) as count
            FROM cases
            GROUP BY status
            ORDER BY count DESC
            """
        )

    status_distribution = {row["status"]: int(row["count"]) for row in status_rows}

    return PlatformStats(
        users_total=int(users_total or 0),
        users_active=int(users_active or 0),
        users_created_7d=int(users_created_7d or 0),
        cases_total=int(cases_total or 0),
        cases_created_7d=int(cases_created_7d or 0),
        cases_created_24h=int(cases_created_24h or 0),
        documents_total=int(documents_total or 0),
        reports_generated=int(reports_generated or 0),
        eligibility_runs=int(eligibility_runs or 0),
        avg_case_completeness=float(avg_case_completeness or 0.0),
        status_distribution=status_distribution,
    )


@router.get("/users", response_model=List[UserOpsRow])
async def list_users_ops(
    current_user: CurrentAdmin,
    q: Optional[str] = Query(None, description="Search by user name/email"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    """User operations view with activity metadata."""
    search_pattern = f"%{q.strip()}%" if q else None

    async with get_db_session() as db:
        if search_pattern:
            rows = await db.fetch(
                """
                SELECT
                    u.id::text,
                    u.email,
                    u.full_name,
                    u.role,
                    u.organization,
                    u.is_active,
                    u.created_at,
                    COUNT(c.id) as case_count,
                    MAX(c.created_at) as latest_case_at
                FROM users u
                LEFT JOIN cases c ON c.user_id = u.id
                WHERE u.email ILIKE $1 OR u.full_name ILIKE $1
                GROUP BY u.id
                ORDER BY u.created_at DESC
                LIMIT $2 OFFSET $3
                """,
                search_pattern,
                limit,
                offset,
            )
        else:
            rows = await db.fetch(
                """
                SELECT
                    u.id::text,
                    u.email,
                    u.full_name,
                    u.role,
                    u.organization,
                    u.is_active,
                    u.created_at,
                    COUNT(c.id) as case_count,
                    MAX(c.created_at) as latest_case_at
                FROM users u
                LEFT JOIN cases c ON c.user_id = u.id
                GROUP BY u.id
                ORDER BY u.created_at DESC
                LIMIT $1 OFFSET $2
                """,
                limit,
                offset,
            )

    return [
        UserOpsRow(
            id=row["id"],
            email=row["email"],
            full_name=row["full_name"],
            role=row["role"],
            organization=row["organization"],
            is_active=bool(row["is_active"]),
            created_at=row["created_at"],
            case_count=int(row["case_count"] or 0),
            latest_case_at=row["latest_case_at"],
        )
        for row in rows
    ]


@router.get("/cases", response_model=List[CaseOpsRow])
async def list_cases_ops(
    current_user: CurrentAdmin,
    status: Optional[str] = Query(None, description="Filter by case status"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    """Cross-organization case operations view."""
    async with get_db_session() as db:
        if status:
            rows = await db.fetch(
                """
                SELECT
                    c.id::text,
                    c.case_id,
                    c.borrower_name,
                    c.status,
                    c.program_type,
                    c.completeness_score,
                    u.email as user_email,
                    c.created_at,
                    c.updated_at
                FROM cases c
                INNER JOIN users u ON u.id = c.user_id
                WHERE c.status = $1
                ORDER BY c.created_at DESC
                LIMIT $2 OFFSET $3
                """,
                status,
                limit,
                offset,
            )
        else:
            rows = await db.fetch(
                """
                SELECT
                    c.id::text,
                    c.case_id,
                    c.borrower_name,
                    c.status,
                    c.program_type,
                    c.completeness_score,
                    u.email as user_email,
                    c.created_at,
                    c.updated_at
                FROM cases c
                INNER JOIN users u ON u.id = c.user_id
                ORDER BY c.created_at DESC
                LIMIT $1 OFFSET $2
                """,
                limit,
                offset,
            )

    return [
        CaseOpsRow(
            id=row["id"],
            case_id=row["case_id"],
            borrower_name=row["borrower_name"],
            status=row["status"],
            program_type=row["program_type"],
            completeness_score=float(row["completeness_score"] or 0.0),
            user_email=row["user_email"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
        for row in rows
    ]


@router.get("/logs")
async def get_operational_logs(
    current_user: CurrentAdmin,
    days: int = Query(7, ge=1, le=30),
):
    """
    Lightweight operational logs from DB signals.

    This endpoint surfaces failure-oriented operational evidence without requiring
    direct filesystem log access in Railway runtime.
    """
    since = datetime.now(timezone.utc) - timedelta(days=days)

    async with get_db_session() as db:
        failed_cases = await db.fetch(
            """
            SELECT case_id, borrower_name, updated_at
            FROM cases
            WHERE status = 'failed' AND updated_at >= $1
            ORDER BY updated_at DESC
            LIMIT 100
            """,
            since,
        )

        unreadable_docs = await db.fetch(
            """
            SELECT c.case_id, d.original_filename, d.status, d.doc_type, d.created_at
            FROM documents d
            INNER JOIN cases c ON c.id = d.case_id
            WHERE d.created_at >= $1 AND (d.doc_type = 'unknown' OR d.status IN ('uploaded', 'ocr_complete'))
            ORDER BY d.created_at DESC
            LIMIT 200
            """,
            since,
        )

    return {
        "window_days": days,
        "failed_cases": [dict(r) for r in failed_cases],
        "classification_watchlist": [dict(r) for r in unreadable_docs],
    }


@router.get("/health", response_model=AdminHealthStatus)
async def get_admin_health(current_user: CurrentAdmin):
    """Service dependency status useful for admin troubleshooting."""
    db_ok = False
    whatsapp_ok = False
    whatsapp_status = None

    # DB check
    try:
        async with get_db_session() as db:
            _ = await db.fetchval("SELECT 1")
        db_ok = True
    except Exception:
        db_ok = False

    # WhatsApp health check
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            res = await client.get(f"{settings.WHATSAPP_SERVICE_URL}/health")
            whatsapp_status = res.status_code
            whatsapp_ok = res.status_code == 200
    except Exception:
        whatsapp_ok = False

    return AdminHealthStatus(
        database_ok=db_ok,
        llm_configured=bool(settings.LLM_API_KEY),
        whatsapp_service_ok=whatsapp_ok,
        whatsapp_service_status=whatsapp_status,
        checked_at=datetime.now(timezone.utc),
    )
