"""
Flexible Case Creation API

Supports two workflows:
1. Documents First: Upload documents → Extract data → Auto-fill form
2. Form First: Fill form → Upload documents (traditional)
"""

import logging
from typing import Optional, Dict, Any, List
from pydantic import BaseModel
from uuid import UUID

from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from fastapi.responses import JSONResponse

from app.db.database import get_db_session
from app.core.deps import CurrentUser
from app.services.stages.stage0_case_entry import CaseEntryService
from app.services.gst_api import GSTAPIService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/flexible-case", tags=["flexible-case"])


# ============================================================
# REQUEST/RESPONSE MODELS
# ============================================================

class CreateMinimalCaseRequest(BaseModel):
    """Create case with minimal information for documents-first workflow."""
    workflow_type: str  # 'documents_first' or 'form_first'
    borrower_name: Optional[str] = None


class CreateMinimalCaseResponse(BaseModel):
    success: bool
    case_id: str
    workflow_type: str
    message: str


class AutoFillSuggestionsResponse(BaseModel):
    """Suggestions for auto-filling form based on uploaded documents."""
    case_id: str
    suggestions: Dict[str, Any]
    confidence_scores: Dict[str, float]
    source_documents: List[str]
    ready_for_review: bool


# ============================================================
# FLEXIBLE CASE CREATION
# ============================================================

@router.post("/create", response_model=CreateMinimalCaseResponse)
async def create_flexible_case(
    request: CreateMinimalCaseRequest,
    current_user: CurrentUser
):
    """
    Create a case with minimal information.

    Supports two workflows:
    - documents_first: User will upload documents, then fill form
    - form_first: Traditional workflow (fill form, then documents)

    Args:
        request: Minimal case creation request
        current_user: Authenticated user

    Returns:
        Case ID and workflow type
    """
    logger.info(f"Creating flexible case with workflow: {request.workflow_type}")

    try:
        async with get_db_session() as db:
            # Generate case ID
            from datetime import datetime as dt
            today = dt.now().strftime("%Y%m%d")

            # Get count of cases created today
            count_query = """
                SELECT COUNT(*)
                FROM cases
                WHERE case_id LIKE $1
            """
            count = await db.fetchval(count_query, f"CASE-{today}-%")
            sequence = count + 1

            case_id = f"CASE-{today}-{sequence:04d}"

            # Create case with minimal data
            insert_query = """
                INSERT INTO cases (
                    case_id,
                    user_id,
                    status,
                    borrower_name,
                    created_at,
                    updated_at
                )
                VALUES ($1, $2, $3, $4, NOW(), NOW())
                RETURNING id
            """

            status = 'documents_pending' if request.workflow_type == 'documents_first' else 'created'

            await db.execute(
                insert_query,
                case_id,
                current_user.id,
                status,
                request.borrower_name or f"Case {case_id}"
            )

            logger.info(f"Created flexible case: {case_id} (workflow: {request.workflow_type})")

            return CreateMinimalCaseResponse(
                success=True,
                case_id=case_id,
                workflow_type=request.workflow_type,
                message=f"Case created successfully. {'Upload documents to begin.' if request.workflow_type == 'documents_first' else 'Fill in borrower details.'}"
            )

    except Exception as e:
        logger.error(f"Error creating flexible case: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# AUTO-FILL SUGGESTIONS
# ============================================================

@router.get("/auto-fill-suggestions/{case_id}", response_model=AutoFillSuggestionsResponse)
async def get_auto_fill_suggestions(
    case_id: str,
    current_user: CurrentUser
):
    """
    Get auto-fill suggestions based on uploaded documents and extracted data.

    This endpoint analyzes all uploaded documents for a case and suggests
    values for form fields based on extracted data (OCR, classification, etc.).

    Args:
        case_id: Case ID
        current_user: Authenticated user

    Returns:
        {
            'case_id': str,
            'suggestions': {
                'borrower_name': 'LAKSHMI TRADERS',
                'entity_type': 'proprietorship',
                'gstin': '29ABCDE1234F1Z5',
                'business_vintage_years': 2.5,
                'pincode': '411001',
                ...
            },
            'confidence_scores': {
                'borrower_name': 0.95,
                'entity_type': 0.85,
                ...
            },
            'source_documents': [
                'GST Certificate (confidence: 95%)',
                'Bank Statement (confidence: 90%)'
            ],
            'ready_for_review': true
        }
    """
    logger.info(f"Generating auto-fill suggestions for case {case_id}")

    try:
        async with get_db_session() as db:
            # Get case UUID
            case_query = "SELECT id FROM cases WHERE case_id = $1 AND user_id = $2"
            case_row = await db.fetchrow(case_query, case_id, current_user.id)

            if not case_row:
                raise HTTPException(status_code=404, detail="Case not found")

            case_uuid = case_row['id']

            # Get all extracted fields for this case
            extracted_query = """
                SELECT
                    ef.field_name,
                    ef.field_value,
                    ef.confidence,
                    ef.source,
                    d.doc_type,
                    d.original_filename
                FROM extracted_fields ef
                LEFT JOIN documents d ON ef.document_id = d.id
                WHERE ef.case_id = $1
                ORDER BY ef.confidence DESC
            """

            rows = await db.fetch(extracted_query, case_uuid)

            if not rows:
                return AutoFillSuggestionsResponse(
                    case_id=case_id,
                    suggestions={},
                    confidence_scores={},
                    source_documents=[],
                    ready_for_review=False
                )

            # Aggregate suggestions (take highest confidence for each field)
            suggestions = {}
            confidence_scores = {}
            source_docs_set = set()

            for row in rows:
                field_name = row['field_name']
                field_value = row['field_value']
                confidence = row['confidence']
                doc_type = row['doc_type']
                filename = row['original_filename']

                # Only include if we don't have this field yet, or if confidence is higher
                if field_name not in suggestions or confidence > confidence_scores.get(field_name, 0):
                    suggestions[field_name] = field_value
                    confidence_scores[field_name] = confidence

                # Track source documents
                if doc_type and filename:
                    source_docs_set.add(f"{doc_type}: {filename} ({confidence:.0%})")

            # Get GST data if GSTIN is available
            if 'gstin' in suggestions or 'GSTIN' in suggestions:
                gstin = suggestions.get('gstin') or suggestions.get('GSTIN')

                # Check if we already have GST data
                gst_query = "SELECT gst_data FROM cases WHERE id = $1"
                gst_row = await db.fetchrow(gst_query, case_uuid)

                if gst_row and gst_row['gst_data']:
                    gst_data = gst_row['gst_data']

                    # Add GST-derived fields to suggestions
                    if gst_data.get('borrower_name'):
                        suggestions['borrower_name'] = gst_data['borrower_name']
                        confidence_scores['borrower_name'] = 0.95

                    if gst_data.get('entity_type'):
                        suggestions['entity_type'] = gst_data['entity_type']
                        confidence_scores['entity_type'] = 0.95

                    if gst_data.get('business_vintage_years'):
                        suggestions['business_vintage_years'] = gst_data['business_vintage_years']
                        confidence_scores['business_vintage_years'] = 0.90

                    if gst_data.get('pincode'):
                        suggestions['pincode'] = gst_data['pincode']
                        confidence_scores['pincode'] = 0.90

                    source_docs_set.add("GST API (95%)")

            # Check if we have borrower features (from bank statement analysis)
            features_query = """
                SELECT
                    cibil_score,
                    business_vintage_years,
                    monthly_turnover,
                    avg_monthly_balance,
                    bounced_cheques_count
                FROM borrower_features
                WHERE case_id = $1
            """

            features_row = await db.fetchrow(features_query, case_uuid)

            if features_row:
                if features_row['cibil_score']:
                    suggestions['cibil_score'] = features_row['cibil_score']
                    confidence_scores['cibil_score'] = 0.85

                if features_row['monthly_turnover']:
                    suggestions['monthly_turnover'] = features_row['monthly_turnover']
                    confidence_scores['monthly_turnover'] = 0.90

                if features_row['business_vintage_years']:
                    suggestions['business_vintage_years'] = features_row['business_vintage_years']
                    confidence_scores['business_vintage_years'] = 0.85

                source_docs_set.add("Bank Statement Analysis (90%)")

            # Determine if ready for review (at least 3 fields with confidence > 70%)
            high_confidence_count = sum(1 for conf in confidence_scores.values() if conf > 0.7)
            ready_for_review = high_confidence_count >= 3

            return AutoFillSuggestionsResponse(
                case_id=case_id,
                suggestions=suggestions,
                confidence_scores=confidence_scores,
                source_documents=sorted(list(source_docs_set)),
                ready_for_review=ready_for_review
            )

    except Exception as e:
        logger.error(f"Error generating auto-fill suggestions: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# APPLY AUTO-FILL SUGGESTIONS
# ============================================================

@router.post("/apply-suggestions/{case_id}")
async def apply_auto_fill_suggestions(
    case_id: str,
    suggestions: Dict[str, Any],
    current_user: CurrentUser
):
    """
    Apply auto-fill suggestions to a case.

    User can review and modify suggestions before applying them.
    This endpoint updates the case with the provided values.

    Args:
        case_id: Case ID
        suggestions: Dictionary of field names and values to apply
        current_user: Authenticated user

    Returns:
        Success message
    """
    logger.info(f"Applying auto-fill suggestions to case {case_id}")

    try:
        async with get_db_session() as db:
            # Get case UUID
            case_query = "SELECT id FROM cases WHERE case_id = $1 AND user_id = $2"
            case_row = await db.fetchrow(case_query, case_id, current_user.id)

            if not case_row:
                raise HTTPException(status_code=404, detail="Case not found")

            case_uuid = case_row['id']

            # Build dynamic UPDATE query
            update_fields = []
            update_values = []
            param_index = 1

            # Map of allowed fields
            allowed_fields = {
                'borrower_name', 'entity_type', 'business_vintage_years',
                'industry_type', 'pincode', 'loan_amount_requested', 'gstin',
                'cibil_score_manual', 'monthly_turnover_manual'
            }

            for field, value in suggestions.items():
                if field in allowed_fields and value is not None:
                    update_fields.append(f"{field} = ${param_index}")
                    update_values.append(value)
                    param_index += 1

            if not update_fields:
                return {"success": False, "message": "No valid fields to update"}

            # Add updated_at
            update_fields.append(f"updated_at = NOW()")
            update_fields.append(f"status = 'form_completed'")

            # Execute update
            update_query = f"""
                UPDATE cases
                SET {', '.join(update_fields)}
                WHERE id = ${param_index}
            """
            update_values.append(case_uuid)

            await db.execute(update_query, *update_values)

            logger.info(f"Applied auto-fill suggestions to case {case_id}")

            return {
                "success": True,
                "message": f"Applied {len([f for f in update_fields if '$' in f])} suggestions to case {case_id}",
                "case_id": case_id,
                "updated_fields": [field.split(' =')[0] for field in update_fields if '$' in field]
            }

    except Exception as e:
        logger.error(f"Error applying auto-fill suggestions: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# WORKFLOW STATUS
# ============================================================

@router.get("/workflow-status/{case_id}")
async def get_workflow_status(
    case_id: str,
    current_user: CurrentUser
):
    """
    Get the current workflow status of a case.

    Returns information about what step the user is on and what they need to do next.

    Args:
        case_id: Case ID
        current_user: Authenticated user

    Returns:
        {
            'case_id': str,
            'status': str,
            'workflow_type': str,
            'documents_uploaded': int,
            'form_completed': bool,
            'next_step': str,
            'completion_percentage': int
        }
    """
    try:
        async with get_db_session() as db:
            # Get case info
            case_query = """
                SELECT
                    c.id,
                    c.status,
                    c.borrower_name,
                    c.entity_type,
                    c.pincode,
                    COUNT(d.id) as doc_count
                FROM cases c
                LEFT JOIN documents d ON c.id = d.case_id
                WHERE c.case_id = $1 AND c.user_id = $2
                GROUP BY c.id, c.status, c.borrower_name, c.entity_type, c.pincode
            """

            row = await db.fetchrow(case_query, case_id, current_user.id)

            if not row:
                raise HTTPException(status_code=404, detail="Case not found")

            status = row['status']
            doc_count = row['doc_count'] or 0

            # Check if form is completed (has essential fields)
            form_completed = bool(
                row['borrower_name'] and
                row['entity_type'] and
                row['pincode']
            )

            # Determine workflow type based on status
            workflow_type = 'documents_first' if status == 'documents_pending' else 'form_first'

            # Determine next step
            if workflow_type == 'documents_first':
                if doc_count == 0:
                    next_step = "Upload documents to begin"
                    completion = 10
                elif doc_count > 0 and not form_completed:
                    next_step = "Review and complete form with auto-filled data"
                    completion = 50
                else:
                    next_step = "Case ready for processing"
                    completion = 100
            else:
                if not form_completed:
                    next_step = "Complete borrower information form"
                    completion = 20
                elif doc_count == 0:
                    next_step = "Upload required documents"
                    completion = 60
                else:
                    next_step = "Case ready for processing"
                    completion = 100

            return {
                "case_id": case_id,
                "status": status,
                "workflow_type": workflow_type,
                "documents_uploaded": doc_count,
                "form_completed": form_completed,
                "next_step": next_step,
                "completion_percentage": completion
            }

    except Exception as e:
        logger.error(f"Error getting workflow status: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
