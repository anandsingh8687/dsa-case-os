"""
Batch Upload API Endpoints

Handles ZIP file uploads and batch document processing.
"""

import logging
from typing import Optional
from pydantic import BaseModel

from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from fastapi.responses import JSONResponse

from app.services.zip_handler import zip_handler, bank_aggregator
from app.core.deps import CurrentUser

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/batch", tags=["batch"])


# ============================================================
# REQUEST/RESPONSE MODELS
# ============================================================

class ZIPUploadResponse(BaseModel):
    success: bool
    message: str
    case_id: str
    total_files: int
    processed: int
    failed: int
    document_ids: list
    errors: list


class BankStatementAggregateResponse(BaseModel):
    case_id: str
    total_months: int
    statement_count: int
    aggregate_metrics: dict
    trend_analysis: dict


# ============================================================
# ZIP UPLOAD ENDPOINT
# ============================================================

@router.post("/upload-zip/{case_id}", response_model=ZIPUploadResponse)
async def upload_zip_batch(
    case_id: str,
    file: UploadFile = File(...),
    current_user: CurrentUser = None
):
    """
    Upload a ZIP file containing multiple bank statements or documents.

    The ZIP will be extracted and all files will be processed as separate documents.
    Supports:
    - Multiple bank statements (aggregated analysis)
    - Mixed document types
    - Up to 50 files per ZIP
    - Max 100MB ZIP size

    Args:
        case_id: Case ID to attach documents to
        file: ZIP file upload
        current_user: Authenticated user

    Returns:
        {
            'success': bool,
            'message': str,
            'case_id': str,
            'total_files': int,
            'processed': int,
            'failed': int,
            'document_ids': List[str],
            'errors': List[str]
        }
    """
    logger.info(f"Received ZIP upload for case {case_id}: {file.filename}")

    try:
        # Validate file is ZIP
        if not file.filename.endswith('.zip'):
            raise HTTPException(status_code=400, detail="File must be a ZIP archive")

        # Read file content
        file_content = await file.read()

        # Validate ZIP
        is_valid, error_message = zip_handler.validate_zip(file_content, file.filename)
        if not is_valid:
            raise HTTPException(status_code=400, detail=error_message)

        # Extract ZIP
        extracted_files = await zip_handler.extract_zip(file_content, file.filename)

        if not extracted_files:
            raise HTTPException(status_code=400, detail="No valid files found in ZIP")

        logger.info(f"Extracted {len(extracted_files)} files from {file.filename}")

        # Process batch documents
        result = await zip_handler.process_batch_documents(
            extracted_files=extracted_files,
            case_id=case_id,
            user_id=str(current_user.id) if current_user else None
        )

        # Check if processing was successful
        if not result.get('success'):
            return ZIPUploadResponse(
                success=False,
                message=result.get('error', 'Failed to process documents'),
                case_id=case_id,
                total_files=result.get('total_files', 0),
                processed=result.get('processed', 0),
                failed=result.get('failed', 0),
                document_ids=result.get('document_ids', []),
                errors=result.get('errors', [])
            )

        # Success response
        message = f"Successfully processed {result['processed']} files"
        if result['failed'] > 0:
            message += f" ({result['failed']} failed)"

        return ZIPUploadResponse(
            success=True,
            message=message,
            case_id=case_id,
            total_files=result['total_files'],
            processed=result['processed'],
            failed=result['failed'],
            document_ids=result['document_ids'],
            errors=result['errors']
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error processing ZIP upload: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error processing ZIP: {str(e)}")


# ============================================================
# BANK STATEMENT AGGREGATION
# ============================================================

@router.get("/bank-statements-aggregate/{case_id}", response_model=BankStatementAggregateResponse)
async def get_bank_statement_aggregate(
    case_id: str,
    current_user: CurrentUser
):
    """
    Get aggregated analysis from all bank statements in a case.

    When multiple bank statements are uploaded (via ZIP or individually),
    this endpoint provides combined analysis:
    - Total months of data
    - Average monthly credit (across all statements)
    - Trends and patterns
    - Consistency metrics

    Args:
        case_id: Case ID
        current_user: Authenticated user

    Returns:
        {
            'case_id': str,
            'total_months': int,
            'statement_count': int,
            'aggregate_metrics': {
                'avg_monthly_credit': float,
                'avg_monthly_balance': float,
                'total_bounced_cheques': int,
                'banking_months': int
            },
            'trend_analysis': {
                'credit_trend': 'stable',
                'volatility': 'low',
                'consistent_inflows': true
            }
        }
    """
    logger.info(f"Getting bank statement aggregate for case {case_id}")

    try:
        result = await bank_aggregator.aggregate_bank_statements(case_id)

        if 'error' in result:
            raise HTTPException(
                status_code=404 if result['error'] == 'Case not found' else 400,
                detail=result['error']
            )

        return BankStatementAggregateResponse(**result)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting bank statement aggregate: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# BATCH UPLOAD STATUS
# ============================================================

@router.get("/upload-status/{case_id}")
async def get_batch_upload_status(
    case_id: str,
    current_user: CurrentUser
):
    """
    Get status of batch uploads for a case.

    Shows:
    - Total documents uploaded
    - Documents by type
    - Processing status
    - Any errors

    Args:
        case_id: Case ID
        current_user: Authenticated user

    Returns:
        Status information
    """
    from app.db.database import get_db_session

    try:
        async with get_db_session() as db:
            # Get case UUID
            case_query = "SELECT id FROM cases WHERE case_id = $1 AND user_id = $2"
            case_row = await db.fetchrow(case_query, case_id, current_user.id)

            if not case_row:
                raise HTTPException(status_code=404, detail="Case not found")

            case_uuid = case_row['id']

            # Get document counts
            stats_query = """
                SELECT
                    COUNT(*) as total,
                    COUNT(*) FILTER (WHERE status = 'processed') as processed,
                    COUNT(*) FILTER (WHERE status = 'failed') as failed,
                    COUNT(*) FILTER (WHERE doc_type = 'BANK_STATEMENT') as bank_statements,
                    COUNT(*) FILTER (WHERE doc_type = 'GST_CERTIFICATE') as gst_certs,
                    COUNT(*) FILTER (WHERE doc_type = 'GST_RETURNS') as gst_returns,
                    COUNT(*) FILTER (WHERE doc_type = 'PAN_CARD') as pan_cards,
                    COUNT(*) FILTER (WHERE doc_type = 'AADHAAR_CARD') as aadhaar_cards
                FROM documents
                WHERE case_id = $1
            """

            stats_row = await db.fetchrow(stats_query, case_uuid)

            return {
                "case_id": case_id,
                "total_documents": stats_row['total'],
                "processed": stats_row['processed'],
                "failed": stats_row['failed'],
                "by_type": {
                    "bank_statements": stats_row['bank_statements'],
                    "gst_certificates": stats_row['gst_certs'],
                    "gst_returns": stats_row['gst_returns'],
                    "pan_cards": stats_row['pan_cards'],
                    "aadhaar_cards": stats_row['aadhaar_cards']
                },
                "completion_percentage": (stats_row['processed'] / stats_row['total'] * 100) if stats_row['total'] > 0 else 0
            }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting batch upload status: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
