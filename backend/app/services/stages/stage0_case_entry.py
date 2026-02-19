"""Stage 0: Case Entry (Chaos Ingestion) - File upload and case creation service."""
import io
import mimetypes
import zipfile
import re
from typing import List, Optional, BinaryIO, Tuple
from pathlib import Path
from uuid import UUID
import logging

from fastapi import UploadFile, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text
from sqlalchemy.orm import selectinload

from app.models.case import Case, Document, DocumentProcessingJob
from app.schemas.shared import CaseCreate, CaseResponse, CaseUpdate, DocumentResponse
from app.core.enums import CaseStatus, DocumentStatus
from app.core.config import settings
from app.services.file_storage import get_storage_backend, compute_file_hash
from app.utils.case_id_generator import generate_case_id
from app.services.document_processor import document_processor
from app.services.stages.stage1_classifier import classify_document
from app.services.gst_api import get_gst_api_service, GSTAPIService
from datetime import datetime as dt

logger = logging.getLogger(__name__)

# File validation constants
ALLOWED_EXTENSIONS = settings.ALLOWED_EXTENSIONS
MAX_FILE_SIZE_BYTES = settings.MAX_FILE_SIZE_MB * 1024 * 1024
MAX_CASE_UPLOAD_BYTES = settings.MAX_CASE_UPLOAD_MB * 1024 * 1024

# Files/folders to ignore in ZIP extraction
IGNORED_FILES = {".DS_Store", "Thumbs.db", "desktop.ini"}
IGNORED_FOLDERS = {"__MACOSX", ".git", ".svn"}
GSTIN_FILENAME_REGEX = re.compile(r"\b\d{2}[A-Z]{5}\d{4}[A-Z][A-Z\d]Z[A-Z\d]\b", re.IGNORECASE)


class CaseEntryService:
    """Service for creating cases and handling file uploads (Stage 0)."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.storage = get_storage_backend()

    async def create_case(
        self,
        user_id: UUID,
        case_data: Optional[CaseCreate] = None
    ) -> CaseResponse:
        """
        Create a new case.

        Args:
            user_id: ID of the user creating the case
            case_data: Optional initial case data

        Returns:
            CaseResponse with created case details
        """
        try:
            # Generate unique case ID
            case_id = await generate_case_id(self.db)

            # Create case record
            case = Case(
                case_id=case_id,
                user_id=user_id,
                status=CaseStatus.CREATED.value,
                borrower_name=case_data.borrower_name if case_data else None,
                entity_type=case_data.entity_type.value if case_data and case_data.entity_type else None,
                program_type=case_data.program_type.value if case_data and case_data.program_type else None,
                industry_type=case_data.industry_type if case_data else None,
                pincode=case_data.pincode if case_data else None,
                loan_amount_requested=case_data.loan_amount_requested if case_data else None,
            )

            self.db.add(case)
            await self.db.commit()
            await self.db.refresh(case)

            logger.info(f"Created case: {case.case_id} for user: {user_id}")

            return self._case_to_response(case)

        except Exception as e:
            await self.db.rollback()
            logger.error(f"Failed to create case: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to create case: {str(e)}"
            )

    async def upload_files(
        self,
        case_id: str,
        files: List[UploadFile],
        user_id: UUID
    ) -> List[DocumentResponse]:
        """
        Upload files to a case. Handles single files and ZIP archives.

        Features:
        - File size validation (max 25MB per file, 100MB per case upload)
        - Duplicate detection via SHA-256 hash
        - ZIP extraction with auto-flattening
        - Ignores .DS_Store, __MACOSX, etc.

        Args:
            case_id: Case ID to upload files to
            files: List of uploaded files
            user_id: ID of the user uploading files

        Returns:
            List of DocumentResponse for uploaded documents

        Raises:
            HTTPException: If validation fails or upload errors occur
        """
        try:
            # Get case and verify ownership
            case = await self._get_case_by_case_id(case_id, user_id)

            # Validate total upload size
            total_size = 0
            for file in files:
                total_size += await self._get_file_size(file)
            if total_size > MAX_CASE_UPLOAD_BYTES:
                raise HTTPException(
                    status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    detail=f"Total upload size ({total_size / (1024*1024):.2f}MB) exceeds limit "
                           f"({settings.MAX_CASE_UPLOAD_MB}MB)"
                )

            uploaded_documents = []

            # Process each file
            for file in files:
                # Validate file size
                file_size = await self._get_file_size(file)
                if file_size > MAX_FILE_SIZE_BYTES:
                    logger.warning(f"File {file.filename} exceeds size limit, skipping")
                    continue

                # Validate extension
                extension = Path(file.filename).suffix.lower().lstrip(".")
                if extension not in ALLOWED_EXTENSIONS:
                    logger.warning(f"File {file.filename} has unsupported extension, skipping")
                    continue

                # Handle ZIP files
                if extension == "zip":
                    zip_documents = await self._process_zip_file(file, case)
                    uploaded_documents.extend(zip_documents)
                else:
                    # Handle regular file
                    document = await self._process_single_file(file, case)
                    if document:
                        uploaded_documents.append(document)

            # Update case status to PROCESSING
            case.status = CaseStatus.PROCESSING.value
            await self.db.commit()

            # Update completeness score if program type is set
            if case.program_type:
                await self._update_case_completeness(case_id, user_id)

            logger.info(f"Uploaded {len(uploaded_documents)} documents to case {case_id}")

            return [self._document_to_response(doc) for doc in uploaded_documents]

        except HTTPException:
            raise
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Failed to upload files to case {case_id}: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to upload files: {str(e)}"
            )

    async def _process_single_file(
        self,
        file: UploadFile,
        case: Case
    ) -> Optional[Document]:
        """Process a single file upload with automatic OCR and classification."""
        try:
            # Read file data
            file_data = await file.read()
            file_stream = io.BytesIO(file_data)

            # Compute hash for duplicate detection
            file_hash = compute_file_hash(file_stream)

            # Check for duplicate
            existing_doc = await self._find_duplicate_document(case.id, file_hash)
            if existing_doc:
                logger.info(f"Duplicate file detected: {file.filename} (hash: {file_hash[:16]}...)")
                return None

            # Store file
            storage_key = await self.storage.store_file(
                file_stream,
                case.case_id,
                file.filename
            )

            # Determine MIME type
            mime_type = file.content_type or mimetypes.guess_type(file.filename)[0] or "application/octet-stream"

            # Create document record
            document = Document(
                case_id=case.id,
                original_filename=file.filename,
                storage_key=storage_key,
                file_size_bytes=len(file_data),
                mime_type=mime_type,
                file_hash=file_hash,
                status=DocumentStatus.UPLOADED.value
            )

            self.db.add(document)
            await self.db.flush()

            logger.info(f"Processed file: {file.filename} -> {storage_key}")

            # Queue asynchronous OCR/classification job.
            await self._enqueue_processing_job(case.id, document.id)

            return document

        except Exception as e:
            logger.error(f"Failed to process file {file.filename}: {e}")
            raise

    async def _run_ocr_and_classification(self, document: Document, storage_key: str) -> None:
        """Run OCR and classification on a newly uploaded document.

        Args:
            document: Document record
            storage_key: Storage key for the file
        """
        try:
            # Fast filename classification pass first to avoid unnecessary OCR on obvious docs.
            filename_classification = classify_document("", filename=document.original_filename)

            from app.core.enums import DocumentType

            def _should_skip_ocr(initial_doc_type: DocumentType) -> bool:
                filename_lower = (document.original_filename or "").lower()
                is_photo = "photo" in filename_lower or filename_lower.endswith((".jpg", ".jpeg", ".png"))

                if initial_doc_type == DocumentType.BANK_STATEMENT:
                    return True
                if initial_doc_type == DocumentType.GST_RETURNS:
                    # Most GST return files carry GSTIN in filename; skip heavy OCR if available.
                    return bool(self._extract_gstin_from_filename(document.original_filename))
                if initial_doc_type == DocumentType.GST_CERTIFICATE:
                    return False
                if initial_doc_type in {
                    DocumentType.PAN_PERSONAL,
                    DocumentType.PAN_BUSINESS,
                    DocumentType.AADHAAR,
                    DocumentType.CIBIL_REPORT,
                }:
                    return False
                if initial_doc_type == DocumentType.UNKNOWN and is_photo:
                    return True
                return initial_doc_type != DocumentType.UNKNOWN

            if filename_classification.doc_type.value != "unknown":
                document.doc_type = filename_classification.doc_type.value
                document.classification_confidence = filename_classification.confidence
                document.status = DocumentStatus.CLASSIFIED.value
                await self.db.flush()

                # If GST doc has GSTIN in filename, fetch GST data without OCR.
                if filename_classification.doc_type in [DocumentType.GST_CERTIFICATE, DocumentType.GST_RETURNS]:
                    gstin_from_filename = self._extract_gstin_from_filename(document.original_filename)
                    if gstin_from_filename:
                        await self._fetch_and_apply_gst_data(document, gstin_from_filename)

                if _should_skip_ocr(filename_classification.doc_type):
                    logger.info(
                        "Skipping OCR for %s (doc_type=%s, filename-first classification)",
                        document.original_filename,
                        filename_classification.doc_type.value,
                    )
                    return

            # Get file path from storage
            file_path = self.storage.get_file_path(storage_key)

            if not file_path or not file_path.exists():
                logger.warning(f"File not found for OCR: {storage_key}")
                return

            # Run OCR
            logger.info(f"Running OCR on document {document.id} ({document.original_filename})")
            ocr_result = await document_processor.process_document_ocr(
                self.db,
                document.id,
                str(file_path)
            )

            # Run classification if OCR produced at least some text.
            if ocr_result and ocr_result.text and len(ocr_result.text.strip()) > 3:
                logger.info(f"Running classification on document {document.id}")
                # IMPROVED: Pass filename for better classification
                classification_result = classify_document(ocr_result.text, filename=document.original_filename)

                # Update document with classification results
                document.doc_type = classification_result.doc_type.value
                document.classification_confidence = classification_result.confidence
                document.status = DocumentStatus.CLASSIFIED.value

                await self.db.flush()

                logger.info(
                    f"Document {document.id} classified as {classification_result.doc_type.value} "
                    f"(confidence: {classification_result.confidence:.2f}, method: {classification_result.method})"
                )

                # === AUTO-EXTRACT GSTIN AND CALL GST API ===
                # Check if document is GST-related
                if classification_result.doc_type in [DocumentType.GST_CERTIFICATE, DocumentType.GST_RETURNS]:
                    await self._extract_and_fetch_gst_data(document, ocr_result.text)

            else:
                # Even with short/no OCR text, try filename-based classification
                logger.warning(f"OCR text too short, trying filename-based classification: {document.id}")
                classification_result = classify_document("", filename=document.original_filename)

                if classification_result.doc_type.value != "unknown":
                    # Update with filename-based classification
                    document.doc_type = classification_result.doc_type.value
                    document.classification_confidence = classification_result.confidence
                    document.status = DocumentStatus.CLASSIFIED.value

                    await self.db.flush()

                    logger.info(
                        f"Document {document.id} classified from filename as {classification_result.doc_type.value} "
                        f"(confidence: {classification_result.confidence:.2f})"
                    )

                    # Try GST extraction even when OCR text is short; GSTIN may still be present.
                    if classification_result.doc_type in [DocumentType.GST_CERTIFICATE, DocumentType.GST_RETURNS]:
                        await self._extract_and_fetch_gst_data(
                            document,
                            (ocr_result.text if ocr_result and ocr_result.text else "")
                        )

        except Exception as e:
            logger.error(f"Failed to run OCR/classification for document {document.id}: {e}", exc_info=True)
            # Don't fail the upload if OCR/classification fails
            # Document is already uploaded successfully

    async def _process_zip_file(
        self,
        zip_file: UploadFile,
        case: Case
    ) -> List[Document]:
        """
        Extract and process files from a ZIP archive.

        Features:
        - Auto-flattens nested folder structure
        - Ignores .DS_Store, __MACOSX, etc.
        - Validates extracted files
        - Duplicate detection per file

        Args:
            zip_file: Uploaded ZIP file
            case: Case to associate files with

        Returns:
            List of created Document records
        """
        documents = []

        try:
            # Read ZIP file
            zip_data = await zip_file.read()
            zip_stream = io.BytesIO(zip_data)

            with zipfile.ZipFile(zip_stream, 'r') as zf:
                # Get list of files to extract
                file_list = zf.namelist()

                for file_path in file_list:
                    # Skip directories
                    if file_path.endswith('/'):
                        continue

                    # Parse path
                    path_parts = Path(file_path).parts
                    filename = Path(file_path).name

                    # Skip ignored files and folders
                    if filename in IGNORED_FILES:
                        continue
                    if any(folder in IGNORED_FOLDERS for folder in path_parts):
                        continue

                    # Validate extension
                    extension = Path(filename).suffix.lower().lstrip(".")
                    if extension not in ALLOWED_EXTENSIONS or extension == "zip":
                        logger.warning(f"Skipping unsupported file in ZIP: {filename}")
                        continue

                    # Extract file
                    try:
                        file_data = zf.read(file_path)

                        # Validate file size
                        if len(file_data) > MAX_FILE_SIZE_BYTES:
                            logger.warning(f"File {filename} in ZIP exceeds size limit, skipping")
                            continue

                        file_stream = io.BytesIO(file_data)

                        # Compute hash
                        file_hash = compute_file_hash(file_stream)

                        # Check for duplicate
                        existing_doc = await self._find_duplicate_document(case.id, file_hash)
                        if existing_doc:
                            logger.info(f"Duplicate file in ZIP: {filename}")
                            continue

                        # Store file
                        storage_key = await self.storage.store_file(
                            file_stream,
                            case.case_id,
                            filename  # Use flattened filename
                        )

                        # Determine MIME type
                        mime_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"

                        # Create document record
                        document = Document(
                            case_id=case.id,
                            original_filename=filename,
                            storage_key=storage_key,
                            file_size_bytes=len(file_data),
                            mime_type=mime_type,
                            file_hash=file_hash,
                            status=DocumentStatus.UPLOADED.value
                        )

                        self.db.add(document)
                        await self.db.flush()

                        documents.append(document)
                        logger.info(f"Extracted from ZIP: {filename}")

                        # Queue asynchronous OCR/classification for this file.
                        await self._enqueue_processing_job(case.id, document.id)

                    except Exception as e:
                        logger.error(f"Failed to extract {file_path} from ZIP: {e}")
                        continue

            return documents

        except zipfile.BadZipFile:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid ZIP file"
            )
        except Exception as e:
            logger.error(f"Failed to process ZIP file: {e}")
            raise

    async def _enqueue_processing_job(self, case_uuid: UUID, document_uuid: UUID) -> None:
        """Create a persistent OCR/classification job for worker queue."""
        job = DocumentProcessingJob(
            case_id=case_uuid,
            document_id=document_uuid,
            status="queued",
            attempts=0,
            max_attempts=2,
        )
        self.db.add(job)
        await self.db.flush()

    async def get_case(self, case_id: str, user_id: UUID) -> CaseResponse:
        """Get case details by case ID."""
        case = await self._get_case_by_case_id(case_id, user_id)
        return self._case_to_response(case)

    async def list_cases(self, user_id: UUID) -> List[CaseResponse]:
        """List all cases for a user."""
        try:
            query = select(Case).where(Case.user_id == user_id).order_by(Case.created_at.desc())
            result = await self.db.execute(query)
            cases = result.scalars().all()

            return [self._case_to_response(case) for case in cases]

        except Exception as e:
            logger.error(f"Failed to list cases for user {user_id}: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to list cases"
            )

    async def update_case(
        self,
        case_id: str,
        user_id: UUID,
        update_data: CaseUpdate
    ) -> CaseResponse:
        """Update case with manual overrides."""
        try:
            case = await self._get_case_by_case_id(case_id, user_id)

            # Update fields
            update_dict = update_data.dict(exclude_unset=True)
            for field, value in update_dict.items():
                if hasattr(case, field):
                    # Handle enum values
                    if hasattr(value, 'value'):
                        setattr(case, field, value.value)
                    else:
                        setattr(case, field, value)

            await self.db.commit()
            await self.db.refresh(case)

            # Update completeness score if program type is set
            if case.program_type:
                await self._update_case_completeness(case_id, user_id)

            logger.info(f"Updated case: {case_id}")
            return self._case_to_response(case)

        except HTTPException:
            raise
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Failed to update case {case_id}: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to update case"
            )

    async def delete_case(self, case_id: str, user_id: UUID) -> None:
        """
        Permanently delete a case and all dependent records.

        Also attempts cleanup of stored uploaded files.
        """
        try:
            case = await self._get_case_by_case_id(case_id, user_id)
            storage_keys = [
                doc.storage_key for doc in case.documents
                if doc.storage_key
            ]

            # Prevent FK restriction from leads table where case link is optional.
            try:
                await self.db.execute(
                    text("UPDATE leads SET case_id = NULL WHERE case_id = :case_uuid"),
                    {"case_uuid": case.id},
                )
            except Exception as lead_fk_error:
                logger.warning(
                    "Could not clear lead linkage for case %s before delete: %s",
                    case_id,
                    lead_fk_error,
                )

            await self.db.delete(case)
            await self.db.commit()

            # File cleanup is best-effort and should not rollback case deletion.
            for storage_key in storage_keys:
                try:
                    await self.storage.delete_file(storage_key)
                except Exception as cleanup_error:
                    logger.warning(
                        "Storage cleanup failed for case %s file %s: %s",
                        case_id,
                        storage_key,
                        cleanup_error,
                    )

            logger.info(f"Deleted case: {case_id}")

        except HTTPException:
            raise
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Failed to delete case {case_id}: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to delete case"
            )

    # Helper methods

    async def _get_case_by_case_id(self, case_id: str, user_id: UUID) -> Case:
        """Get case by case_id and verify ownership."""
        query = select(Case).where(
            Case.case_id == case_id,
            Case.user_id == user_id
        ).options(selectinload(Case.documents))

        result = await self.db.execute(query)
        case = result.scalar_one_or_none()

        if not case:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Case {case_id} not found"
            )

        return case

    async def _find_duplicate_document(
        self,
        case_id: UUID,
        file_hash: str
    ) -> Optional[Document]:
        """Check if a document with the same hash already exists in the case."""
        query = select(Document).where(
            Document.case_id == case_id,
            Document.file_hash == file_hash
        )
        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    async def _get_file_size(self, file: UploadFile) -> int:
        """Get file size without consuming the stream."""
        # Read file content to get size, then reset
        content = await file.read()
        await file.seek(0)
        return len(content)

    def _case_to_response(self, case: Case) -> CaseResponse:
        """Convert Case model to CaseResponse schema."""
        return CaseResponse(
            id=case.id,
            case_id=case.case_id,
            status=CaseStatus(case.status),
            program_type=case.program_type,
            borrower_name=case.borrower_name,
            entity_type=case.entity_type,
            completeness_score=case.completeness_score,
            cibil_score_manual=case.cibil_score_manual,
            business_vintage_years=case.business_vintage_years,
            monthly_turnover_manual=case.monthly_turnover_manual,
            industry_type=case.industry_type,
            pincode=case.pincode,
            loan_amount_requested=case.loan_amount_requested,
            gstin=case.gstin,
            created_at=case.created_at,
            updated_at=case.updated_at
        )

    def _document_to_response(self, document: Document) -> DocumentResponse:
        """Convert Document model to DocumentResponse schema."""
        from app.core.enums import DocumentType

        doc_type = None
        if document.doc_type:
            try:
                doc_type = DocumentType(document.doc_type)
            except ValueError:
                doc_type = None

        return DocumentResponse(
            id=document.id,
            original_filename=document.original_filename,
            doc_type=doc_type,
            classification_confidence=document.classification_confidence or 0.0,
            status=DocumentStatus(document.status),
            page_count=document.page_count,
            created_at=document.created_at
        )

    async def _update_case_completeness(self, case_id: str, user_id: UUID) -> None:
        """Update case completeness score using ChecklistEngine."""
        try:
            from app.services.stages.stage1_checklist import ChecklistEngine
            checklist_engine = ChecklistEngine(self.db)
            await checklist_engine.update_completeness(case_id, user_id)
        except Exception as e:
            # Log error but don't fail the main operation
            logger.error(f"Failed to update completeness for case {case_id}: {e}")

    async def _extract_and_fetch_gst_data(self, document: Document, ocr_text: str) -> None:
        """
        Extract GSTIN from OCR text and fetch company details from GST API.

        Args:
            document: Document record
            ocr_text: OCR text from document
        """
        try:
            # Extract GSTIN from text
            gst_service = get_gst_api_service()
            gstin = GSTAPIService.extract_gstin_from_text(ocr_text)

            if not gstin:
                logger.info(f"No GSTIN found in document {document.id}")
                return

            logger.info(f"Found GSTIN {gstin} in document {document.id}")
            await self._fetch_and_apply_gst_data(document, gstin)

        except Exception as e:
            logger.error(f"Failed to extract/fetch GST data for document {document.id}: {e}", exc_info=True)
            # Don't fail the document processing if GST fetch fails

    async def _fetch_and_apply_gst_data(self, document: Document, gstin: str) -> None:
        """Fetch GST details and apply data to case."""
        try:
            gst_service = get_gst_api_service()

            # Get the case
            case = await self.db.get(Case, document.case_id)
            if not case:
                logger.error(f"Case not found for document {document.id}")
                return

            # Check if we already have GST data for this case
            if case.gst_data and case.gstin == gstin:
                logger.info(f"GST data already fetched for case {case.case_id}")
                return

            # Fetch GST data from API
            logger.info(f"Fetching GST data for GSTIN {gstin}")
            gst_data = await gst_service.fetch_company_details(gstin)

            if not gst_data:
                logger.warning(f"Failed to fetch GST data for GSTIN {gstin}")
                # Still save the GSTIN even if API call failed
                case.gstin = gstin
                await self.db.flush()
                return

            # Update case with GST data
            case.gstin = gstin
            case.gst_data = gst_data
            case.gst_fetched_at = dt.utcnow()

            # Auto-populate fields from GST data (GST data overrides manual entry per user preference)
            if gst_data.get("borrower_name"):
                case.borrower_name = gst_data["borrower_name"]

            if gst_data.get("entity_type"):
                case.entity_type = gst_data["entity_type"]

            if gst_data.get("business_vintage_years") is not None:
                case.business_vintage_years = gst_data["business_vintage_years"]

            if gst_data.get("pincode"):
                case.pincode = gst_data["pincode"]

            if gst_data.get("industry_type") and not case.industry_type:
                case.industry_type = gst_data["industry_type"]

            await self.db.flush()

            logger.info(
                f"Successfully saved GST data for case {case.case_id}: "
                f"borrower={gst_data.get('borrower_name')}, "
                f"entity={gst_data.get('entity_type')}, "
                f"vintage={gst_data.get('business_vintage_years')} years"
            )

        except Exception as e:
            logger.error(f"Failed to fetch/apply GST data for document {document.id}: {e}", exc_info=True)
            # Don't fail the document processing if GST fetch fails

    def _extract_gstin_from_filename(self, filename: Optional[str]) -> Optional[str]:
        if not filename:
            return None
        match = GSTIN_FILENAME_REGEX.search(filename.upper())
        return match.group(0) if match else None
