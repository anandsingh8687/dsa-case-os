"""FastAPI Application Entry Point."""
import os
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from app.core.config import settings
from app.db.database import init_db, close_db
from app.api.v1.endpoints import (
    auth, cases, documents, extraction,
    eligibility, reports, copilot, lenders, whatsapp, share, pincodes,
    flexible_case, batch_upload, bank_statement, admin, quick_scan, commission, leads, submissions
)

logger = logging.getLogger(__name__)


async def _auto_ingest_lender_data():
    """Auto-ingest lender CSV data if tables are empty."""
    try:
        from app.db.database import get_asyncpg_pool
        pool = await get_asyncpg_pool()
        async with pool.acquire() as conn:
            count = await conn.fetchval("SELECT COUNT(*) FROM lenders")
            if count and count > 0:
                logger.info(f"Lender data already loaded ({count} lenders). Skipping ingestion.")
                return

        # Tables empty — ingest CSV data
        data_dir = os.path.join(os.path.dirname(__file__), "..", "data")
        policy_csv = os.path.join(data_dir, "lender_policy.csv")
        pincode_csv = os.path.join(data_dir, "pincode_serviceability.csv")

        if not os.path.isfile(policy_csv):
            logger.warning(f"Lender policy CSV not found at {policy_csv}. Skipping.")
            return

        from app.services.stages.stage3_ingestion import (
            ingest_lender_policy_csv,
            ingest_pincode_csv,
        )

        logger.info("Auto-ingesting lender policy data...")
        policy_stats = await ingest_lender_policy_csv(policy_csv)
        logger.info(f"Policy ingestion: {policy_stats}")

        if os.path.isfile(pincode_csv):
            logger.info("Auto-ingesting pincode serviceability data...")
            pincode_stats = await ingest_pincode_csv(pincode_csv)
            logger.info(f"Pincode ingestion: {pincode_stats}")

        logger.info("Lender data auto-ingestion complete!")

    except Exception as e:
        logger.error(f"Auto-ingestion failed (non-fatal): {e}", exc_info=True)


@asynccontextmanager
async def lifespan(application: FastAPI):
    """Startup and shutdown events."""
    # Startup: auto-create tables if they don't exist
    try:
        await init_db()
        logger.info("Database tables initialized successfully")
    except Exception as e:
        logger.warning(f"Auto-create tables skipped (likely already exist): {e}")

    # Auto-ingest lender data if tables are empty
    await _auto_ingest_lender_data()

    yield
    # Shutdown
    await close_db()


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Tighten in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── Route Registration ───────────────────────────────────────
# Each router already defines its own prefix (e.g. /auth, /cases)
# so we only add the API version prefix here.
app.include_router(auth.router,        prefix=settings.API_PREFIX, tags=["Auth"])
app.include_router(cases.router,       prefix=settings.API_PREFIX, tags=["Cases"])
app.include_router(documents.router,   prefix=settings.API_PREFIX, tags=["Documents"])
app.include_router(extraction.router,  prefix=settings.API_PREFIX, tags=["Extraction"])
app.include_router(eligibility.router, prefix=settings.API_PREFIX, tags=["Eligibility"])
app.include_router(reports.router,     prefix=settings.API_PREFIX, tags=["Reports"])
app.include_router(copilot.router,     prefix=settings.API_PREFIX, tags=["Copilot"])
app.include_router(lenders.router,     prefix=settings.API_PREFIX, tags=["Lenders"])
app.include_router(pincodes.router,    prefix=settings.API_PREFIX, tags=["Pincodes"])
app.include_router(whatsapp.router,    prefix=f"{settings.API_PREFIX}/whatsapp", tags=["WhatsApp"])
app.include_router(share.router,       prefix=settings.API_PREFIX, tags=["Share"])
app.include_router(flexible_case.router, prefix=settings.API_PREFIX, tags=["Flexible Case"])
app.include_router(batch_upload.router, prefix=settings.API_PREFIX, tags=["Batch Upload"])
app.include_router(bank_statement.router, prefix=settings.API_PREFIX, tags=["Bank Statement"])
app.include_router(admin.router,       prefix=settings.API_PREFIX, tags=["Admin"])
app.include_router(quick_scan.router,  prefix=settings.API_PREFIX, tags=["Quick Scan"])
app.include_router(commission.router,  prefix=settings.API_PREFIX, tags=["Commission"])
app.include_router(leads.router,       prefix=settings.API_PREFIX, tags=["Leads"])
app.include_router(submissions.router, prefix=settings.API_PREFIX, tags=["Submissions"])


# ─── Static Frontend ─────────────────────────────────────────
STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
if os.path.isdir(STATIC_DIR):
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/", include_in_schema=False)
async def serve_frontend():
    """Serve the DSA Case OS single-page frontend."""
    index_path = os.path.join(STATIC_DIR, "index.html")
    if os.path.isfile(index_path):
        return FileResponse(index_path, media_type="text/html")
    return {"message": "DSA Case OS API", "docs": "/docs"}


@app.get("/health")
async def health():
    return {"status": "ok", "version": settings.APP_VERSION}
