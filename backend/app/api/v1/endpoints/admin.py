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
    quick_scans_total: int
    quick_scans_7d: int
    copilot_queries_7d: int
    leads_total: int
    leads_7d: int
    submissions_total: int
    submissions_7d: int
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


class UserUsageRow(BaseModel):
    id: str
    email: str
    full_name: str
    role: str
    is_active: bool
    cases_total: int
    docs_uploaded_30d: int
    quick_scans_30d: int
    copilot_queries_30d: int
    leads_30d: int
    submissions_30d: int
    failed_cases_30d: int
    last_activity_at: Optional[datetime] = None


class ActivityEventRow(BaseModel):
    occurred_at: datetime
    event_type: str
    actor_email: Optional[str] = None
    actor_name: Optional[str] = None
    details: str


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
        quick_scans_total = await db.fetchval("SELECT COUNT(*) FROM quick_scans")
        quick_scans_7d = await db.fetchval(
            "SELECT COUNT(*) FROM quick_scans WHERE created_at >= $1",
            seven_days_ago,
        )
        copilot_queries_7d = await db.fetchval(
            "SELECT COUNT(*) FROM copilot_queries WHERE created_at >= $1",
            seven_days_ago,
        )
        leads_total = await db.fetchval("SELECT COUNT(*) FROM leads")
        leads_7d = await db.fetchval(
            "SELECT COUNT(*) FROM leads WHERE created_at >= $1",
            seven_days_ago,
        )
        submissions_total = await db.fetchval("SELECT COUNT(*) FROM lender_submissions")
        submissions_7d = await db.fetchval(
            "SELECT COUNT(*) FROM lender_submissions WHERE created_at >= $1",
            seven_days_ago,
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
        quick_scans_total=int(quick_scans_total or 0),
        quick_scans_7d=int(quick_scans_7d or 0),
        copilot_queries_7d=int(copilot_queries_7d or 0),
        leads_total=int(leads_total or 0),
        leads_7d=int(leads_7d or 0),
        submissions_total=int(submissions_total or 0),
        submissions_7d=int(submissions_7d or 0),
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
        "error_summary": {
            "failed_case_count": len(failed_cases),
            "classification_watchlist_count": len(unreadable_docs),
        },
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


@router.get("/user-usage", response_model=List[UserUsageRow])
async def get_user_usage_matrix(
    current_user: CurrentAdmin,
    days: int = Query(30, ge=1, le=90),
    q: Optional[str] = Query(None, description="Search user/email"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    """Usage matrix across product modules for each user."""
    since = datetime.now(timezone.utc) - timedelta(days=days)
    search_pattern = f"%{q.strip()}%" if q else None

    query_base = """
        WITH case_agg AS (
            SELECT
                user_id,
                COUNT(*)::int AS cases_total,
                COUNT(*) FILTER (WHERE status = 'failed' AND updated_at >= $1)::int AS failed_cases_30d,
                MAX(updated_at) AS last_case_at
            FROM cases
            GROUP BY user_id
        ),
        doc_agg AS (
            SELECT
                c.user_id,
                COUNT(*) FILTER (WHERE d.created_at >= $1)::int AS docs_uploaded_30d,
                MAX(d.created_at) AS last_doc_at
            FROM documents d
            INNER JOIN cases c ON c.id = d.case_id
            GROUP BY c.user_id
        ),
        quick_scan_agg AS (
            SELECT
                user_id,
                COUNT(*) FILTER (WHERE created_at >= $1)::int AS quick_scans_30d,
                MAX(created_at) AS last_quick_scan_at
            FROM quick_scans
            GROUP BY user_id
        ),
        copilot_agg AS (
            SELECT
                user_id,
                COUNT(*) FILTER (WHERE created_at >= $1)::int AS copilot_queries_30d,
                MAX(created_at) AS last_copilot_at
            FROM copilot_queries
            GROUP BY user_id
        ),
        lead_agg AS (
            SELECT
                created_by AS user_id,
                COUNT(*) FILTER (WHERE created_at >= $1)::int AS leads_30d,
                MAX(created_at) AS last_lead_at
            FROM leads
            GROUP BY created_by
        ),
        submission_agg AS (
            SELECT
                c.user_id,
                COUNT(*) FILTER (WHERE ls.created_at >= $1)::int AS submissions_30d,
                MAX(ls.created_at) AS last_submission_at
            FROM lender_submissions ls
            INNER JOIN cases c ON c.id = ls.case_id
            GROUP BY c.user_id
        )
        SELECT
            u.id::text,
            u.email,
            u.full_name,
            u.role,
            u.is_active,
            COALESCE(ca.cases_total, 0) AS cases_total,
            COALESCE(da.docs_uploaded_30d, 0) AS docs_uploaded_30d,
            COALESCE(qa.quick_scans_30d, 0) AS quick_scans_30d,
            COALESCE(coa.copilot_queries_30d, 0) AS copilot_queries_30d,
            COALESCE(la.leads_30d, 0) AS leads_30d,
            COALESCE(sa.submissions_30d, 0) AS submissions_30d,
            COALESCE(ca.failed_cases_30d, 0) AS failed_cases_30d,
            GREATEST(
                ca.last_case_at,
                da.last_doc_at,
                qa.last_quick_scan_at,
                coa.last_copilot_at,
                la.last_lead_at,
                sa.last_submission_at
            ) AS last_activity_at
        FROM users u
        LEFT JOIN case_agg ca ON ca.user_id = u.id
        LEFT JOIN doc_agg da ON da.user_id = u.id
        LEFT JOIN quick_scan_agg qa ON qa.user_id = u.id
        LEFT JOIN copilot_agg coa ON coa.user_id = u.id
        LEFT JOIN lead_agg la ON la.user_id = u.id
        LEFT JOIN submission_agg sa ON sa.user_id = u.id
    """

    async with get_db_session() as db:
        if search_pattern:
            rows = await db.fetch(
                f"""
                {query_base}
                WHERE u.email ILIKE $2 OR u.full_name ILIKE $2
                ORDER BY last_activity_at DESC NULLS LAST, u.created_at DESC
                LIMIT $3 OFFSET $4
                """,
                since,
                search_pattern,
                limit,
                offset,
            )
        else:
            rows = await db.fetch(
                f"""
                {query_base}
                ORDER BY last_activity_at DESC NULLS LAST, u.created_at DESC
                LIMIT $2 OFFSET $3
                """,
                since,
                limit,
                offset,
            )

    return [
        UserUsageRow(
            id=row["id"],
            email=row["email"],
            full_name=row["full_name"],
            role=row["role"],
            is_active=bool(row["is_active"]),
            cases_total=int(row["cases_total"] or 0),
            docs_uploaded_30d=int(row["docs_uploaded_30d"] or 0),
            quick_scans_30d=int(row["quick_scans_30d"] or 0),
            copilot_queries_30d=int(row["copilot_queries_30d"] or 0),
            leads_30d=int(row["leads_30d"] or 0),
            submissions_30d=int(row["submissions_30d"] or 0),
            failed_cases_30d=int(row["failed_cases_30d"] or 0),
            last_activity_at=row["last_activity_at"],
        )
        for row in rows
    ]


@router.get("/activity-feed", response_model=List[ActivityEventRow])
async def get_activity_feed(
    current_user: CurrentAdmin,
    days: int = Query(7, ge=1, le=30),
    limit: int = Query(100, ge=1, le=500),
):
    """Cross-module activity feed to debug platform usage and failures."""
    since = datetime.now(timezone.utc) - timedelta(days=days)

    async with get_db_session() as db:
        rows = await db.fetch(
            """
            SELECT *
            FROM (
                SELECT
                    c.created_at AS occurred_at,
                    'case_created'::text AS event_type,
                    u.email AS actor_email,
                    u.full_name AS actor_name,
                    CONCAT(c.case_id, ' • ', COALESCE(c.borrower_name, 'Unnamed borrower')) AS details
                FROM cases c
                INNER JOIN users u ON u.id = c.user_id
                WHERE c.created_at >= $1

                UNION ALL

                SELECT
                    d.created_at AS occurred_at,
                    'document_uploaded'::text AS event_type,
                    u.email AS actor_email,
                    u.full_name AS actor_name,
                    CONCAT(c.case_id, ' • ', COALESCE(d.original_filename, 'unnamed file')) AS details
                FROM documents d
                INNER JOIN cases c ON c.id = d.case_id
                INNER JOIN users u ON u.id = c.user_id
                WHERE d.created_at >= $1

                UNION ALL

                SELECT
                    qs.created_at AS occurred_at,
                    'quick_scan_run'::text AS event_type,
                    u.email AS actor_email,
                    u.full_name AS actor_name,
                    CONCAT(qs.loan_type, ' • ', COALESCE(qs.pincode, 'no pincode')) AS details
                FROM quick_scans qs
                INNER JOIN users u ON u.id = qs.user_id
                WHERE qs.created_at >= $1

                UNION ALL

                SELECT
                    cq.created_at AS occurred_at,
                    'copilot_query'::text AS event_type,
                    u.email AS actor_email,
                    u.full_name AS actor_name,
                    LEFT(COALESCE(cq.query_text, ''), 120) AS details
                FROM copilot_queries cq
                LEFT JOIN users u ON u.id = cq.user_id
                WHERE cq.created_at >= $1

                UNION ALL

                SELECT
                    l.created_at AS occurred_at,
                    'lead_created'::text AS event_type,
                    u.email AS actor_email,
                    u.full_name AS actor_name,
                    CONCAT(COALESCE(l.customer_name, 'Unnamed lead'), ' • ', COALESCE(l.loan_type_interest, 'N/A')) AS details
                FROM leads l
                LEFT JOIN users u ON u.id = l.created_by
                WHERE l.created_at >= $1

                UNION ALL

                SELECT
                    ls.created_at AS occurred_at,
                    'submission_created'::text AS event_type,
                    u.email AS actor_email,
                    u.full_name AS actor_name,
                    CONCAT(c.case_id, ' • ', COALESCE(ls.lender_name, 'Unknown lender')) AS details
                FROM lender_submissions ls
                INNER JOIN cases c ON c.id = ls.case_id
                INNER JOIN users u ON u.id = c.user_id
                WHERE ls.created_at >= $1
            ) feed
            ORDER BY occurred_at DESC
            LIMIT $2
            """,
            since,
            limit,
        )

    return [
        ActivityEventRow(
            occurred_at=row["occurred_at"],
            event_type=row["event_type"],
            actor_email=row["actor_email"],
            actor_name=row["actor_name"],
            details=row["details"],
        )
        for row in rows
    ]
