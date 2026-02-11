"""Pytest configuration and fixtures for testing."""
import asyncio
import io
import os
import shutil
import zipfile
from pathlib import Path
from typing import AsyncGenerator, Generator
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from fastapi import UploadFile

from app.models.base import Base
from app.models.case import Case, Document
from app.core.config import settings


# Test database URL
TEST_DATABASE_URL = "postgresql+asyncpg://postgres:postgres@localhost:5432/dsa_case_os_test"

# Test user ID
TEST_USER_ID = UUID("00000000-0000-0000-0000-000000000001")


@pytest.fixture(scope="session")
def event_loop() -> Generator:
    """Create an event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="function")
async def db_engine():
    """Create a test database engine."""
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)

    # Create all tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    # Drop all tables after tests
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    await engine.dispose()


@pytest_asyncio.fixture(scope="function")
async def db_session(db_engine) -> AsyncGenerator[AsyncSession, None]:
    """Create a test database session."""
    async_session = async_sessionmaker(
        db_engine,
        class_=AsyncSession,
        expire_on_commit=False
    )

    async with async_session() as session:
        yield session
        await session.rollback()


@pytest.fixture(scope="function")
def test_storage_path(tmp_path) -> Generator[Path, None, None]:
    """Create a temporary storage path for test files."""
    storage_path = tmp_path / "test_uploads"
    storage_path.mkdir(parents=True, exist_ok=True)

    # Override settings
    original_path = settings.LOCAL_STORAGE_PATH
    settings.LOCAL_STORAGE_PATH = str(storage_path)

    yield storage_path

    # Cleanup
    settings.LOCAL_STORAGE_PATH = original_path
    if storage_path.exists():
        shutil.rmtree(storage_path)


@pytest.fixture
def test_user_id() -> UUID:
    """Return a test user ID."""
    return TEST_USER_ID


@pytest.fixture
def sample_pdf_file() -> Generator[UploadFile, None, None]:
    """Create a sample PDF file for testing."""
    content = b"%PDF-1.4\n%Test PDF content\n%%EOF"
    file = io.BytesIO(content)

    upload_file = UploadFile(
        filename="test_document.pdf",
        file=file,
        content_type="application/pdf"
    )

    yield upload_file

    file.close()


@pytest.fixture
def sample_image_file() -> Generator[UploadFile, None, None]:
    """Create a sample image file for testing."""
    # Minimal valid PNG file (1x1 pixel, red)
    content = (
        b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01'
        b'\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\xcf'
        b'\xc0\x00\x00\x00\x03\x00\x01\x00\x18\xdd\x8d\xb4\x00\x00\x00\x00IEND\xaeB`\x82'
    )
    file = io.BytesIO(content)

    upload_file = UploadFile(
        filename="test_image.png",
        file=file,
        content_type="image/png"
    )

    yield upload_file

    file.close()


@pytest.fixture
def sample_zip_file() -> Generator[UploadFile, None, None]:
    """Create a sample ZIP file containing multiple test files."""
    zip_buffer = io.BytesIO()

    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
        # Add a PDF
        zf.writestr("document1.pdf", b"%PDF-1.4\n%Test PDF 1\n%%EOF")

        # Add another PDF in a subdirectory
        zf.writestr("subfolder/document2.pdf", b"%PDF-1.4\n%Test PDF 2\n%%EOF")

        # Add an image
        png_content = (
            b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01'
            b'\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\xcf'
            b'\xc0\x00\x00\x00\x03\x00\x01\x00\x18\xdd\x8d\xb4\x00\x00\x00\x00IEND\xaeB`\x82'
        )
        zf.writestr("image.png", png_content)

        # Add ignored files (should be skipped)
        zf.writestr(".DS_Store", b"junk")
        zf.writestr("__MACOSX/._document1.pdf", b"junk")

    zip_buffer.seek(0)

    upload_file = UploadFile(
        filename="test_archive.zip",
        file=zip_buffer,
        content_type="application/zip"
    )

    yield upload_file

    zip_buffer.close()


@pytest.fixture
def large_file() -> Generator[UploadFile, None, None]:
    """Create a large file that exceeds size limits."""
    # Create a file slightly larger than MAX_FILE_SIZE_MB
    size_mb = settings.MAX_FILE_SIZE_MB + 1
    content = b"x" * (size_mb * 1024 * 1024)

    file = io.BytesIO(content)

    upload_file = UploadFile(
        filename="large_file.pdf",
        file=file,
        content_type="application/pdf"
    )

    yield upload_file

    file.close()


@pytest_asyncio.fixture
async def sample_case(db_session: AsyncSession, test_user_id: UUID) -> Case:
    """Create a sample case for testing."""
    case = Case(
        case_id="CASE-20240210-0001",
        user_id=test_user_id,
        status="created",
        borrower_name="Test Borrower",
        entity_type="proprietorship"
    )

    db_session.add(case)
    await db_session.commit()
    await db_session.refresh(case)

    return case


@pytest_asyncio.fixture
async def sample_document(
    db_session: AsyncSession,
    sample_case: Case,
    test_storage_path: Path
) -> Document:
    """Create a sample document for testing."""
    # Create a test file in storage
    case_dir = test_storage_path / sample_case.case_id
    case_dir.mkdir(parents=True, exist_ok=True)

    test_file_path = case_dir / "test_doc.pdf"
    test_file_path.write_bytes(b"%PDF-1.4\n%Test\n%%EOF")

    document = Document(
        case_id=sample_case.id,
        original_filename="test_doc.pdf",
        storage_key=f"{sample_case.case_id}/test_doc.pdf",
        file_size_bytes=23,
        mime_type="application/pdf",
        file_hash="abc123",
        status="uploaded"
    )

    db_session.add(document)
    await db_session.commit()
    await db_session.refresh(document)

    return document
