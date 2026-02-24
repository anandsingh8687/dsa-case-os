"""RQ job handlers for heavy background workloads."""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import UUID

from sqlalchemy import func, select

from app.core.enums import CaseStatus
from app.db.database import async_session_maker
from app.models.case import Case, Document, DocumentProcessingJob
from app.services.rag_service import ingest_lender_policy_documents
from app.services.stages.stage0_case_entry import CaseEntryService

logger = logging.getLogger(__name__)


async def _sync_case_status(case_id: UUID) -> None:
    async with async_session_maker() as db:
        rows = await db.execute(
            select(DocumentProcessingJob.status, func.count())
            .where(DocumentProcessingJob.case_id == case_id)
            .group_by(DocumentProcessingJob.status)
        )
        counts = {status: int(count) for status, count in rows.all()}

        queued = counts.get("queued", 0)
        processing = counts.get("processing", 0)
        completed = counts.get("completed", 0)
        failed = counts.get("failed", 0)

        case = await db.get(Case, case_id)
        if not case:
            return

        if queued > 0 or processing > 0:
            case.status = CaseStatus.PROCESSING.value
        elif completed > 0:
            case.status = CaseStatus.DOCUMENTS_CLASSIFIED.value
        elif failed > 0:
            case.status = CaseStatus.FAILED.value
        else:
            case.status = CaseStatus.CREATED.value

        case.updated_at = datetime.now(timezone.utc)
        await db.commit()


async def _process_document_job_async(job_id: str) -> None:
    try:
        job_uuid = UUID(job_id)
    except Exception as exc:  # noqa: BLE001
        logger.error("Invalid document job id %s: %s", job_id, exc)
        return

    # Mark processing and increment attempts.
    async with async_session_maker() as db:
        job = await db.get(DocumentProcessingJob, job_uuid)
        if not job:
            return

        if job.status == "completed":
            return

        job.status = "processing"
        job.started_at = datetime.now(timezone.utc)
        job.error_message = None
        job.attempts = int(job.attempts or 0) + 1
        await db.commit()

    try:
        async with async_session_maker() as db:
            job = await db.get(DocumentProcessingJob, job_uuid)
            if not job:
                return

            doc = await db.get(Document, job.document_id)
            if not doc:
                job.status = "failed"
                job.completed_at = datetime.now(timezone.utc)
                job.error_message = "Document not found"
                await db.commit()
                await _sync_case_status(job.case_id)
                return

            service = CaseEntryService(db)
            await service._run_ocr_and_classification(doc, doc.storage_key)

            job.status = "completed"
            job.completed_at = datetime.now(timezone.utc)
            job.error_message = None
            await db.commit()

            await _sync_case_status(job.case_id)

    except Exception as exc:  # noqa: BLE001
        logger.error("RQ document job %s failed: %s", job_id, exc, exc_info=True)

        async with async_session_maker() as db:
            job = await db.get(DocumentProcessingJob, job_uuid)
            if not job:
                raise

            attempts = int(job.attempts or 0)
            max_attempts = int(job.max_attempts or 1)
            job.error_message = str(exc)[:1000]

            if attempts >= max_attempts:
                job.status = "failed"
                job.completed_at = datetime.now(timezone.utc)
            else:
                job.status = "queued"
                job.started_at = None

            await db.commit()
            await _sync_case_status(job.case_id)

        # Reraise only when retry is still allowed.
        if attempts < max_attempts:
            raise


def process_document_job(job_id: str) -> None:
    """RQ-compatible synchronous wrapper for document processing."""
    asyncio.run(_process_document_job_async(job_id))


async def _run_rag_ingestion_async(organization_id: str, source_paths: list[str] | None = None) -> dict:
    org_uuid = UUID(organization_id)
    return await ingest_lender_policy_documents(
        organization_id=org_uuid,
        source_paths=source_paths or None,
    )


def run_rag_ingestion_job(organization_id: str, source_paths: list[str] | None = None) -> dict:
    """RQ-compatible synchronous wrapper for lender policy ingestion."""
    return asyncio.run(_run_rag_ingestion_async(organization_id, source_paths))


async def _wait_for_document_jobs(case_uuid: UUID, timeout_seconds: int = 900) -> dict[str, int]:
    deadline = time.monotonic() + timeout_seconds
    latest_counts = {"queued": 0, "processing": 0, "completed": 0, "failed": 0}

    while time.monotonic() < deadline:
        async with async_session_maker() as db:
            rows = await db.execute(
                select(DocumentProcessingJob.status, func.count())
                .where(DocumentProcessingJob.case_id == case_uuid)
                .group_by(DocumentProcessingJob.status)
            )
            latest_counts = {status: int(count) for status, count in rows.all()}
            if latest_counts.get("queued", 0) + latest_counts.get("processing", 0) == 0:
                return latest_counts
        await asyncio.sleep(2)

    raise TimeoutError(
        f"Document queue timeout for case {case_uuid}. Last counts: {latest_counts}"
    )


async def _run_case_pipeline_async(case_id: str) -> dict:
    from app.api.v1.endpoints.extraction import trigger_extraction
    from app.api.v1.endpoints.eligibility import score_eligibility
    from app.api.v1.endpoints.reports import generate_report

    async with async_session_maker() as db:
        row = await db.execute(select(Case).where(Case.case_id == case_id))
        case = row.scalar_one_or_none()
        if not case:
            raise ValueError(f"Case not found: {case_id}")
        case_uuid = case.id
        system_user = SimpleNamespace(
            id=case.user_id,
            organization_id=getattr(case, "organization_id", None),
            role="super_admin",
        )

    queue_counts = await _wait_for_document_jobs(case_uuid)

    async with async_session_maker() as db:
        await trigger_extraction(case_id=case_id, current_user=system_user, db=db)

    async with async_session_maker() as db:
        await score_eligibility(case_id=case_id, current_user=system_user, db=db)

    await generate_report(case_id=case_id, current_user=system_user)

    return {
        "case_id": case_id,
        "document_queue": queue_counts,
        "status": "completed",
    }


async def run_case_pipeline_async(case_id: str) -> dict:
    """Async full-pipeline runner (safe for current event loop/background tasks)."""
    try:
        return await _run_case_pipeline_async(case_id)
    except Exception as exc:  # noqa: BLE001
        logger.error("Case pipeline failed for %s: %s", case_id, exc, exc_info=True)
        try:
            await _mark_case_failed(case_id, str(exc))
        except Exception:  # noqa: BLE001
            logger.exception("Failed to mark case as failed for %s", case_id)
        raise


def run_case_pipeline_job(case_id: str) -> dict:
    """RQ-compatible synchronous wrapper for full case pipeline."""
    return asyncio.run(run_case_pipeline_async(case_id))


async def _mark_case_failed(case_id: str, reason: str) -> None:
    async with async_session_maker() as db:
        row = await db.execute(select(Case).where(Case.case_id == case_id))
        case = row.scalar_one_or_none()
        if not case:
            return
        case.status = CaseStatus.FAILED.value
        case.updated_at = datetime.now(timezone.utc)
        await db.commit()
