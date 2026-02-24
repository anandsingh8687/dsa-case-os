"""Application configuration - shared across all modules."""
import os
from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    # App
    APP_NAME: str = "DSA Case OS"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = True
    API_PREFIX: str = "/api/v1"

    # Database
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL",
        "postgresql+asyncpg://postgres:postgres@localhost:5432/dsa_case_os"
    )
    DATABASE_URL_SYNC: str = os.getenv(
        "DATABASE_URL_SYNC",
        "postgresql://postgres:postgres@localhost:5432/dsa_case_os"
    )

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # Railway sets DATABASE_URL as postgresql:// but we need postgresql+asyncpg://
        if self.DATABASE_URL.startswith("postgresql://"):
            self.DATABASE_URL = self.DATABASE_URL.replace(
                "postgresql://", "postgresql+asyncpg://", 1
            )
        # Set sync URL from async URL if not explicitly set
        if self.DATABASE_URL_SYNC.startswith("postgresql+asyncpg://"):
            self.DATABASE_URL_SYNC = self.DATABASE_URL_SYNC.replace(
                "postgresql+asyncpg://", "postgresql://", 1
            )

    # Auth
    SECRET_KEY: str = os.getenv("SECRET_KEY", "dev-secret-key-change-in-prod")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 24 hours
    JWT_ALGORITHM: str = "HS256"

    # File Storage
    STORAGE_BACKEND: str = "local"  # "local" or "s3"
    LOCAL_STORAGE_PATH: str = "./uploads"
    S3_BUCKET: Optional[str] = None
    S3_REGION: Optional[str] = None
    AWS_ACCESS_KEY: Optional[str] = None
    AWS_SECRET_KEY: Optional[str] = None

    # File Limits
    MAX_FILE_SIZE_MB: int = 25
    MAX_CASE_UPLOAD_MB: int = 100
    ALLOWED_EXTENSIONS: list = ["pdf", "jpg", "jpeg", "png", "tiff", "zip"]

    # OCR
    TESSERACT_CMD: str = "tesseract"
    PDF_PASSWORD_CANDIDATES: Optional[str] = os.getenv("PDF_PASSWORD_CANDIDATES", "")

    # Kimi 2.5 API (Moonshot AI - for Copilot)
    LLM_API_KEY: Optional[str] = None
    LLM_MODEL: str = "kimi-k2.5"
    LLM_BASE_URL: str = "https://api.moonshot.ai/v1"
    COPILOT_FAST_MODEL: str = os.getenv("COPILOT_FAST_MODEL", "moonshot-v1-8k")

    # Async document processing worker queue
    DOC_QUEUE_ENABLED: bool = os.getenv("DOC_QUEUE_ENABLED", "true").lower() == "true"
    DOC_QUEUE_WORKER_CONCURRENCY: int = int(os.getenv("DOC_QUEUE_WORKER_CONCURRENCY", "1"))
    DOC_QUEUE_POLL_INTERVAL_MS: int = int(os.getenv("DOC_QUEUE_POLL_INTERVAL_MS", "750"))
    DOC_QUEUE_MAX_ATTEMPTS: int = int(os.getenv("DOC_QUEUE_MAX_ATTEMPTS", "2"))

    # Redis/RQ
    REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    RQ_ASYNC_ENABLED: bool = os.getenv("RQ_ASYNC_ENABLED", "false").lower() == "true"
    RQ_DEFAULT_TIMEOUT: int = int(os.getenv("RQ_DEFAULT_TIMEOUT", "600"))
    RQ_QUEUE_DEFAULT: str = os.getenv("RQ_QUEUE_DEFAULT", "default")
    RQ_QUEUE_OCR: str = os.getenv("RQ_QUEUE_OCR", "ocr")
    RQ_QUEUE_REPORTS: str = os.getenv("RQ_QUEUE_REPORTS", "reports")
    RQ_QUEUE_RAG: str = os.getenv("RQ_QUEUE_RAG", "rag")
    RQ_QUEUE_WHATSAPP: str = os.getenv("RQ_QUEUE_WHATSAPP", "whatsapp")

    # Multi-tenancy
    DEFAULT_ORG_NAME: str = os.getenv("DEFAULT_ORG_NAME", "Credilo Workspace")

    # WhatsApp Cloud API (Meta)
    WHATSAPP_CLOUD_ACCESS_TOKEN: Optional[str] = os.getenv("WHATSAPP_CLOUD_ACCESS_TOKEN")
    WHATSAPP_CLOUD_PHONE_NUMBER_ID: Optional[str] = os.getenv("WHATSAPP_CLOUD_PHONE_NUMBER_ID")
    WHATSAPP_CLOUD_BUSINESS_NUMBER: str = os.getenv("WHATSAPP_CLOUD_BUSINESS_NUMBER", "8130781881")
    WHATSAPP_CLOUD_VERIFY_TOKEN: str = os.getenv("WHATSAPP_CLOUD_VERIFY_TOKEN", "credilo-whatsapp-verify")
    WHATSAPP_CLOUD_API_VERSION: str = os.getenv("WHATSAPP_CLOUD_API_VERSION", "v21.0")

    # RAG
    RAG_EMBEDDING_MODEL: str = os.getenv("RAG_EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
    RAG_TOP_K: int = int(os.getenv("RAG_TOP_K", "8"))

    # WhatsApp Service
    WHATSAPP_SERVICE_URL: str = os.getenv("WHATSAPP_SERVICE_URL", "http://localhost:3001")

    # Credilo Bank Parser Integration
    CREDILO_API_BASE_URL: str = os.getenv(
        "CREDILO_API_BASE_URL",
        "https://skill-deploy-wudy4wwji7-codex-agent-deploys.vercel.app",
    )
    CREDILO_PROCESS_PATH: str = os.getenv("CREDILO_PROCESS_PATH", "/api/process")
    CREDILO_PREVIEW_PATH: str = os.getenv("CREDILO_PREVIEW_PATH", "/api/process-preview")
    CREDILO_TIMEOUT_SECONDS: float = float(os.getenv("CREDILO_TIMEOUT_SECONDS", "210"))
    CREDILO_USE_REMOTE_IN_EXTRACTION: bool = os.getenv(
        "CREDILO_USE_REMOTE_IN_EXTRACTION",
        "true",
    ).lower() == "true"
    CREDILO_FALLBACK_TO_LOCAL: bool = os.getenv(
        "CREDILO_FALLBACK_TO_LOCAL",
        "true",
    ).lower() == "true"
    EXTRACTION_BANK_ANALYSIS_TIMEOUT_SECONDS: float = float(
        os.getenv("EXTRACTION_BANK_ANALYSIS_TIMEOUT_SECONDS", "180")
    )
    EXTRACTION_MAX_BANK_STATEMENTS_PER_RUN: int = int(
        os.getenv("EXTRACTION_MAX_BANK_STATEMENTS_PER_RUN", "3")
    )

    # Case ID Format
    CASE_ID_PREFIX: str = "CASE"

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()
