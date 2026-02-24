#!/usr/bin/env python3
"""Ingest lender policy documents into pgvector RAG store.

Default sources:
  /Users/aparajitasharma/Downloads/ILB((POLICY PINCODE)-20260222T040809Z-1-001.zip
  /Users/aparajitasharma/Downloads/Policies BL -20260222T040706Z-1-001.zip
"""

from __future__ import annotations

import argparse
import asyncio
import json
from uuid import UUID

from app.db.database import get_asyncpg_pool
from app.services.rag_service import DEFAULT_POLICY_SOURCES, ingest_lender_policy_documents


async def _resolve_org_id(explicit_org_id: str | None) -> UUID:
    if explicit_org_id:
        return UUID(explicit_org_id)

    pool = await get_asyncpg_pool()
    async with pool.acquire() as db:
        row = await db.fetchrow(
            "SELECT id FROM organizations WHERE is_active = TRUE ORDER BY created_at ASC LIMIT 1"
        )
        if not row:
            raise RuntimeError("No organization found. Create an organization first.")
        return row["id"]


async def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest lender docs into pgvector table.")
    parser.add_argument("--organization-id", help="Target organization UUID")
    parser.add_argument(
        "--sources",
        nargs="*",
        default=None,
        help="Override source paths. If omitted, the two default ZIP paths are used and sibling docs are auto-scanned.",
    )
    args = parser.parse_args()

    org_id = await _resolve_org_id(args.organization_id)
    result = await ingest_lender_policy_documents(
        organization_id=org_id,
        source_paths=args.sources or list(DEFAULT_POLICY_SOURCES),
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    asyncio.run(main())

