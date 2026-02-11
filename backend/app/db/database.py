"""
Database configuration and session management for SQLAlchemy with async support.
"""

import os
import logging
from typing import AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    AsyncEngine,
    create_async_engine,
)
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool
import asyncpg

from app.core.config import settings

logger = logging.getLogger(__name__)


# Create async engine
engine: AsyncEngine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.DEBUG,
    future=True,
    pool_pre_ping=True,
    poolclass=NullPool,
)

# Create async session factory
async_session_maker = sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Dependency function to get database session for FastAPI routes.
    
    Yields:
        AsyncSession: Database session for the request
    """
    async with async_session_maker() as session:
        try:
            yield session
        finally:
            await session.close()


async def init_db() -> None:
    """
    Initialize the database by creating all tables.
    Should be called on application startup.

    This creates:
    1. SQLAlchemy ORM tables (users, cases, documents, etc.)
    2. Non-ORM tables from schema.sql (lenders, lender_products, etc.)
    """
    # Step 1: Create ORM tables
    async with engine.begin() as conn:
        from app.models import Base  # noqa: F811 — triggers __init__.py imports
        await conn.run_sync(Base.metadata.create_all)

    # Step 2: Create non-ORM tables (lenders, lender_products, etc.)
    await _ensure_schema_tables()


async def _ensure_schema_tables() -> None:
    """Create non-ORM tables if they don't exist (from schema.sql).

    These tables include: lenders, lender_products, lender_pincodes,
    lender_branches, lender_rms, eligibility_results, case_reports, copilot_queries.
    """
    pool = await get_asyncpg_pool()
    async with pool.acquire() as conn:
        # Check if lenders table exists
        exists = await conn.fetchval(
            "SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'lenders')"
        )
        if exists:
            logger.info("Schema tables already exist, skipping creation")
            return

        # Read and execute schema.sql
        schema_path = os.path.join(os.path.dirname(__file__), "schema.sql")
        if not os.path.isfile(schema_path):
            logger.warning(f"schema.sql not found at {schema_path}")
            return

        logger.info("Creating non-ORM schema tables from schema.sql...")
        with open(schema_path, 'r') as f:
            schema_sql = f.read()

        # Execute schema - use IF NOT EXISTS logic
        # Split by semicolons and execute each statement
        for statement in schema_sql.split(';'):
            statement = statement.strip()
            if not statement or statement.startswith('--'):
                continue
            try:
                # Add IF NOT EXISTS where possible
                if statement.upper().startswith('CREATE TABLE'):
                    statement = statement.replace('CREATE TABLE ', 'CREATE TABLE IF NOT EXISTS ', 1)
                elif statement.upper().startswith('CREATE INDEX'):
                    statement = statement.replace('CREATE INDEX ', 'CREATE INDEX IF NOT EXISTS ', 1)
                elif statement.upper().startswith('CREATE EXTENSION'):
                    # Extensions already have IF NOT EXISTS
                    pass
                await conn.execute(statement)
            except Exception as e:
                # Some statements may fail if table already exists, that's OK
                if 'already exists' not in str(e).lower():
                    logger.warning(f"Schema statement warning: {e}")

        logger.info("Schema tables created successfully")


async def close_db() -> None:
    """
    Close the database connection pool.
    Should be called on application shutdown.
    """
    await engine.dispose()
    if _asyncpg_pool is not None:
        await _asyncpg_pool.close()


# ═══════════════════════════════════════════════════════════════
# ASYNCPG RAW CONNECTION POOL (for lender_service and eligibility)
# ═══════════════════════════════════════════════════════════════

_asyncpg_pool: asyncpg.Pool = None


async def get_asyncpg_pool() -> asyncpg.Pool:
    """Get or create the asyncpg connection pool."""
    global _asyncpg_pool

    if _asyncpg_pool is None:
        # Convert SQLAlchemy async URL to standard postgres URL for asyncpg
        db_url = settings.DATABASE_URL
        # Remove the +asyncpg driver specification
        db_url = db_url.replace("postgresql+asyncpg://", "")
        db_url = db_url.replace("postgresql://", "")

        # Parse connection details
        # Format: postgres:postgres@localhost:5432/dsa_case_os
        parts = db_url.split("@")
        user_pass = parts[0].split(":")
        host_db = parts[1].split("/")
        host_port = host_db[0].split(":")

        _asyncpg_pool = await asyncpg.create_pool(
            user=user_pass[0],
            password=user_pass[1] if len(user_pass) > 1 else "",
            host=host_port[0],
            port=int(host_port[1]) if len(host_port) > 1 else 5432,
            database=host_db[1],
            min_size=2,
            max_size=10
        )

    return _asyncpg_pool


@asynccontextmanager
async def get_db_session():
    """Get a raw asyncpg connection from the pool.

    This is used by lender_service and eligibility_service for raw SQL queries.

    Usage:
        async with get_db_session() as db:
            rows = await db.fetch("SELECT * FROM table")
            row = await db.fetchrow("SELECT * FROM table WHERE id = $1", id)
            await db.execute("INSERT INTO table ...")
    """
    pool = await get_asyncpg_pool()
    async with pool.acquire() as connection:
        yield connection
