from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from uuid import UUID

from app.schemas.shared import DocumentResponse
from app.schemas.classifier import ClassificationResultSchema, ReclassifyRequest
from app.models.case import Document
from app.db.database import get_db
from app.services.stages.stage1_classifier import classify_document
from app.core.enums import DocumentStatus

router = APIRouter(prefix="/documents", tags=["documents"])


@router.get("/{doc_id}", response_model=DocumentResponse)
async def get_document(doc_id: str):
    """Get a document by ID."""
    return {"status": "TODO", "message": "Not implemented yet"}


@router.get("/{doc_id}/ocr-text")
async def get_ocr_text(
    doc_id: str,
    db: AsyncSession = Depends(get_db)
) -> dict:
    """
    Get OCR extracted text from a document.

    Returns:
        dict with text, confidence, page_count, method, and status
    """
    try:
        # Parse UUID
        try:
            document_uuid = UUID(doc_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid document ID format")

        # Fetch document
        stmt = select(Document).where(Document.id == document_uuid)
        result = await db.execute(stmt)
        document = result.scalar_one_or_none()

        if not document:
            raise HTTPException(status_code=404, detail="Document not found")

        # Check if OCR has been performed
        if document.status == "uploaded":
            return {
                "status": "pending",
                "message": "OCR has not been performed yet on this document",
                "text": None,
                "confidence": None,
                "page_count": None
            }

        if document.status == "failed":
            return {
                "status": "failed",
                "message": "OCR processing failed for this document",
                "text": None,
                "confidence": None,
                "page_count": None
            }

        # Return OCR results
        return {
            "status": "completed",
            "text": document.ocr_text or "",
            "confidence": document.ocr_confidence,
            "page_count": document.page_count,
            "document_status": document.status
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error retrieving OCR text: {str(e)}")


@router.post("/{doc_id}/classify", response_model=ClassificationResultSchema)
async def classify_document_endpoint(
    doc_id: str,
    db: AsyncSession = Depends(get_db)
):
    """
    Classify a document based on its OCR text.
    Updates the document's doc_type and classification_confidence in the database.
    """
    try:
        # Parse UUID
        try:
            document_uuid = UUID(doc_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid document ID format")

        # Fetch document
        stmt = select(Document).where(Document.id == document_uuid)
        result = await db.execute(stmt)
        document = result.scalar_one_or_none()

        if not document:
            raise HTTPException(status_code=404, detail="Document not found")

        # Check if OCR text is available
        if not document.ocr_text or len(document.ocr_text.strip()) < 10:
            raise HTTPException(
                status_code=400,
                detail="Document does not have sufficient OCR text for classification"
            )

        # Classify the document (IMPROVED: pass filename for better accuracy)
        classification_result = classify_document(document.ocr_text, filename=document.original_filename)

        # Update document in database
        document.doc_type = classification_result.doc_type.value
        document.classification_confidence = classification_result.confidence
        document.status = DocumentStatus.CLASSIFIED.value

        await db.commit()
        await db.refresh(document)

        return ClassificationResultSchema(
            doc_type=classification_result.doc_type,
            confidence=classification_result.confidence,
            method=classification_result.method,
            scores=classification_result.scores
        )

    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"Error classifying document: {str(e)}")


@router.post("/{doc_id}/reclassify")
async def reclassify_document_endpoint(
    doc_id: str,
    reclassify_request: ReclassifyRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Manually reclassify a document (override automatic classification).
    Use this endpoint when the automatic classification is incorrect.
    """
    try:
        # Parse UUID
        try:
            document_uuid = UUID(doc_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid document ID format")

        # Fetch document
        stmt = select(Document).where(Document.id == document_uuid)
        result = await db.execute(stmt)
        document = result.scalar_one_or_none()

        if not document:
            raise HTTPException(status_code=404, detail="Document not found")

        # Update document classification
        document.doc_type = reclassify_request.doc_type.value
        document.classification_confidence = reclassify_request.confidence
        document.status = DocumentStatus.CLASSIFIED.value

        await db.commit()
        await db.refresh(document)

        return {
            "status": "success",
            "message": "Document reclassified successfully",
            "doc_id": str(document.id),
            "doc_type": document.doc_type,
            "classification_confidence": document.classification_confidence
        }

    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"Error reclassifying document: {str(e)}")
