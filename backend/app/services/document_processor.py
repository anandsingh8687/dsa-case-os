"""Document processing orchestration - coordinates OCR and DB updates."""
import logging
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.case import Document
from app.services.stages.stage1_ocr import ocr_service
from app.schemas.shared import OCRResult

logger = logging.getLogger(__name__)


class DocumentProcessor:
    """Orchestrates document processing workflows."""

    async def process_document_ocr(
        self,
        db: AsyncSession,
        document_id: UUID,
        file_path: str
    ) -> OCRResult:
        """
        Run OCR on a document and update the database.

        Args:
            db: Database session
            document_id: UUID of the document
            file_path: Absolute path to the file

        Returns:
            OCRResult with extracted text and metadata
        """
        try:
            # Fetch document from DB
            stmt = select(Document).where(Document.id == document_id)
            result = await db.execute(stmt)
            document = result.scalar_one_or_none()

            if not document:
                raise ValueError(f"Document {document_id} not found")

            # Run OCR
            logger.info(f"Starting OCR for document {document_id} ({document.original_filename})")
            ocr_result = await ocr_service.extract_text(
                file_path=file_path,
                mime_type=document.mime_type or ""
            )

            # Update document in DB
            document.ocr_text = ocr_result.text
            document.ocr_confidence = ocr_result.confidence
            document.page_count = ocr_result.page_count
            document.status = "ocr_complete"

            await db.commit()
            await db.refresh(document)

            logger.info(
                f"OCR completed for document {document_id} | "
                f"Method: {ocr_result.method} | Confidence: {ocr_result.confidence:.2f}"
            )

            return ocr_result

        except Exception as e:
            await db.rollback()
            logger.error(f"OCR processing failed for document {document_id}: {str(e)}", exc_info=True)

            # Mark document as failed
            try:
                stmt = select(Document).where(Document.id == document_id)
                result = await db.execute(stmt)
                document = result.scalar_one_or_none()
                if document:
                    document.status = "failed"
                    await db.commit()
            except:
                pass

            raise


document_processor = DocumentProcessor()
