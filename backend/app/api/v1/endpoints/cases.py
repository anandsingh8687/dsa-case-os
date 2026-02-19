"""Case management API endpoints."""
import io
import mimetypes
import zipfile
from typing import List, Optional
from uuid import UUID
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, File, UploadFile, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.core.deps import get_current_user
from app.models.user import User
from app.schemas.shared import (
    CaseCreate,
    CaseResponse,
    CaseUpdate,
    CaseSummary,
    DocumentResponse,
    DocumentChecklist,
    ManualFieldPrompt
)
from app.services.stages.stage0_case_entry import CaseEntryService
from app.services.stages.stage1_checklist import ChecklistEngine

router = APIRouter(prefix="/cases", tags=["cases"])


async def _read_document_bytes(service: CaseEntryService, storage_key: str) -> Optional[bytes]:
    """Read document bytes from configured storage with safe fallbacks."""
    if not storage_key:
        return None

    file_content = await service.storage.get_file(storage_key)
    if file_content:
        return file_content

    file_path = service.storage.get_file_path(storage_key)
    if file_path and file_path.exists():
        return file_path.read_bytes()

    raw_path = Path(storage_key)
    if raw_path.is_absolute() and raw_path.exists():
        return raw_path.read_bytes()

    return None


@router.post("/", response_model=CaseResponse, status_code=status.HTTP_201_CREATED)
async def create_case(
    case_data: CaseCreate = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Create a new case.

    Args:
        case_data: Optional initial case data (borrower info, loan details)
        db: Database session
        user_id: Current user ID (from auth)

    Returns:
        CaseResponse with generated case_id and initial state
    """
    service = CaseEntryService(db)
    return await service.create_case(current_user.id, case_data)


@router.post("/{case_id}/upload", response_model=List[DocumentResponse])
async def upload_documents(
    case_id: str,
    files: List[UploadFile] = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Upload documents to a case.

    Supports:
    - Single files: PDF, JPG, JPEG, PNG, TIFF
    - ZIP archives (auto-extracted and flattened)

    Features:
    - Duplicate detection (SHA-256 hash)
    - File size validation (max 25MB per file, 100MB per upload)
    - Ignores .DS_Store, __MACOSX, etc.

    Args:
        case_id: Case ID to upload to
        files: List of files to upload
        db: Database session
        current_user: Current authenticated user

    Returns:
        List of DocumentResponse for uploaded documents

    Raises:
        404: Case not found
        413: File(s) too large
        400: Invalid file format
    """
    service = CaseEntryService(db)
    return await service.upload_files(case_id, files, current_user.id)


@router.get("/", response_model=List[CaseResponse])
async def list_cases(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    List all cases for the current user.

    Args:
        db: Database session
        user_id: Current user ID (from auth)

    Returns:
        List of cases ordered by creation date (newest first)
    """
    service = CaseEntryService(db)
    return await service.list_cases(current_user.id)


@router.get("/{case_id}", response_model=CaseResponse)
async def get_case(
    case_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get detailed information about a specific case.

    Args:
        case_id: Case ID (format: CASE-YYYYMMDD-XXXX)
        db: Database session
        user_id: Current user ID (from auth)

    Returns:
        CaseResponse with full case details

    Raises:
        404: Case not found or doesn't belong to user
    """
    service = CaseEntryService(db)
    return await service.get_case(case_id, current_user.id)


@router.patch("/{case_id}", response_model=CaseResponse)
async def update_case(
    case_id: str,
    case_data: CaseUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Update case with manual overrides.

    Use this to:
    - Override extracted values
    - Add missing information
    - Correct misclassified data

    Args:
        case_id: Case ID to update
        case_data: Fields to update (only provided fields are updated)
        db: Database session
        user_id: Current user ID (from auth)

    Returns:
        Updated CaseResponse

    Raises:
        404: Case not found
    """
    service = CaseEntryService(db)
    return await service.update_case(case_id, current_user.id, case_data)


@router.delete("/{case_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_case(
    case_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Permanently delete a case owned by current user.

    Associated DB records are deleted via cascade relationships.
    Uploaded file cleanup is attempted in storage backend.

    Args:
        case_id: Case ID to delete
        db: Database session
        user_id: Current user ID (from auth)

    Raises:
        404: Case not found
    """
    service = CaseEntryService(db)
    await service.delete_case(case_id, current_user.id)
    return None


@router.get("/{case_id}/documents", response_model=List[DocumentResponse])
async def get_case_documents(
    case_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get all uploaded documents for a case.

    Args:
        case_id: Case ID
        db: Database session
        current_user: Current authenticated user

    Returns:
        List of DocumentResponse with document details
    """
    service = CaseEntryService(db)
    case = await service._get_case_by_case_id(case_id, current_user.id)
    return [service._document_to_response(doc) for doc in case.documents]


@router.get("/{case_id}/documents/archive")
async def download_case_documents_archive(
    case_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Download all uploaded case documents as a ZIP archive.

    Useful for one-click lender sharing from the report/email workflow.
    """
    service = CaseEntryService(db)
    case = await service._get_case_by_case_id(case_id, current_user.id)

    if not case.documents:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No documents found for this case"
        )

    archive_buffer = io.BytesIO()
    filename_counts = {}
    added_files = 0

    with zipfile.ZipFile(archive_buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as archive:
        for doc in case.documents:
            if not doc.storage_key:
                continue
            file_content = await _read_document_bytes(service, doc.storage_key)
            if not file_content:
                continue

            original_name = doc.original_filename or Path(doc.storage_key).name
            duplicate_idx = filename_counts.get(original_name, 0)
            filename_counts[original_name] = duplicate_idx + 1

            if duplicate_idx > 0:
                stem = Path(original_name).stem
                suffix = Path(original_name).suffix
                archive_name = f"{stem}_{duplicate_idx}{suffix}"
            else:
                archive_name = original_name

            archive.writestr(archive_name, file_content)
            added_files += 1

        if added_files == 0:
            archive.writestr(
                "README.txt",
                "No readable files were found for this case at download time. "
                "Please re-upload the latest documents and try again.",
            )

    archive_buffer.seek(0)
    return StreamingResponse(
        iter([archive_buffer.getvalue()]),
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{case_id}_documents.zip"'
        }
    )


@router.get("/{case_id}/documents/{document_id}/preview")
async def preview_case_document(
    case_id: str,
    document_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Preview/download one case document in-browser."""
    service = CaseEntryService(db)
    case = await service._get_case_by_case_id(case_id, current_user.id)

    target_doc = next((doc for doc in case.documents if str(doc.id) == document_id), None)
    if not target_doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found for this case",
        )

    file_content = await _read_document_bytes(service, target_doc.storage_key)
    if not file_content:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Unable to read this document file. Please re-upload and try again.",
        )

    filename = target_doc.original_filename or Path(target_doc.storage_key).name or "document"
    media_type = target_doc.mime_type or mimetypes.guess_type(filename)[0] or "application/octet-stream"

    return StreamingResponse(
        iter([file_content]),
        media_type=media_type,
        headers={
            "Content-Disposition": f'inline; filename="{filename}"'
        }
    )


@router.get("/{case_id}/checklist", response_model=DocumentChecklist)
async def get_case_checklist(
    case_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get document completeness checklist for a case.

    Shows:
    - Available documents
    - Missing required documents
    - Optional documents present
    - Completeness score (0-100)
    - Unreadable files (failed OCR/classification)

    Args:
        case_id: Case ID (format: CASE-YYYYMMDD-XXXX)
        db: Database session
        user_id: Current user ID (from auth)

    Returns:
        DocumentChecklist with completeness analysis

    Raises:
        404: Case not found
        400: Program type not set
    """
    try:
        checklist_engine = ChecklistEngine(db)
        return await checklist_engine.generate_checklist(case_id, current_user.id)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.get("/{case_id}/manual-prompts", response_model=List[ManualFieldPrompt])
async def get_manual_field_prompts(
    case_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get progressive data capture prompts for missing documents.

    When certain documents are missing, prompt user to manually enter data:
    - CIBIL report missing → prompt for CIBIL score
    - GST certificate missing → prompt for business vintage & entity type
    - GST returns missing → prompt for monthly turnover

    Args:
        case_id: Case ID
        db: Database session
        user_id: Current user ID (from auth)

    Returns:
        List of ManualFieldPrompt for fields that can be manually entered

    Raises:
        404: Case not found
    """
    try:
        checklist_engine = ChecklistEngine(db)
        return await checklist_engine.get_missing_manual_prompts(case_id, current_user.id)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )


@router.get("/{case_id}/status")
async def get_case_status(
    case_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get lightweight processing status for a case.

    Used by frontend polling after document upload to avoid fixed delays.
    """
    service = CaseEntryService(db)
    case = await service._get_case_by_case_id(case_id, current_user.id)

    return {
        "case_id": case.case_id,
        "status": case.status,
        "updated_at": case.updated_at,
        "has_gst_data": bool(case.gst_data),
    }


@router.get("/{case_id}/gst-data")
async def get_gst_data(
    case_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get extracted GST data for a case.

    Returns the raw GST API response data if available, along with metadata
    about when it was fetched.

    Args:
        case_id: Case ID
        db: Database session
        current_user: Current authenticated user

    Returns:
        Dict with GST data, GSTIN, and fetch timestamp

    Raises:
        404: Case not found or no GST data available
    """
    service = CaseEntryService(db)
    case = await service._get_case_by_case_id(case_id, current_user.id)

    if not case.gst_data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No GST data available for this case"
        )

    return {
        "gstin": case.gstin,
        "gst_data": case.gst_data,
        "fetched_at": case.gst_fetched_at,
        "case_id": case.case_id
    }
