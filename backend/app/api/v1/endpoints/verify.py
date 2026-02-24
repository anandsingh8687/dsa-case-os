"""Operational verification endpoints for RAG and auto-pipeline checks."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import CurrentSuperAdmin
from app.db.database import get_db
from app.models.case import Case, Document, DocumentProcessingJob
from app.models.organization import Organization
from app.services.rag_service import search_relevant_lender_chunks

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/verify", tags=["verify"])


class VerifyRagRequest(BaseModel):
    organization_id: Optional[UUID] = None
    queries: Optional[list[str]] = None


class VerifyAutoRequest(BaseModel):
    case_id: Optional[str] = None


async def _resolve_org_id(db: AsyncSession, preferred_org_id: UUID | None, current_user) -> UUID:
    if preferred_org_id:
        org = await db.get(Organization, preferred_org_id)
        if not org:
            raise HTTPException(status_code=404, detail="Organization not found")
        return preferred_org_id

    if getattr(current_user, "organization_id", None):
        return current_user.organization_id

    row = await db.execute(select(Organization.id).order_by(Organization.created_at.asc()).limit(1))
    org_id = row.scalar_one_or_none()
    if not org_id:
        raise HTTPException(status_code=404, detail="No organizations found")
    return org_id


async def _rag_capabilities(db: AsyncSession) -> dict:
    row = await db.execute(
        text(
            """
            SELECT
              EXISTS (
                SELECT 1
                FROM information_schema.tables
                WHERE table_schema = 'public' AND table_name = 'lender_documents'
              ) AS has_table,
              EXISTS (
                SELECT 1
                FROM pg_extension
                WHERE extname = 'vector'
              ) AS has_vector
            """
        )
    )
    result = row.mappings().first() or {}
    has_table = bool(result.get("has_table"))
    has_vector = bool(result.get("has_vector"))
    return {
        "has_table": has_table,
        "has_vector": has_vector,
        "mode": "pgvector" if has_vector else "json_fallback",
    }


@router.post("/rag")
async def verify_rag(
    payload: VerifyRagRequest,
    current_user: CurrentSuperAdmin,
    db: AsyncSession = Depends(get_db),
):
    """Run retrieval-quality sanity checks against ingested lender policy chunks."""
    rag_caps = await _rag_capabilities(db)
    if not rag_caps["has_table"]:
        raise HTTPException(
            status_code=503,
            detail="RAG verification unavailable: lender_documents table is not ready",
        )

    org_id = await _resolve_org_id(db, payload.organization_id, current_user)

    rows = await db.execute(
        text(
            """
            SELECT lender_name, product_type
            FROM lender_documents
            WHERE organization_id = :org_id
            GROUP BY lender_name, product_type
            ORDER BY lender_name
            LIMIT 8
            """
        ),
        {"org_id": org_id},
    )
    lender_products = rows.mappings().all()
    if not lender_products:
        raise HTTPException(status_code=404, detail="No lender_documents found for this organization")

    if payload.queries:
        test_items = [{"query": q, "expected_lender": None} for q in payload.queries if q.strip()]
    else:
        test_items = [
            {
                "query": f"{row['lender_name']} {row['product_type']} policy interest and eligibility",
                "expected_lender": row["lender_name"],
            }
            for row in lender_products
        ]

    results = []
    hits = 0
    for item in test_items:
        query = item["query"]
        expected = (item.get("expected_lender") or "").strip().lower()
        chunks = await search_relevant_lender_chunks(
            organization_id=org_id,
            query=query,
            top_k=8,
        )
        top = chunks[0] if chunks else None
        predicted = (top or {}).get("lender_name")
        predicted_norm = str(predicted or "").strip().lower()
        relevant = bool(predicted_norm and expected and (expected in predicted_norm or predicted_norm in expected))
        if expected and relevant:
            hits += 1

        results.append(
            {
                "query": query,
                "expected_lender": item.get("expected_lender"),
                "top_lender": predicted,
                "top_product_type": (top or {}).get("product_type"),
                "top_distance": (top or {}).get("distance"),
                "top_section": (top or {}).get("section_title"),
                "is_relevant": relevant if expected else bool(top),
            }
        )

    denominator = len([r for r in results if r.get("expected_lender")]) or len(results) or 1
    accuracy = round(hits / denominator, 4)
    logger.info(
        "RAG verify completed: org=%s tests=%s hits=%s accuracy=%s",
        org_id,
        len(results),
        hits,
        accuracy,
    )

    return {
        "status": "success",
        "mode": rag_caps["mode"],
        "organization_id": str(org_id),
        "tested_queries": len(results),
        "accuracy": accuracy,
        "results": results,
        "verified_at": datetime.now(timezone.utc).isoformat(),
    }


@router.post("/auto")
async def verify_auto_pipeline(
    payload: VerifyAutoRequest,
    current_user: CurrentSuperAdmin,
    db: AsyncSession = Depends(get_db),
):
    """Verify prefill and async pipeline behavior on a recent case."""
    case_query = select(Case).order_by(Case.updated_at.desc())
    if payload.case_id:
        case_query = select(Case).where(Case.case_id == payload.case_id)
    case_row = await db.execute(case_query.limit(1))
    case = case_row.scalar_one_or_none()
    if not case:
        raise HTTPException(status_code=404, detail="No case found for verification")

    doc_rows = await db.execute(
        select(Document.created_at)
        .where(Document.case_id == case.id)
        .order_by(Document.created_at.asc())
        .limit(1)
    )
    first_doc_time = doc_rows.scalar_one_or_none()

    job_rows = await db.execute(
        select(DocumentProcessingJob.status, func.count())
        .where(DocumentProcessingJob.case_id == case.id)
        .group_by(DocumentProcessingJob.status)
    )
    job_counts = {status: int(count) for status, count in job_rows.all()}
    pending_jobs = int(job_counts.get("queued", 0) + job_counts.get("processing", 0))

    prefill_latency_ms = None
    if first_doc_time and case.gst_fetched_at:
        prefill_latency_ms = int(
            max(
                0,
                (case.gst_fetched_at.replace(tzinfo=None) - first_doc_time.replace(tzinfo=None)).total_seconds()
                * 1000,
            )
        )

    pipeline_complete = case.status in {
        "features_extracted",
        "eligibility_scored",
        "report_generated",
        "submitted",
    }
    gst_ok = bool(case.gstin and case.gst_data)

    result = {
        "status": "success",
        "case_id": case.case_id,
        "case_status": case.status,
        "prefill": {
            "gst_extraction_success": gst_ok,
            "prefill_latency_ms": prefill_latency_ms,
            "prefill_under_60s": prefill_latency_ms is not None and prefill_latency_ms <= 60000,
        },
        "background_pipeline": {
            "document_jobs": {
                "queued": int(job_counts.get("queued", 0)),
                "processing": int(job_counts.get("processing", 0)),
                "completed": int(job_counts.get("completed", 0)),
                "failed": int(job_counts.get("failed", 0)),
                "pending": pending_jobs,
            },
            "pipeline_complete": pipeline_complete,
            "pipeline_not_blocked_by_queue": pending_jobs == 0,
        },
        "checks_passed": bool(gst_ok and pending_jobs == 0),
        "verified_at": datetime.now(timezone.utc).isoformat(),
    }
    logger.info("Auto verify completed: %s", result)
    return result
