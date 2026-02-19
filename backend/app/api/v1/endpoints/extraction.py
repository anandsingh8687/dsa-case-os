"""Extraction API endpoints - Stage 2 field extraction and feature assembly."""
import logging
from typing import List
from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.models.case import Case, Document
from app.schemas.shared import ExtractedFieldItem, BorrowerFeatureVector
from app.core.enums import DocumentType, CaseStatus
from app.services.stages.stage2_extraction import get_extractor
from app.services.stages.stage2_features import get_assembler
from app.services.stages.stage2_bank_analyzer import get_analyzer
from app.services.file_storage import get_storage_backend

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/extraction", tags=["extraction"])


@router.post("/case/{case_id}/extract")
async def trigger_extraction(
    case_id: str,
    db: AsyncSession = Depends(get_db)
):
    """
    Trigger extraction pipeline for a case.

    This will:
    1. Extract fields from all classified documents
    2. Assemble them into a BorrowerFeatureVector
    3. Save results to database
    4. Update case status

    Args:
        case_id: Case ID string
        db: Database session

    Returns:
        Summary of extraction results
    """
    try:
        # Get the case
        query = select(Case).where(Case.case_id == case_id)
        result = await db.execute(query)
        case = result.scalar_one_or_none()

        if not case:
            raise HTTPException(status_code=404, detail=f"Case {case_id} not found")

        # Load all documents; bank analysis should run even when OCR text is unavailable.
        query = select(Document).where(Document.case_id == case.id)
        result = await db.execute(query)
        documents = result.scalars().all()

        if not documents:
            raise HTTPException(
                status_code=400,
                detail="No documents found for this case"
            )

        # Extract fields from each document
        extractor = get_extractor()
        assembler = get_assembler()
        analyzer = get_analyzer()
        storage = get_storage_backend()
        all_extracted_fields = []
        extraction_summary = []
        bank_statement_docs = []

        for doc in documents:
            try:
                if not doc.doc_type:
                    extraction_summary.append({
                        "document_id": str(doc.id),
                        "doc_type": "unknown",
                        "fields_extracted": 0,
                        "note": "Document type unavailable",
                    })
                    continue

                doc_type = DocumentType(doc.doc_type)

                # Collect bank statement documents for separate analysis
                if doc_type == DocumentType.BANK_STATEMENT:
                    bank_statement_docs.append(doc)
                    continue

                if not doc.ocr_text:
                    extraction_summary.append({
                        "document_id": str(doc.id),
                        "doc_type": doc.doc_type,
                        "fields_extracted": 0,
                        "note": "No OCR text available for field extraction",
                    })
                    continue

                fields = await extractor.extract_fields(doc.ocr_text, doc_type)

                # Save extracted fields
                if fields:
                    await assembler.save_extracted_fields(
                        db=db,
                        case_id=case_id,
                        document_id=str(doc.id),
                        fields=fields
                    )
                    all_extracted_fields.extend(fields)

                extraction_summary.append({
                    "document_id": str(doc.id),
                    "doc_type": doc.doc_type,
                    "fields_extracted": len(fields)
                })

                logger.info(
                    f"Extracted {len(fields)} fields from {doc.doc_type} "
                    f"for case {case_id}"
                )

            except Exception as e:
                logger.error(
                    f"Error extracting from document {doc.id}: {str(e)}",
                    exc_info=True
                )
                extraction_summary.append({
                    "document_id": str(doc.id),
                    "doc_type": doc.doc_type,
                    "error": str(e)
                })

        # Analyze bank statements if present
        if bank_statement_docs:
            try:
                # Get file paths for bank statements
                bank_pdf_paths = []
                for doc in bank_statement_docs:
                    if doc.storage_key:
                        file_path = storage.get_file_path(doc.storage_key)
                        if file_path and file_path.exists():
                            bank_pdf_paths.append(str(file_path))

                if bank_pdf_paths:
                    logger.info(
                        f"Analyzing {len(bank_pdf_paths)} bank statement(s) "
                        f"for case {case_id}"
                    )

                    # Run bank analysis
                    bank_result = await analyzer.analyze(bank_pdf_paths)

                    # Convert bank analysis results to extracted fields
                    bank_fields = []

                    if bank_result.avg_monthly_balance is not None:
                        bank_fields.append(ExtractedFieldItem(
                            field_name="avg_monthly_balance",
                            field_value=str(bank_result.avg_monthly_balance),
                            confidence=bank_result.confidence,
                            source="bank_analysis"
                        ))

                    if bank_result.monthly_credit_avg is not None:
                        bank_fields.append(ExtractedFieldItem(
                            field_name="monthly_credit_avg",
                            field_value=str(bank_result.monthly_credit_avg),
                            confidence=bank_result.confidence,
                            source="bank_analysis"
                        ))
                        bank_fields.append(ExtractedFieldItem(
                            field_name="monthly_turnover",
                            field_value=str(bank_result.monthly_credit_avg),
                            confidence=bank_result.confidence,
                            source="bank_analysis"
                        ))
                        annual_turnover_lakhs = round((bank_result.monthly_credit_avg * 12) / 100000, 2)
                        bank_fields.append(ExtractedFieldItem(
                            field_name="annual_turnover",
                            field_value=str(annual_turnover_lakhs),
                            confidence=bank_result.confidence,
                            source="bank_analysis"
                        ))

                    if bank_result.emi_outflow_monthly is not None:
                        bank_fields.append(ExtractedFieldItem(
                            field_name="emi_outflow_monthly",
                            field_value=str(bank_result.emi_outflow_monthly),
                            confidence=bank_result.confidence,
                            source="bank_analysis"
                        ))

                    if bank_result.bounce_count_12m is not None:
                        bank_fields.append(ExtractedFieldItem(
                            field_name="bounce_count_12m",
                            field_value=str(bank_result.bounce_count_12m),
                            confidence=bank_result.confidence,
                            source="bank_analysis"
                        ))

                    if bank_result.cash_deposit_ratio is not None:
                        bank_fields.append(ExtractedFieldItem(
                            field_name="cash_deposit_ratio",
                            field_value=str(bank_result.cash_deposit_ratio),
                            confidence=bank_result.confidence,
                            source="bank_analysis"
                        ))

                    # Save bank analysis fields
                    if bank_fields:
                        await assembler.save_extracted_fields(
                            db=db,
                            case_id=case_id,
                            document_id=str(bank_statement_docs[0].id),
                            fields=bank_fields
                        )
                        all_extracted_fields.extend(bank_fields)

                    extraction_summary.append({
                        "document_type": "BANK_STATEMENT",
                        "documents_analyzed": len(bank_pdf_paths),
                        "fields_extracted": len(bank_fields),
                        "bank_detected": bank_result.bank_detected,
                        "transaction_count": bank_result.transaction_count,
                        "statement_period_months": bank_result.statement_period_months,
                        "confidence": bank_result.confidence
                    })

                    logger.info(
                        f"Bank analysis completed for case {case_id}: "
                        f"{len(bank_fields)} fields extracted with "
                        f"{bank_result.confidence:.2f} confidence"
                    )

            except Exception as e:
                logger.error(
                    f"Error analyzing bank statements for case {case_id}: {str(e)}",
                    exc_info=True
                )
                extraction_summary.append({
                    "document_type": "BANK_STATEMENT",
                    "error": str(e)
                })

        # Assemble feature vector
        try:
            feature_vector = await assembler.assemble_features(
                db=db,
                case_id=case_id,
                extracted_fields=all_extracted_fields
            )

            # Save feature vector
            await assembler.save_feature_vector(
                db=db,
                case_id=case_id,
                feature_vector=feature_vector
            )

            # Update case status
            case.status = CaseStatus.FEATURES_EXTRACTED.value
            case.completeness_score = feature_vector.feature_completeness
            await db.commit()

            logger.info(
                f"Assembled feature vector for case {case_id} "
                f"with {feature_vector.feature_completeness:.1f}% completeness"
            )

            return {
                "status": "success",
                "case_id": case_id,
                "total_fields_extracted": len(all_extracted_fields),
                "feature_completeness": feature_vector.feature_completeness,
                "documents_processed": len(documents),
                "extraction_summary": extraction_summary
            }

        except Exception as e:
            logger.error(
                f"Error assembling features for case {case_id}: {str(e)}",
                exc_info=True
            )
            raise HTTPException(
                status_code=500,
                detail=f"Error assembling features: {str(e)}"
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in extraction pipeline: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Extraction pipeline failed: {str(e)}"
        )


@router.get("/case/{case_id}/fields", response_model=List[ExtractedFieldItem])
async def get_extracted_fields(
    case_id: str,
    db: AsyncSession = Depends(get_db)
):
    """
    Get all extracted field items for a case.

    Args:
        case_id: Case ID string
        db: Database session

    Returns:
        List of extracted field items with confidence scores
    """
    try:
        assembler = get_assembler()
        fields = await assembler.get_extracted_fields(db=db, case_id=case_id)
        return fields

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Error fetching extracted fields: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Error fetching fields: {str(e)}"
        )


@router.get("/case/{case_id}/features", response_model=BorrowerFeatureVector)
async def get_feature_vector(
    case_id: str,
    db: AsyncSession = Depends(get_db)
):
    """
    Get the assembled borrower feature vector for a case.

    Args:
        case_id: Case ID string
        db: Database session

    Returns:
        BorrowerFeatureVector with all assembled features
    """
    try:
        assembler = get_assembler()
        feature_vector = await assembler.get_feature_vector(db=db, case_id=case_id)

        if not feature_vector:
            raise HTTPException(
                status_code=404,
                detail=f"No feature vector found for case {case_id}. "
                       "Run extraction first."
            )

        return feature_vector

    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Error fetching feature vector: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Error fetching features: {str(e)}"
        )
