"""Extraction API endpoints - Stage 2 field extraction and feature assembly."""
import logging
import time
import asyncio
from pathlib import Path
from typing import List
from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.models.case import Case, Document, DocumentProcessingJob
from app.schemas.shared import ExtractedFieldItem, BorrowerFeatureVector
from app.core.enums import DocumentType, CaseStatus
from app.services.stages.stage2_extraction import get_extractor
from app.services.stages.stage2_features import get_assembler
from app.services.stages.stage2_bank_analyzer import get_analyzer
from app.services.file_storage import get_storage_backend
from app.core.deps import CurrentUser
from app.core.config import settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/extraction", tags=["extraction"])

MAX_BANK_STATEMENTS_PER_RUN = max(0, int(settings.EXTRACTION_MAX_BANK_STATEMENTS_PER_RUN))
BANK_ANALYSIS_TIMEOUT_SECONDS = max(10.0, float(settings.EXTRACTION_BANK_ANALYSIS_TIMEOUT_SECONDS))
BANK_FILENAME_HINTS = (
    "bank",
    "statement",
    "stmt",
    "account",
    "passbook",
    "transaction",
)
MAX_BANK_STATEMENT_FILE_BYTES = 8 * 1024 * 1024  # 8 MB safety guard for extraction-time parser


def _as_float(value):
    if value is None or value == "":
        return None


def _is_likely_bank_statement_document(document: Document) -> bool:
    """Filter false-positive bank statement classifications to avoid heavy parser crashes."""
    filename = (document.original_filename or "").lower()
    if any(hint in filename for hint in BANK_FILENAME_HINTS):
        return True

    # Keep tiny files with high confidence even if filename is generic.
    confidence = float(document.classification_confidence or 0.0)
    file_size = int(document.file_size_bytes or 0)
    if confidence >= 0.9 and 0 < file_size <= 2 * 1024 * 1024:
        return True

    return False
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _scoped_case_query(case_id: str, current_user):
    query = select(Case).where(Case.case_id == case_id)
    org_id = getattr(current_user, "organization_id", None)
    if current_user.role != "super_admin":
        if org_id:
            query = query.where(Case.organization_id == org_id)
        else:
            query = query.where(Case.user_id == current_user.id)
    return query


@router.post("/case/{case_id}/extract")
async def trigger_extraction(
    case_id: str,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
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
    started_at = time.perf_counter()
    document_extraction_ms = 0.0
    bank_analysis_ms = 0.0
    feature_assembly_ms = 0.0

    try:
        # Get the case
        query = _scoped_case_query(case_id, current_user)
        result = await db.execute(query)
        case = result.scalar_one_or_none()

        if not case:
            raise HTTPException(status_code=404, detail=f"Case {case_id} not found")

        pending_jobs_query = select(DocumentProcessingJob).where(
            DocumentProcessingJob.case_id == case.id,
            DocumentProcessingJob.status.in_(["queued", "processing"]),
        )
        pending_jobs_result = await db.execute(pending_jobs_query)
        pending_jobs = pending_jobs_result.scalars().all()
        if pending_jobs:
            raise HTTPException(
                status_code=409,
                detail=(
                    f"Document processing is still running ({len(pending_jobs)} file(s) pending). "
                    "Please retry extraction after document jobs complete."
                ),
            )

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
        doc_extract_started = time.perf_counter()

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
                    if _is_likely_bank_statement_document(doc):
                        bank_statement_docs.append(doc)
                    else:
                        extraction_summary.append({
                            "document_id": str(doc.id),
                            "doc_type": doc.doc_type,
                            "fields_extracted": 0,
                            "note": "Skipped bank analysis for non-statement-like document",
                        })
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

        document_extraction_ms = round((time.perf_counter() - doc_extract_started) * 1000, 2)

        # Analyze bank statements if present
        if bank_statement_docs:
            bank_started = time.perf_counter()
            try:
                bank_statement_docs = sorted(
                    bank_statement_docs,
                    key=lambda item: (
                        int(item.file_size_bytes or 0),
                        item.created_at or 0,
                    ),
                )

                # Get file paths for bank statements
                bank_pdf_paths = []
                for doc in bank_statement_docs:
                    if doc.storage_key:
                        file_path = storage.get_file_path(doc.storage_key)
                        if (
                            file_path
                            and file_path.exists()
                            and Path(file_path).suffix.lower() == ".pdf"
                            and int(doc.file_size_bytes or 0) <= MAX_BANK_STATEMENT_FILE_BYTES
                        ):
                            bank_pdf_paths.append(str(file_path))

                max_docs = MAX_BANK_STATEMENTS_PER_RUN or len(bank_pdf_paths)
                analyzed_pdf_paths = bank_pdf_paths[:max_docs]

                if bank_pdf_paths:
                    logger.info(
                        "Analyzing %s/%s bank statement(s) for case %s with timeout=%ss",
                        len(analyzed_pdf_paths),
                        len(bank_pdf_paths),
                        case_id,
                        BANK_ANALYSIS_TIMEOUT_SECONDS,
                    )

                    # Run bank analysis
                    bank_result = await asyncio.wait_for(
                        analyzer.analyze(analyzed_pdf_paths),
                        timeout=BANK_ANALYSIS_TIMEOUT_SECONDS
                    )

                    # Convert bank analysis results to extracted fields.
                    # Prefer explicit analyzer outputs and fallback to Credilo summary
                    # so profile metrics are available even when raw transaction shapes vary.
                    bank_fields = []
                    credilo_summary = bank_result.credilo_summary or {}
                    statement_months = max(int(bank_result.statement_period_months or 0), 1)

                    avg_monthly_balance = (
                        bank_result.avg_monthly_balance
                        if bank_result.avg_monthly_balance is not None
                        else _as_float(credilo_summary.get("custom_average_balance"))
                        or _as_float(credilo_summary.get("average_balance"))
                    )

                    monthly_credit_avg = bank_result.monthly_credit_avg
                    if monthly_credit_avg is None:
                        total_credit_amount = _as_float(credilo_summary.get("credit_transactions_amount"))
                        if total_credit_amount and statement_months > 0:
                            monthly_credit_avg = round(total_credit_amount / statement_months, 2)

                    emi_outflow_monthly = bank_result.emi_outflow_monthly
                    if emi_outflow_monthly is None:
                        total_emi_amount = _as_float(credilo_summary.get("total_emi_amount"))
                        if total_emi_amount and statement_months > 0:
                            emi_outflow_monthly = round(total_emi_amount / statement_months, 2)

                    bounce_count_12m = bank_result.bounce_count_12m
                    if not bounce_count_12m:
                        bounce_count_12m = int(_as_float(credilo_summary.get("no_of_emi_bounce")) or 0)

                    if avg_monthly_balance is not None:
                        bank_fields.append(ExtractedFieldItem(
                            field_name="avg_monthly_balance",
                            field_value=str(avg_monthly_balance),
                            confidence=bank_result.confidence,
                            source="bank_analysis"
                        ))

                    if monthly_credit_avg is not None:
                        bank_fields.append(ExtractedFieldItem(
                            field_name="monthly_credit_avg",
                            field_value=str(monthly_credit_avg),
                            confidence=bank_result.confidence,
                            source="bank_analysis"
                        ))
                        bank_fields.append(ExtractedFieldItem(
                            field_name="monthly_turnover",
                            field_value=str(monthly_credit_avg),
                            confidence=bank_result.confidence,
                            source="bank_analysis"
                        ))
                        annual_turnover_lakhs = round((monthly_credit_avg * 12) / 100000, 2)
                        bank_fields.append(ExtractedFieldItem(
                            field_name="annual_turnover",
                            field_value=str(annual_turnover_lakhs),
                            confidence=bank_result.confidence,
                            source="bank_analysis"
                        ))

                    if emi_outflow_monthly is not None:
                        bank_fields.append(ExtractedFieldItem(
                            field_name="emi_outflow_monthly",
                            field_value=str(emi_outflow_monthly),
                            confidence=bank_result.confidence,
                            source="bank_analysis"
                        ))

                    if bounce_count_12m is not None:
                        bank_fields.append(ExtractedFieldItem(
                            field_name="bounce_count_12m",
                            field_value=str(bounce_count_12m),
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

                    analyzer_detail_fields = {
                        "bank_detected": bank_result.bank_detected,
                        "transaction_count": bank_result.transaction_count,
                        "statement_period_months": bank_result.statement_period_months,
                        "monthly_debit_avg": bank_result.monthly_debit_avg,
                        "peak_balance": bank_result.peak_balance,
                        "min_balance": bank_result.min_balance,
                        "total_credits_12m": bank_result.total_credits_12m,
                        "total_debits_12m": bank_result.total_debits_12m,
                    }
                    for field_name, value in analyzer_detail_fields.items():
                        if value is None:
                            continue
                        bank_fields.append(
                            ExtractedFieldItem(
                                field_name=field_name,
                                field_value=str(value),
                                confidence=bank_result.confidence,
                                source="bank_analysis",
                            )
                        )

                    credilo_summary_fields = [
                        ("credilo_total_input_files", "total_input_files"),
                        ("credilo_total_transactions", "total_transactions"),
                        ("credilo_statement_count", "statement_count"),
                        ("credilo_period_start", "period_start"),
                        ("credilo_period_end", "period_end"),
                        ("credilo_average_balance", "average_balance"),
                        ("credilo_custom_average_balance", "custom_average_balance"),
                        (
                            "credilo_custom_average_balance_last_three_month",
                            "custom_average_balance_last_three_month",
                        ),
                        ("credilo_credit_transactions_amount", "credit_transactions_amount"),
                        ("credilo_debit_transactions_amount", "debit_transactions_amount"),
                        ("credilo_net_credit_transactions_amount", "net_credit_transactions_amount"),
                        ("credilo_net_debit_transactions_amount", "net_debit_transactions_amount"),
                        ("credilo_no_of_emi", "no_of_emi"),
                        ("credilo_total_emi_amount", "total_emi_amount"),
                        ("credilo_no_of_emi_bounce", "no_of_emi_bounce"),
                        ("credilo_total_emi_bounce_amount", "total_emi_bounce_amount"),
                        ("credilo_no_of_loan_disbursal", "no_of_loan_disbursal"),
                        ("credilo_loan_disbursal_amount", "loan_disbursal_amount"),
                    ]

                    for field_name, summary_key in credilo_summary_fields:
                        value = credilo_summary.get(summary_key)
                        if value is None:
                            continue
                        bank_fields.append(
                            ExtractedFieldItem(
                                field_name=field_name,
                                field_value=str(value),
                                confidence=bank_result.confidence,
                                source="bank_analysis",
                            )
                        )

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
                        "documents_analyzed": len(analyzed_pdf_paths),
                        "documents_detected": len(bank_pdf_paths),
                        "fields_extracted": len(bank_fields),
                        "bank_detected": bank_result.bank_detected,
                        "transaction_count": bank_result.transaction_count,
                        "statement_period_months": bank_result.statement_period_months,
                        "confidence": bank_result.confidence,
                        "source": bank_result.source,
                        "credilo_summary": bank_result.credilo_summary or None,
                        "note": (
                            f"Used latest {len(analyzed_pdf_paths)} statements for faster analysis"
                            if len(bank_pdf_paths) > len(analyzed_pdf_paths)
                            else None
                        ),
                    })

                    logger.info(
                        f"Bank analysis completed for case {case_id}: "
                        f"{len(bank_fields)} fields extracted with "
                        f"{bank_result.confidence:.2f} confidence"
                    )

            except asyncio.TimeoutError:
                logger.warning(
                    "Bank analysis timed out for case %s after %ss",
                    case_id,
                    BANK_ANALYSIS_TIMEOUT_SECONDS,
                )
                extraction_summary.append({
                    "document_type": "BANK_STATEMENT",
                    "error": f"Bank analysis timed out after {BANK_ANALYSIS_TIMEOUT_SECONDS:.0f}s",
                    "documents_detected": len(bank_statement_docs),
                })
            except Exception as e:
                logger.error(
                    f"Error analyzing bank statements for case {case_id}: {str(e)}",
                    exc_info=True
                )
                extraction_summary.append({
                    "document_type": "BANK_STATEMENT",
                    "error": str(e)
                })
            finally:
                bank_analysis_ms = round((time.perf_counter() - bank_started) * 1000, 2)

        # Assemble feature vector
        feature_started = time.perf_counter()
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

            feature_assembly_ms = round((time.perf_counter() - feature_started) * 1000, 2)
            total_ms = round((time.perf_counter() - started_at) * 1000, 2)

            return {
                "status": "success",
                "case_id": case_id,
                "total_fields_extracted": len(all_extracted_fields),
                "feature_completeness": feature_vector.feature_completeness,
                "documents_processed": len(documents),
                "extraction_summary": extraction_summary,
                "timing_ms": {
                    "document_extraction": document_extraction_ms,
                    "bank_analysis": bank_analysis_ms,
                    "feature_assembly": feature_assembly_ms,
                    "total": total_ms,
                },
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
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
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
        case_result = await db.execute(_scoped_case_query(case_id, current_user))
        case = case_result.scalar_one_or_none()
        if not case:
            raise HTTPException(status_code=404, detail=f"Case {case_id} not found")

        assembler = get_assembler()
        fields = await assembler.get_extracted_fields(db=db, case_id=case_id)
        return fields

    except HTTPException:
        raise
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
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
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
        case_result = await db.execute(_scoped_case_query(case_id, current_user))
        case = case_result.scalar_one_or_none()
        if not case:
            raise HTTPException(status_code=404, detail=f"Case {case_id} not found")

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
