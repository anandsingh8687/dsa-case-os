"""RQ worker entrypoint.

Run with:
  PYTHONPATH=/app rq worker ocr reports rag whatsapp default
or:
  python worker.py
"""

from __future__ import annotations

import logging

from rq import Connection, Worker

from app.core.config import settings
from app.services.rq_queue import get_redis_connection

logging.basicConfig(level=logging.INFO)


def main() -> None:
    queues = [
        settings.RQ_QUEUE_OCR,
        settings.RQ_QUEUE_REPORTS,
        settings.RQ_QUEUE_RAG,
        settings.RQ_QUEUE_WHATSAPP,
        settings.RQ_QUEUE_DEFAULT,
    ]
    connection = get_redis_connection()
    with Connection(connection):
        worker = Worker(queues)
        worker.work(with_scheduler=False)


if __name__ == "__main__":
    main()
