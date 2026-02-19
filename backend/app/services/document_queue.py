"""Asynchronous document OCR/classification queue worker."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from sqlalchemy import select, func

from app.core.config import settings
from app.core.enums import CaseStatus
from app.db.database import async_session_maker
from app.models.case import Case, Document, DocumentProcessingJob
from app.services.stages.stage0_case_entry import CaseEntryService

logger = logging.getLogger(__name__)


@dataclass
class ClaimedJob:
    job_id: UUID
    case_id: UUID
    document_id: UUID
    attempts: int
    max_attempts: int


class DocumentQueueManager:
    """Database-backed worker queue for document OCR and classification."""

    def __init__(self) -> None:
        self._stop_event = asyncio.Event()
        self._tasks: list[asyncio.Task] = []
        self._started = False

    async def start(self) -> None:
        if self._started:
            return
        if not settings.DOC_QUEUE_ENABLED:
            logger.info("Document queue disabled by configuration.")
            return

        self._stop_event.clear()
        concurrency = max(1, settings.DOC_QUEUE_WORKER_CONCURRENCY)
        for idx in range(concurrency):
            task = asyncio.create_task(self._worker_loop(idx + 1))
            self._tasks.append(task)
        self._started = True
        logger.info("Document queue started with %s workers.", concurrency)

    async def stop(self) -> None:
        if not self._started:
            return

        self._stop_event.set()
        tasks = list(self._tasks)
        self._tasks.clear()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self._started = False
        logger.info("Document queue stopped.")

    async def _worker_loop(self, worker_id: int) -> None:
        poll_interval = max(200, settings.DOC_QUEUE_POLL_INTERVAL_MS) / 1000.0
        logger.info("Document queue worker-%s running.", worker_id)

        while not self._stop_event.is_set():
            claimed = await self._claim_next_job()
            if not claimed:
                await asyncio.sleep(poll_interval)
                continue
            await self._process_claimed_job(claimed)

        logger.info("Document queue worker-%s exiting.", worker_id)

    async def _claim_next_job(self) -> Optional[ClaimedJob]:
        async with async_session_maker() as db:
            async with db.begin():
                result = await db.execute(
                    select(DocumentProcessingJob)
                    .where(
                        DocumentProcessingJob.status == "queued",
                        DocumentProcessingJob.attempts < DocumentProcessingJob.max_attempts,
                    )
                    .order_by(DocumentProcessingJob.created_at.asc())
                    .with_for_update(skip_locked=True)
                    .limit(1)
                )
                job = result.scalar_one_or_none()
                if not job:
                    return None

                job.status = "processing"
                job.attempts = int(job.attempts or 0) + 1
                job.started_at = datetime.now(timezone.utc)
                job.error_message = None
                await db.flush()

                return ClaimedJob(
                    job_id=job.id,
                    case_id=job.case_id,
                    document_id=job.document_id,
                    attempts=job.attempts,
                    max_attempts=job.max_attempts,
                )

    async def _process_claimed_job(self, claimed: ClaimedJob) -> None:
        try:
            async with async_session_maker() as db:
                job = await db.get(DocumentProcessingJob, claimed.job_id)
                doc = await db.get(Document, claimed.document_id)

                if not job:
                    return
                if not doc:
                    job.status = "failed"
                    job.error_message = "Document not found"
                    job.completed_at = datetime.now(timezone.utc)
                    await self._sync_case_status(db, claimed.case_id)
                    await db.commit()
                    return

                service = CaseEntryService(db)
                await service._run_ocr_and_classification(doc, doc.storage_key)

                job.status = "completed"
                job.error_message = None
                job.completed_at = datetime.now(timezone.utc)

                await self._sync_case_status(db, claimed.case_id)
                await db.commit()

        except Exception as exc:
            logger.error("Document queue job %s failed: %s", claimed.job_id, exc, exc_info=True)
            async with async_session_maker() as db:
                job = await db.get(DocumentProcessingJob, claimed.job_id)
                if not job:
                    return

                job.error_message = str(exc)[:1000]
                if int(job.attempts or 0) >= int(job.max_attempts or 1):
                    job.status = "failed"
                    job.completed_at = datetime.now(timezone.utc)
                else:
                    job.status = "queued"
                    job.started_at = None

                await self._sync_case_status(db, claimed.case_id)
                await db.commit()

    async def _sync_case_status(self, case_id: UUID, db) -> None:
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
        else:
            if completed > 0:
                case.status = CaseStatus.DOCUMENTS_CLASSIFIED.value
            elif failed > 0:
                case.status = CaseStatus.FAILED.value
            else:
                case.status = CaseStatus.CREATED.value

        case.updated_at = datetime.now(timezone.utc)
        await db.flush()


document_queue_manager = DocumentQueueManager()
