"""RAG management endpoints."""

from __future__ import annotations

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.core.deps import CurrentSuperAdmin
from app.core.config import settings
from app.services.rq_queue import enqueue_rag_ingestion_job
from app.services.rag_service import DEFAULT_POLICY_SOURCES, ingest_lender_policy_documents, search_relevant_lender_chunks

router = APIRouter(prefix="/rag", tags=["rag"])


class RAGIngestRequest(BaseModel):
    organization_id: UUID
    source_paths: Optional[list[str]] = None


class RAGSearchRequest(BaseModel):
    organization_id: UUID
    query: str
    top_k: Optional[int] = 8


@router.post("/ingest")
async def ingest_rag_documents(
    payload: RAGIngestRequest,
    current_user: CurrentSuperAdmin,
):
    try:
        source_paths = payload.source_paths or list(DEFAULT_POLICY_SOURCES)
        if settings.RQ_ASYNC_ENABLED:
            rq_job_id = enqueue_rag_ingestion_job(str(payload.organization_id), source_paths)
            return {
                "status": "queued",
                "job_id": rq_job_id,
                "organization_id": str(payload.organization_id),
                "source_paths": source_paths,
            }

        result = await ingest_lender_policy_documents(
            organization_id=payload.organization_id,
            source_paths=source_paths,
        )
        return {"status": "success", **result}
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"RAG ingestion failed: {exc}") from exc


@router.post("/search")
async def search_rag(
    payload: RAGSearchRequest,
    current_user: CurrentSuperAdmin,
):
    try:
        rows = await search_relevant_lender_chunks(
            organization_id=payload.organization_id,
            query=payload.query,
            top_k=payload.top_k or 8,
        )
        return {"status": "success", "count": len(rows), "results": rows}
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"RAG search failed: {exc}") from exc
