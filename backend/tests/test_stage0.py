"""Unit tests for Stage 0: Case Entry service."""
import io
from pathlib import Path
from uuid import UUID

import pytest
from fastapi import UploadFile
from sqlalchemy import select

from app.models.case import Case, Document
from app.services.stages.stage0_case_entry import CaseEntryService
from app.schemas.shared import CaseCreate, CaseUpdate
from app.core.enums import CaseStatus, EntityType, ProgramType
from app.utils.case_id_generator import generate_case_id, validate_case_id_format


class TestCaseIDGeneration:
    """Tests for case ID generation."""

    @pytest.mark.asyncio
    async def test_generate_first_case_id(self, db_session):
        """Test generating the first case ID of the day."""
        case_id = await generate_case_id(db_session)

        assert case_id is not None
        assert case_id.startswith("CASE-")
        assert validate_case_id_format(case_id)
        # Should end with 0001 for first case
        assert case_id.endswith("-0001")

    @pytest.mark.asyncio
    async def test_generate_sequential_case_ids(self, db_session, test_user_id):
        """Test that case IDs are generated sequentially."""
        # Create first case
        case1 = Case(
            case_id=await generate_case_id(db_session),
            user_id=test_user_id,
            status="created"
        )
        db_session.add(case1)
        await db_session.commit()

        # Create second case
        case2_id = await generate_case_id(db_session)

        # Extract counters
        counter1 = int(case1.case_id.split("-")[-1])
        counter2 = int(case2_id.split("-")[-1])

        assert counter2 == counter1 + 1

    @pytest.mark.asyncio
    async def test_validate_case_id_format(self):
        """Test case ID format validation."""
        # Valid formats
        assert validate_case_id_format("CASE-20240210-0001")
        assert validate_case_id_format("CASE-20240210-9999")

        # Invalid formats
        assert not validate_case_id_format("INVALID-20240210-0001")
        assert not validate_case_id_format("CASE-2024-0001")  # Wrong date format
        assert not validate_case_id_format("CASE-20240210-001")  # Wrong counter length
        assert not validate_case_id_format("CASE-20240210")  # Missing counter


class TestCaseCreation:
    """Tests for case creation."""

    @pytest.mark.asyncio
    async def test_create_case_minimal(self, db_session, test_user_id):
        """Test creating a case with minimal data."""
        service = CaseEntryService(db_session)

        result = await service.create_case(test_user_id)

        assert result is not None
        assert result.case_id.startswith("CASE-")
        assert result.status == CaseStatus.CREATED
        assert result.completeness_score == 0.0

    @pytest.mark.asyncio
    async def test_create_case_with_data(self, db_session, test_user_id):
        """Test creating a case with initial data."""
        service = CaseEntryService(db_session)

        case_data = CaseCreate(
            borrower_name="John Doe",
            entity_type=EntityType.PROPRIETORSHIP,
            program_type=ProgramType.BANKING,
            industry_type="Retail",
            pincode="110001",
            loan_amount_requested=500000.0
        )

        result = await service.create_case(test_user_id, case_data)

        assert result.borrower_name == "John Doe"
        assert result.entity_type == "proprietorship"
        assert result.program_type == ProgramType.BANKING
        assert result.completeness_score == 0.0

    @pytest.mark.asyncio
    async def test_create_multiple_cases_same_user(self, db_session, test_user_id):
        """Test creating multiple cases for the same user."""
        service = CaseEntryService(db_session)

        case1 = await service.create_case(test_user_id)
        case2 = await service.create_case(test_user_id)

        assert case1.case_id != case2.case_id
        assert case1.id != case2.id


class TestFileUpload:
    """Tests for file upload functionality."""

    @pytest.mark.asyncio
    async def test_upload_single_pdf(
        self,
        db_session,
        test_user_id,
        test_storage_path,
        sample_case,
        sample_pdf_file
    ):
        """Test uploading a single PDF file."""
        service = CaseEntryService(db_session)

        results = await service.upload_files(
            sample_case.case_id,
            [sample_pdf_file],
            test_user_id
        )

        assert len(results) == 1
        assert results[0].original_filename == "test_document.pdf"
        assert results[0].status == "uploaded"

        # Verify file was stored
        stored_file = test_storage_path / sample_case.case_id / "test_document.pdf"
        assert stored_file.exists()

    @pytest.mark.asyncio
    async def test_upload_single_image(
        self,
        db_session,
        test_user_id,
        test_storage_path,
        sample_case,
        sample_image_file
    ):
        """Test uploading a single image file."""
        service = CaseEntryService(db_session)

        results = await service.upload_files(
            sample_case.case_id,
            [sample_image_file],
            test_user_id
        )

        assert len(results) == 1
        assert results[0].original_filename == "test_image.png"

    @pytest.mark.asyncio
    async def test_upload_multiple_files(
        self,
        db_session,
        test_user_id,
        test_storage_path,
        sample_case,
        sample_pdf_file,
        sample_image_file
    ):
        """Test uploading multiple files at once."""
        service = CaseEntryService(db_session)

        results = await service.upload_files(
            sample_case.case_id,
            [sample_pdf_file, sample_image_file],
            test_user_id
        )

        assert len(results) == 2
        filenames = {doc.original_filename for doc in results}
        assert "test_document.pdf" in filenames
        assert "test_image.png" in filenames

    @pytest.mark.asyncio
    async def test_upload_updates_case_status(
        self,
        db_session,
        test_user_id,
        test_storage_path,
        sample_case,
        sample_pdf_file
    ):
        """Test that uploading files updates case status to PROCESSING."""
        service = CaseEntryService(db_session)

        await service.upload_files(
            sample_case.case_id,
            [sample_pdf_file],
            test_user_id
        )

        # Refresh case
        await db_session.refresh(sample_case)
        assert sample_case.status == CaseStatus.PROCESSING.value

    @pytest.mark.asyncio
    async def test_upload_duplicate_detection(
        self,
        db_session,
        test_user_id,
        test_storage_path,
        sample_case
    ):
        """Test that duplicate files are not uploaded twice."""
        service = CaseEntryService(db_session)

        # Create two identical files
        content = b"%PDF-1.4\n%Identical content\n%%EOF"

        file1 = UploadFile(
            filename="doc1.pdf",
            file=io.BytesIO(content),
            content_type="application/pdf"
        )

        file2 = UploadFile(
            filename="doc2.pdf",  # Different name, same content
            file=io.BytesIO(content),
            content_type="application/pdf"
        )

        # Upload both
        results = await service.upload_files(
            sample_case.case_id,
            [file1, file2],
            test_user_id
        )

        # Only first file should be uploaded (duplicate detected)
        assert len(results) == 1


class TestZIPHandling:
    """Tests for ZIP file extraction."""

    @pytest.mark.asyncio
    async def test_upload_zip_extracts_files(
        self,
        db_session,
        test_user_id,
        test_storage_path,
        sample_case,
        sample_zip_file
    ):
        """Test that ZIP files are extracted and individual files uploaded."""
        service = CaseEntryService(db_session)

        results = await service.upload_files(
            sample_case.case_id,
            [sample_zip_file],
            test_user_id
        )

        # Should extract 3 files (2 PDFs + 1 PNG, ignoring .DS_Store and __MACOSX)
        assert len(results) == 3

        filenames = {doc.original_filename for doc in results}
        assert "document1.pdf" in filenames
        assert "document2.pdf" in filenames  # Should be flattened
        assert "image.png" in filenames

        # Should NOT include ignored files
        assert ".DS_Store" not in filenames

    @pytest.mark.asyncio
    async def test_zip_flattens_directory_structure(
        self,
        db_session,
        test_user_id,
        test_storage_path,
        sample_case,
        sample_zip_file
    ):
        """Test that ZIP extraction flattens directory structure."""
        service = CaseEntryService(db_session)

        results = await service.upload_files(
            sample_case.case_id,
            [sample_zip_file],
            test_user_id
        )

        # Verify files are stored flat (not in subdirectories)
        for doc in results:
            storage_key_path = Path(doc.storage_key)
            # Should only have case_id and filename (no subdirs)
            assert len(storage_key_path.parts) == 2


class TestFileValidation:
    """Tests for file validation."""

    @pytest.mark.asyncio
    async def test_reject_oversized_file(
        self,
        db_session,
        test_user_id,
        test_storage_path,
        sample_case,
        large_file
    ):
        """Test that oversized files are rejected."""
        service = CaseEntryService(db_session)

        # Should not raise error, but should skip the large file
        results = await service.upload_files(
            sample_case.case_id,
            [large_file],
            test_user_id
        )

        # Large file should be skipped
        assert len(results) == 0

    @pytest.mark.asyncio
    async def test_reject_unsupported_extension(
        self,
        db_session,
        test_user_id,
        test_storage_path,
        sample_case
    ):
        """Test that files with unsupported extensions are rejected."""
        service = CaseEntryService(db_session)

        # Create a file with unsupported extension
        bad_file = UploadFile(
            filename="script.exe",
            file=io.BytesIO(b"fake executable"),
            content_type="application/x-executable"
        )

        results = await service.upload_files(
            sample_case.case_id,
            [bad_file],
            test_user_id
        )

        # Should be skipped
        assert len(results) == 0


class TestCaseRetrieval:
    """Tests for case retrieval operations."""

    @pytest.mark.asyncio
    async def test_get_case(self, db_session, test_user_id, sample_case):
        """Test retrieving a case by ID."""
        service = CaseEntryService(db_session)

        result = await service.get_case(sample_case.case_id, test_user_id)

        assert result.case_id == sample_case.case_id
        assert result.borrower_name == sample_case.borrower_name

    @pytest.mark.asyncio
    async def test_get_nonexistent_case(self, db_session, test_user_id):
        """Test retrieving a case that doesn't exist."""
        service = CaseEntryService(db_session)

        with pytest.raises(Exception):  # Should raise HTTPException (404)
            await service.get_case("CASE-20240210-9999", test_user_id)

    @pytest.mark.asyncio
    async def test_list_cases(self, db_session, test_user_id):
        """Test listing all cases for a user."""
        service = CaseEntryService(db_session)

        # Create multiple cases
        case1 = await service.create_case(test_user_id)
        case2 = await service.create_case(test_user_id)

        # List cases
        results = await service.list_cases(test_user_id)

        assert len(results) >= 2
        case_ids = {case.case_id for case in results}
        assert case1.case_id in case_ids
        assert case2.case_id in case_ids

    @pytest.mark.asyncio
    async def test_list_cases_empty(self, db_session):
        """Test listing cases when user has none."""
        service = CaseEntryService(db_session)

        # Use a different user ID
        other_user = UUID("00000000-0000-0000-0000-000000000002")

        results = await service.list_cases(other_user)
        assert len(results) == 0


class TestCaseUpdate:
    """Tests for case update operations."""

    @pytest.mark.asyncio
    async def test_update_case(self, db_session, test_user_id, sample_case):
        """Test updating case fields."""
        service = CaseEntryService(db_session)

        update_data = CaseUpdate(
            borrower_name="Updated Name",
            cibil_score_manual=750,
            monthly_turnover_manual=500000.0
        )

        result = await service.update_case(
            sample_case.case_id,
            test_user_id,
            update_data
        )

        assert result.borrower_name == "Updated Name"
        # Note: CaseResponse doesn't include manual fields, but they should be in DB

    @pytest.mark.asyncio
    async def test_update_partial_fields(self, db_session, test_user_id, sample_case):
        """Test updating only specific fields."""
        service = CaseEntryService(db_session)

        original_name = sample_case.borrower_name

        update_data = CaseUpdate(
            pincode="110002"  # Only update pincode
        )

        result = await service.update_case(
            sample_case.case_id,
            test_user_id,
            update_data
        )

        # Borrower name should remain unchanged
        await db_session.refresh(sample_case)
        assert sample_case.borrower_name == original_name


class TestCaseDeletion:
    """Tests for case deletion."""

    @pytest.mark.asyncio
    async def test_delete_case(self, db_session, test_user_id, sample_case):
        """Test soft deleting a case."""
        service = CaseEntryService(db_session)

        await service.delete_case(sample_case.case_id, test_user_id)

        # Refresh and check status
        await db_session.refresh(sample_case)
        assert sample_case.status == CaseStatus.FAILED.value

    @pytest.mark.asyncio
    async def test_delete_nonexistent_case(self, db_session, test_user_id):
        """Test deleting a case that doesn't exist."""
        service = CaseEntryService(db_session)

        with pytest.raises(Exception):  # Should raise HTTPException (404)
            await service.delete_case("CASE-20240210-9999", test_user_id)
