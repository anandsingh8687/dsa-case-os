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

    # WhatsApp Service
    WHATSAPP_SERVICE_URL: str = os.getenv("WHATSAPP_SERVICE_URL", "http://localhost:3001")

    # Case ID Format
    CASE_ID_PREFIX: str = "CASE"

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()
