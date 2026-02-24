"""Redis/RQ queue helpers for heavy async workloads."""

from __future__ import annotations

import logging
from typing import Any

from redis import Redis
from rq import Queue
from rq.job import Job

from app.core.config import settings

logger = logging.getLogger(__name__)

_redis_conn: Redis | None = None
_queues: dict[str, Queue] = {}


def get_redis_connection() -> Redis:
    global _redis_conn
    if _redis_conn is None:
        _redis_conn = Redis.from_url(settings.REDIS_URL)
    return _redis_conn


def get_queue(name: str | None = None) -> Queue:
    queue_name = name or settings.RQ_QUEUE_DEFAULT
    if queue_name not in _queues:
        _queues[queue_name] = Queue(
            queue_name,
            connection=get_redis_connection(),
            default_timeout=settings.RQ_DEFAULT_TIMEOUT,
        )
    return _queues[queue_name]


def enqueue_document_job(job_id: str) -> str:
    queue = get_queue(settings.RQ_QUEUE_OCR)
    retry_count = max(0, settings.DOC_QUEUE_MAX_ATTEMPTS - 1)
    retry = None
    if retry_count > 0:
        from rq import Retry

        retry = Retry(max=retry_count, interval=[2, 5, 10][:retry_count])

    job: Job = queue.enqueue(
        "app.services.jobs.process_document_job",
        job_id,
        retry=retry,
        job_timeout=settings.RQ_DEFAULT_TIMEOUT,
        description=f"process_document_job:{job_id}",
    )
    return job.id


def enqueue_rag_ingestion_job(organization_id: str, source_paths: list[str] | None = None) -> str:
    queue = get_queue(settings.RQ_QUEUE_RAG)
    job: Job = queue.enqueue(
        "app.services.jobs.run_rag_ingestion_job",
        organization_id,
        source_paths or [],
        job_timeout=max(settings.RQ_DEFAULT_TIMEOUT, 3600),
        description=f"rag_ingest:{organization_id}",
    )
    return job.id


def enqueue_case_pipeline_job(case_id: str) -> str:
    """Queue full async pipeline for one case (extract -> score -> report)."""
    queue = get_queue(settings.RQ_QUEUE_REPORTS)
    job: Job = queue.enqueue(
        "app.services.jobs.run_case_pipeline_job",
        case_id,
        job_timeout=max(settings.RQ_DEFAULT_TIMEOUT, 1800),
        description=f"case_pipeline:{case_id}",
    )
    return job.id


def get_queue_snapshot() -> dict[str, Any]:
    snapshot: dict[str, Any] = {}
    for queue_name in {
        settings.RQ_QUEUE_DEFAULT,
        settings.RQ_QUEUE_OCR,
        settings.RQ_QUEUE_REPORTS,
        settings.RQ_QUEUE_RAG,
        settings.RQ_QUEUE_WHATSAPP,
    }:
        queue = get_queue(queue_name)
        snapshot[queue_name] = {
            "queued": queue.count,
            "started": queue.started_job_registry.count,
            "failed": queue.failed_job_registry.count,
            "deferred": queue.deferred_job_registry.count,
            "finished": queue.finished_job_registry.count,
        }
    return snapshot
