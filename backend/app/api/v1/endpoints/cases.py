"""Case management API endpoints."""
import asyncio
import io
import mimetypes
import zipfile
import re
import hashlib
import secrets
import logging
from typing import List, Optional
from uuid import UUID
from pathlib import Path
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, File, UploadFile, status, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select, func, or_, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.database import get_db
from app.core.deps import get_current_user
from app.models.case import BorrowerFeature, Case, Document, DocumentProcessingJob, CaseShareLink
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
from app.services.gst_api import get_gst_api_service
from app.core.config import settings

router = APIRouter(prefix="/cases", tags=["cases"])
logger = logging.getLogger(__name__)

GSTIN_RE = re.compile(r"^\d{2}[A-Z]{5}\d{4}[A-Z][A-Z\d]Z[A-Z\d]$", re.IGNORECASE)
PAN_RE = re.compile(r"^[A-Z]{5}\d{4}[A-Z]$", re.IGNORECASE)
CASE_ID_RE = re.compile(r"^CASE-\d{8}-\d{4}$", re.IGNORECASE)


class ShareLinkRequest(BaseModel):
    expires_in_hours: int = Field(default=72, ge=1, le=168)
    max_downloads: int = Field(default=10, ge=1, le=100)


class PipelineTriggerRequest(BaseModel):
    force: bool = Field(default=False, description="Force pipeline enqueue even when already complete")


async def _read_document_bytes(service: CaseEntryService, storage_key: str) -> Optional[bytes]:
    """Read document bytes from configured storage with safe fallbacks."""
    if not storage_key:
        return None

    file_content = await service.storage.get_file(storage_key)
    if file_content is not None:
        return file_content

    file_path = service.storage.get_file_path(storage_key)
    if file_path and file_path.exists():
        return file_path.read_bytes()

    raw_path = Path(storage_key)
    if raw_path.is_absolute() and raw_path.exists():
        return raw_path.read_bytes()

    return None


def _hash_share_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


async def _build_case_documents_archive_bytes(service: CaseEntryService, case: Case) -> bytes:
    archive_buffer = io.BytesIO()
    filename_counts: dict[str, int] = {}
    added_files = 0

    with zipfile.ZipFile(archive_buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as archive:
        for doc in case.documents:
            original_name = doc.original_filename or (
                Path(doc.storage_key).name if doc.storage_key else f"document_{doc.id}"
            )
            file_content = await _read_document_bytes(service, doc.storage_key) if doc.storage_key else None
            if file_content is not None:
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
                continue

            ocr_text = (doc.ocr_text or "").strip()
            if ocr_text:
                stem = Path(original_name).stem or f"document_{doc.id}"
                fallback_name = f"{stem}_ocr.txt"
                duplicate_idx = filename_counts.get(fallback_name, 0)
                filename_counts[fallback_name] = duplicate_idx + 1
                if duplicate_idx > 0:
                    fallback_name = f"{Path(fallback_name).stem}_{duplicate_idx}.txt"
                archive.writestr(
                    fallback_name,
                    "Original binary file is currently unavailable in storage.\n\n"
                    f"Source filename: {original_name}\n"
                    f"Document ID: {doc.id}\n\n"
                    "OCR TEXT:\n"
                    f"{ocr_text}",
                )
                added_files += 1

        if added_files == 0:
            archive.writestr(
                "README.txt",
                "No readable files were found for this case at download time. "
                "Please re-upload the latest documents and try again.",
            )

    archive_buffer.seek(0)
    return archive_buffer.getvalue()


def _detect_search_type(raw_term: str) -> str:
    value = (raw_term or "").strip()
    upper = value.upper()
    digits = re.sub(r"\D+", "", value)

    if CASE_ID_RE.match(upper):
        return "case_id"
    if GSTIN_RE.match(upper):
        return "gstin"
    if PAN_RE.match(upper):
        return "pan"
    if len(digits) >= 10:
        return "phone"
    return "company"


def _is_valid_gstin(gstin: Optional[str]) -> bool:
    if not gstin:
        return False
    return bool(GSTIN_RE.match(gstin.strip().upper()))


def _heuristic_pre_score(case_row: Case) -> dict:
    base = float(case_row.completeness_score or 0.0)
    if case_row.gstin:
        base += 8
    if case_row.business_vintage_years and case_row.business_vintage_years >= 2:
        base += 8
    if case_row.cibil_score_manual and case_row.cibil_score_manual >= 700:
        base += 12
    score = max(0.0, min(100.0, round(base, 2)))
    band = "HIGH" if score >= 75 else "MEDIUM" if score >= 50 else "LOW"
    return {"score": score, "band": band, "basis": "heuristic"}


@router.get("/gst/lookup/{gstin}")
async def lookup_gst_details(
    gstin: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Fetch GST details on-demand for case prefill forms.
    """
    normalized = (gstin or "").strip().upper()
    if not _is_valid_gstin(normalized):
        raise HTTPException(status_code=400, detail="Invalid GSTIN format")

    gst_service = get_gst_api_service()
    result = await gst_service.fetch_company_details(normalized)
    if not result:
        raise HTTPException(status_code=404, detail="GST details not found")

    return {
        "gstin": normalized,
        "gst_data": result,
        "validated": True,
    }


@router.get("/search/smart")
async def smart_case_search(
    q: str = Query(..., min_length=2, description="Company / GST / Case ID / PAN / Phone"),
    limit: int = Query(20, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Smart unified search with lightweight quick-view background checks.
    """
    search_term = q.strip()
    search_type = _detect_search_type(search_term)
    normalized_upper = search_term.upper()
    digits = re.sub(r"\D+", "", search_term)
    phone_tail = digits[-10:] if len(digits) >= 10 else digits

    query = (
        select(Case)
        .outerjoin(BorrowerFeature, BorrowerFeature.case_id == Case.id)
        .outerjoin(User, User.id == Case.user_id)
    )

    if search_type == "case_id":
        query = query.where(Case.case_id.ilike(f"%{normalized_upper}%"))
    elif search_type == "gstin":
        query = query.where(Case.gstin.ilike(f"%{normalized_upper}%"))
    elif search_type == "pan":
        query = query.where(BorrowerFeature.pan_number.ilike(f"%{normalized_upper}%"))
    elif search_type == "phone":
        query = query.where(
            or_(
                Case.whatsapp_number.ilike(f"%{phone_tail}%"),
                User.phone.ilike(f"%{phone_tail}%"),
            )
        )
    else:
        query = query.where(Case.borrower_name.ilike(f"%{search_term}%"))

    if current_user.role != "super_admin":
        if current_user.organization_id:
            query = query.where(Case.organization_id == current_user.organization_id)
        else:
            query = query.where(Case.user_id == current_user.id)

    query = query.order_by(Case.updated_at.desc()).distinct().limit(limit)
    rows = (await db.execute(query)).scalars().all()

    quick_view = None
    if rows:
        focus_case = rows[0]

        # PAN + duplicates check (same PAN across org-scoped cases)
        pan_row = await db.execute(
            select(BorrowerFeature.pan_number).where(BorrowerFeature.case_id == focus_case.id)
        )
        pan_value = (pan_row.scalar_one_or_none() or "").strip().upper()
        duplicate_count = 0
        duplicate_case_ids: list[str] = []
        if pan_value:
            duplicate_query = (
                select(Case.case_id)
                .join(BorrowerFeature, BorrowerFeature.case_id == Case.id)
                .where(BorrowerFeature.pan_number.ilike(pan_value))
            )
            if current_user.role != "super_admin":
                if current_user.organization_id:
                    duplicate_query = duplicate_query.where(Case.organization_id == current_user.organization_id)
                else:
                    duplicate_query = duplicate_query.where(Case.user_id == current_user.id)
            duplicate_rows = (await db.execute(duplicate_query)).scalars().all()
            duplicate_case_ids = [case_id for case_id in duplicate_rows if case_id != focus_case.case_id][:5]
            duplicate_count = max(len(duplicate_rows) - 1, 0)

        # Pre-score: use existing eligibility average if available, else heuristic.
        pre_score_row = await db.execute(
            text(
                """
                SELECT AVG(eligibility_score)::float AS avg_score
                FROM eligibility_results
                WHERE case_id = :case_uuid
                """
            ),
            {"case_uuid": focus_case.id},
        )
        pre_score_val = pre_score_row.scalar_one_or_none()
        if pre_score_val is not None:
            pre_score = {
                "score": round(float(pre_score_val), 2),
                "band": "HIGH" if float(pre_score_val) >= 75 else "MEDIUM" if float(pre_score_val) >= 50 else "LOW",
                "basis": "eligibility_results_avg",
            }
        else:
            pre_score = _heuristic_pre_score(focus_case)

        quick_view = {
            "case_id": focus_case.case_id,
            "company_name": focus_case.borrower_name,
            "status": focus_case.status,
            "gstin": focus_case.gstin,
            "pan_number": pan_value or None,
            "pincode": focus_case.pincode,
            "completeness_score": float(focus_case.completeness_score or 0),
            "gst_validation": {
                "is_valid_format": _is_valid_gstin(focus_case.gstin),
                "api_enriched": bool(focus_case.gst_data),
                "status": (focus_case.gst_data or {}).get("status") if isinstance(focus_case.gst_data, dict) else None,
            },
            "duplicate_pan": {
                "has_duplicates": duplicate_count > 0,
                "count": duplicate_count,
                "other_case_ids": duplicate_case_ids,
            },
            "eligibility_pre_score": pre_score,
            "insights": [
                "GST profile verified" if focus_case.gst_data else "GST profile pending verification",
                "PAN appears in multiple cases" if duplicate_count > 0 else "No PAN duplicate in scoped cases",
                f"Pre-score band: {pre_score['band']}",
            ],
        }

    return {
        "query": search_term,
        "detected_type": search_type,
        "matches": [CaseEntryService(db)._case_to_response(item).model_dump() for item in rows],
        "quick_view": quick_view,
    }


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
    return await service.create_case(current_user, case_data)


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
    return await service.upload_files(case_id, files, current_user)


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
    return await service.list_cases(current_user)


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
    return await service.get_case(case_id, current_user)


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
    return await service.update_case(case_id, current_user, case_data)


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
    await service.delete_case(case_id, current_user)
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
    case = await service._get_case_by_case_id(case_id, current_user)
    return [service._document_to_response(doc) for doc in case.documents]


@router.post("/{case_id}/documents/share-link")
async def create_case_documents_share_link(
    case_id: str,
    payload: ShareLinkRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Create a secure temporary public link for downloading full case document ZIP.
    """
    service = CaseEntryService(db)
    case = await service._get_case_by_case_id(case_id, current_user)

    token = secrets.token_urlsafe(32)
    token_hash = _hash_share_token(token)
    expires_at = datetime.now(timezone.utc) + timedelta(hours=payload.expires_in_hours)

    share_link = CaseShareLink(
        case_id=case.id,
        organization_id=getattr(case, "organization_id", None),
        created_by_user_id=current_user.id,
        token_hash=token_hash,
        expires_at=expires_at,
        max_downloads=payload.max_downloads,
        download_count=0,
        is_active=True,
    )
    db.add(share_link)
    await db.commit()
    await db.refresh(share_link)

    download_url = str(request.url_for("download_shared_case_archive", token=token))
    return {
        "status": "success",
        "case_id": case.case_id,
        "share_link_id": str(share_link.id),
        "download_url": download_url,
        "expires_at": share_link.expires_at,
        "max_downloads": share_link.max_downloads,
    }


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
    case = await service._get_case_by_case_id(case_id, current_user)

    if not case.documents:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No documents found for this case"
        )
    archive_bytes = await _build_case_documents_archive_bytes(service, case)
    return StreamingResponse(
        iter([archive_bytes]),
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{case_id}_documents.zip"'
        }
    )


@router.get("/share/{token}/download", name="download_shared_case_archive")
async def download_shared_case_archive(
    token: str,
    db: AsyncSession = Depends(get_db),
):
    """
    Public download endpoint backed by expiring secure token links.
    """
    token_hash = _hash_share_token(token)
    result = await db.execute(
        select(CaseShareLink).where(
            CaseShareLink.token_hash == token_hash,
            CaseShareLink.is_active.is_(True),
        )
    )
    share_link = result.scalar_one_or_none()
    if not share_link:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invalid or expired share link")

    now = datetime.now(timezone.utc)
    expires_at = share_link.expires_at
    if expires_at and expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at and now > expires_at:
        share_link.is_active = False
        await db.commit()
        raise HTTPException(status_code=status.HTTP_410_GONE, detail="Share link has expired")

    if int(share_link.download_count or 0) >= int(share_link.max_downloads or 1):
        share_link.is_active = False
        await db.commit()
        raise HTTPException(status_code=status.HTTP_410_GONE, detail="Share link download limit reached")

    case_result = await db.execute(
        select(Case)
        .where(Case.id == share_link.case_id)
        .options(selectinload(Case.documents))
    )
    case = case_result.scalar_one_or_none()
    if not case:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found")

    service = CaseEntryService(db)
    if not case.documents:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No documents found for this case")

    archive_bytes = await _build_case_documents_archive_bytes(service, case)

    share_link.download_count = int(share_link.download_count or 0) + 1
    share_link.last_accessed_at = now
    if share_link.download_count >= int(share_link.max_downloads or 1):
        share_link.is_active = False
    await db.commit()

    return StreamingResponse(
        iter([archive_bytes]),
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{case.case_id}_documents.zip"',
            "Cache-Control": "no-store",
        },
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
    case = await service._get_case_by_case_id(case_id, current_user)

    target_doc = next((doc for doc in case.documents if str(doc.id) == document_id), None)
    if not target_doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found for this case",
        )

    filename = target_doc.original_filename or Path(target_doc.storage_key).name or "document"
    file_content = await _read_document_bytes(service, target_doc.storage_key)
    if file_content is None:
        ocr_fallback = (target_doc.ocr_text or "").strip()
        if ocr_fallback:
            fallback_name = f"{Path(filename).stem or 'document'}_ocr.txt"
            return StreamingResponse(
                iter(
                    [
                        (
                            "Original binary file is currently unavailable in storage.\n\n"
                            f"Source filename: {filename}\n"
                            f"Document ID: {target_doc.id}\n\n"
                            "OCR TEXT:\n"
                            f"{ocr_fallback}"
                        ).encode("utf-8")
                    ]
                ),
                media_type="text/plain; charset=utf-8",
                headers={
                    "Content-Disposition": f'inline; filename="{fallback_name}"'
                },
            )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Unable to read this document file. Please re-upload and try again.",
        )

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
    case = await service._get_case_by_case_id(case_id, current_user)

    job_rows = await db.execute(
        select(DocumentProcessingJob.status, func.count(DocumentProcessingJob.id))
        .where(DocumentProcessingJob.case_id == case.id)
        .group_by(DocumentProcessingJob.status)
    )
    counts = {status: int(count) for status, count in job_rows.all()}
    queued = counts.get("queued", 0)
    processing = counts.get("processing", 0)
    completed = counts.get("completed", 0)
    failed = counts.get("failed", 0)
    total = queued + processing + completed + failed
    done = completed + failed
    completion_pct = int(round((done * 100 / total), 0)) if total > 0 else 100

    return {
        "case_id": case.case_id,
        "status": case.status,
        "updated_at": case.updated_at,
        "has_gst_data": bool(case.gst_data),
        "document_jobs": {
            "queued": queued,
            "processing": processing,
            "completed": completed,
            "failed": failed,
            "total": total,
            "in_progress": (queued + processing) > 0,
            "completion_pct": completion_pct,
        },
    }


@router.post("/{case_id}/pipeline/trigger")
async def trigger_case_pipeline(
    case_id: str,
    payload: PipelineTriggerRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Trigger full pipeline asynchronously (extract -> score -> report).

    This endpoint is intentionally non-blocking to avoid long-running HTTP requests
    behind reverse proxies/load balancers.
    """
    service = CaseEntryService(db)
    case = await service._get_case_by_case_id(case_id, current_user)

    doc_count_row = await db.execute(
        select(func.count(Document.id)).where(Document.case_id == case.id)
    )
    doc_count = int(doc_count_row.scalar_one() or 0)
    if doc_count == 0:
        raise HTTPException(
            status_code=400,
            detail="No documents uploaded for this case. Upload documents before running full pipeline.",
        )

    if case.status == "report_generated" and not payload.force:
        return {
            "status": "already_complete",
            "case_id": case.case_id,
            "message": "Report is already generated for this case.",
        }

    job_rows = await db.execute(
        select(DocumentProcessingJob.status, func.count(DocumentProcessingJob.id))
        .where(DocumentProcessingJob.case_id == case.id)
        .group_by(DocumentProcessingJob.status)
    )
    counts = {status: int(count) for status, count in job_rows.all()}
    queued = counts.get("queued", 0)
    processing = counts.get("processing", 0)
    pending = queued + processing

    # Upload flow already enqueues full pipeline automatically.
    # If OCR/classification is still in progress, avoid duplicate pipeline jobs.
    if pending > 0 and not payload.force:
        return {
            "status": "waiting_for_documents",
            "case_id": case.case_id,
            "message": (
                "Document processing is still running. "
                "Full pipeline will continue in background after queue completion."
            ),
            "document_jobs": {
                "queued": queued,
                "processing": processing,
                "completed": counts.get("completed", 0),
                "failed": counts.get("failed", 0),
                "total": sum(counts.values()),
            },
        }

    if settings.RQ_ASYNC_ENABLED:
        try:
            from app.services.rq_queue import enqueue_case_pipeline_job

            job_id = enqueue_case_pipeline_job(case.case_id)
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=503, detail=f"Failed to queue pipeline: {exc}")

        case.status = "processing"
        await db.commit()

        return {
            "status": "queued",
            "case_id": case.case_id,
            "job_id": job_id,
            "message": "Full pipeline queued successfully.",
        }

    # Non-blocking in-process fallback for local/non-RQ mode.
    try:
        from app.services.jobs import run_case_pipeline_async

        async def _run_inprocess_pipeline(target_case_id: str) -> None:
            try:
                await run_case_pipeline_async(target_case_id)
            except Exception as exc:  # noqa: BLE001
                logger.error(
                    "In-process pipeline failed for case %s: %s",
                    target_case_id,
                    exc,
                    exc_info=True,
                )

        case.status = "processing"
        await db.commit()
        asyncio.create_task(_run_inprocess_pipeline(case.case_id))
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=503, detail=f"Failed to start in-process pipeline: {exc}")

    return {
        "status": "queued_local",
        "case_id": case.case_id,
        "message": "Pipeline started in background (in-process mode).",
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
    case = await service._get_case_by_case_id(case_id, current_user)

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
