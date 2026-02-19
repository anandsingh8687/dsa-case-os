"""Case Report API Endpoints

Endpoints for generating and retrieving case intelligence reports.
"""

import logging
import time
from uuid import UUID
from pathlib import Path

from fastapi import APIRouter, HTTPException, Response
from fastapi.responses import FileResponse

from app.schemas.shared import CaseReportData
from app.services.stages.stage5_report import (
    assemble_case_report,
    save_report_to_db,
    load_report_from_db,
    generate_whatsapp_summary,
)
from app.services.stages.stage5_pdf_generator import (
    generate_pdf_report,
    save_pdf_to_file,
)
from app.db.database import get_db_session
from app.core.enums import CaseStatus

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/reports", tags=["reports"])


# ═══════════════════════════════════════════════════════════════
# HELPER FUNCTIONS
# ═══════════════════════════════════════════════════════════════

async def get_case_uuid_from_case_id(case_id: str) -> UUID:
    """Convert case_id string to UUID.

    Args:
        case_id: The case ID string (e.g., CASE-20250210-0001)

    Returns:
        Case UUID

    Raises:
        HTTPException: If case not found
    """
    async with get_db_session() as db:
        row = await db.fetchrow(
            "SELECT id FROM cases WHERE case_id = $1",
            case_id
        )

        if not row:
            raise HTTPException(status_code=404, detail=f"Case {case_id} not found")

        return row['id']


async def update_case_status(case_uuid: UUID, status: CaseStatus) -> None:
    """Update case status.

    Args:
        case_uuid: The case UUID
        status: New status
    """
    async with get_db_session() as db:
        await db.execute(
            "UPDATE cases SET status = $1, updated_at = NOW() WHERE id = $2",
            status.value,
            case_uuid
        )


# ═══════════════════════════════════════════════════════════════
# ENDPOINTS
# ═══════════════════════════════════════════════════════════════

@router.post("/case/{case_id}/generate")
async def generate_report(case_id: str):
    """Generate a complete case intelligence report.

    This endpoint:
    1. Assembles all case data (borrower features, documents, eligibility)
    2. Generates PDF report
    3. Saves report to database
    4. Updates case status

    Args:
        case_id: The case ID (e.g., CASE-20250210-0001)

    Returns:
        Success message with report details
    """
    logger.info(f"Generating report for case {case_id}")
    started_at = time.perf_counter()
    assemble_ms = 0.0
    pdf_ms = 0.0
    save_ms = 0.0

    try:
        # Get case UUID
        case_uuid = await get_case_uuid_from_case_id(case_id)

        # Assemble report data
        assemble_started = time.perf_counter()
        report_data = await assemble_case_report(case_uuid)
        assemble_ms = round((time.perf_counter() - assemble_started) * 1000, 2)

        if not report_data:
            raise HTTPException(
                status_code=400,
                detail="Insufficient data to generate report. Please complete borrower features and eligibility scoring first."
            )

        # Generate PDF
        pdf_started = time.perf_counter()
        pdf_bytes = generate_pdf_report(report_data)
        pdf_ms = round((time.perf_counter() - pdf_started) * 1000, 2)

        # Save PDF to storage
        # In production, this would go to S3. For now, save locally.
        storage_dir = Path("/tmp/dsa_case_reports")
        storage_dir.mkdir(parents=True, exist_ok=True)

        pdf_filename = f"{case_id}_report.pdf"
        pdf_path = storage_dir / pdf_filename

        save_pdf_to_file(pdf_bytes, str(pdf_path))

        # Save report data to database
        save_started = time.perf_counter()
        storage_key = str(pdf_path)  # In production, this would be S3 key
        report_uuid = await save_report_to_db(case_uuid, report_data, storage_key)

        # Update case status
        await update_case_status(case_uuid, CaseStatus.REPORT_GENERATED)
        save_ms = round((time.perf_counter() - save_started) * 1000, 2)

        logger.info(f"Report generated successfully for case {case_id}")
        total_ms = round((time.perf_counter() - started_at) * 1000, 2)

        return {
            "status": "success",
            "case_id": case_id,
            "report_id": str(report_uuid),
            "pdf_path": storage_key,
            "pdf_size_bytes": len(pdf_bytes),
            "lenders_matched": len([
                lm for lm in report_data.lender_matches
                if lm.hard_filter_status.value == "pass"
            ]),
            "strengths_count": len(report_data.strengths),
            "risks_count": len(report_data.risk_flags),
            "timing_ms": {
                "assemble_report": assemble_ms,
                "pdf_generation": pdf_ms,
                "save_and_status_update": save_ms,
                "total": total_ms,
            },
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating report for case {case_id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error generating report: {str(e)}")


@router.get("/case/{case_id}/report", response_model=CaseReportData)
async def get_case_report(case_id: str):
    """Get the generated report data for a case.

    This returns the structured JSON report data, not the PDF.

    Args:
        case_id: The case ID (e.g., CASE-20250210-0001)

    Returns:
        CaseReportData object
    """
    logger.info(f"Retrieving report for case {case_id}")

    try:
        # Get case UUID
        case_uuid = await get_case_uuid_from_case_id(case_id)

        # Load report from database
        report_data = await load_report_from_db(case_uuid)

        if not report_data:
            raise HTTPException(
                status_code=404,
                detail=f"No report found for case {case_id}. Generate the report first."
            )

        return report_data

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving report for case {case_id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error retrieving report: {str(e)}")


@router.get("/case/{case_id}/report/pdf")
async def download_report_pdf(case_id: str):
    """Download the PDF report for a case.

    Args:
        case_id: The case ID (e.g., CASE-20250210-0001)

    Returns:
        PDF file download
    """
    logger.info(f"Downloading PDF report for case {case_id}")

    try:
        # Get case UUID
        case_uuid = await get_case_uuid_from_case_id(case_id)

        # Get storage key from database
        async with get_db_session() as db:
            row = await db.fetchrow(
                """
                SELECT storage_key
                FROM case_reports
                WHERE case_id = $1 AND report_type = 'full'
                ORDER BY generated_at DESC
                LIMIT 1
                """,
                case_uuid
            )

            if not row or not row['storage_key']:
                raise HTTPException(
                    status_code=404,
                    detail=f"No PDF report found for case {case_id}. Generate the report first."
                )

            storage_key = row['storage_key']

        # Check if file exists
        pdf_path = Path(storage_key)
        if not pdf_path.exists():
            raise HTTPException(
                status_code=404,
                detail=f"PDF file not found at {storage_key}"
            )

        # Return file
        return FileResponse(
            path=str(pdf_path),
            media_type='application/pdf',
            filename=f"{case_id}_report.pdf",
            headers={
                'Content-Disposition': f'attachment; filename="{case_id}_report.pdf"'
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error downloading PDF for case {case_id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error downloading PDF: {str(e)}")


@router.get("/case/{case_id}/report/whatsapp")
async def get_whatsapp_summary(case_id: str):
    """Get WhatsApp-friendly summary for a case.

    This returns a short text summary that can be copied and pasted into WhatsApp.

    Args:
        case_id: The case ID (e.g., CASE-20250210-0001)

    Returns:
        Plain text WhatsApp summary
    """
    logger.info(f"Generating WhatsApp summary for case {case_id}")

    try:
        # Get case UUID
        case_uuid = await get_case_uuid_from_case_id(case_id)

        # Load report from database
        report_data = await load_report_from_db(case_uuid)

        if not report_data:
            raise HTTPException(
                status_code=404,
                detail=f"No report found for case {case_id}. Generate the report first."
            )

        # Generate WhatsApp summary
        summary = generate_whatsapp_summary(report_data)

        return Response(
            content=summary,
            media_type="text/plain; charset=utf-8"
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating WhatsApp summary for case {case_id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error generating WhatsApp summary: {str(e)}")


@router.get("/case/{case_id}/report/regenerate")
async def regenerate_report(case_id: str):
    """Regenerate report for a case (re-runs the entire report generation).

    This is useful when:
    - Borrower data has been updated
    - New documents have been added
    - Eligibility has been re-scored

    Args:
        case_id: The case ID (e.g., CASE-20250210-0001)

    Returns:
        Success message
    """
    logger.info(f"Regenerating report for case {case_id}")

    # Simply call the generate endpoint
    return await generate_report(case_id)


# ═══════════════════════════════════════════════════════════════
# LLM-BASED NARRATIVE REPORTS
# ═══════════════════════════════════════════════════════════════

from app.services.llm_report_service import llm_report_service


@router.get("/case/{case_id}/narrative/profile")
async def get_narrative_profile_report(case_id: str):
    """
    Generate LLM-based narrative profile report.

    Instead of showing field-value pairs, generates a professional narrative
    describing the borrower's business, financial health, and credit profile.

    Args:
        case_id: Case ID

    Returns:
        {
            'success': bool,
            'case_id': str,
            'report_type': 'profile',
            'narrative': str (full text),
            'sections': {
                'business_overview': str,
                'financial_health': str,
                'credit_profile': str,
                'risk_assessment': str
            },
            'generated_at': str
        }
    """
    logger.info(f"Generating narrative profile report for case {case_id}")

    try:
        report = await llm_report_service.generate_borrower_profile_report(case_id)
        return report
    except Exception as e:
        logger.error(f"Error generating narrative profile: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error generating narrative profile: {str(e)}")


@router.get("/case/{case_id}/narrative/eligibility")
async def get_narrative_eligibility_report(case_id: str):
    """
    Generate LLM-based narrative eligibility report.

    Explains eligibility results in flowing paragraphs instead of showing
    raw numbers and pass/fail indicators.

    Args:
        case_id: Case ID

    Returns:
        {
            'success': bool,
            'case_id': str,
            'report_type': 'eligibility',
            'narrative': str,
            'sections': {...},
            'generated_at': str
        }
    """
    logger.info(f"Generating narrative eligibility report for case {case_id}")

    try:
        report = await llm_report_service.generate_eligibility_report(case_id)
        return report
    except Exception as e:
        logger.error(f"Error generating narrative eligibility: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error generating narrative eligibility: {str(e)}")


@router.get("/case/{case_id}/narrative/documents")
async def get_narrative_document_report(case_id: str):
    """
    Generate LLM-based narrative document summary.

    Describes uploaded documents in professional narrative form.

    Args:
        case_id: Case ID

    Returns:
        {
            'success': bool,
            'case_id': str,
            'report_type': 'documents',
            'narrative': str,
            'sections': {...},
            'generated_at': str
        }
    """
    logger.info(f"Generating narrative document report for case {case_id}")

    try:
        report = await llm_report_service.generate_document_summary(case_id)
        return report
    except Exception as e:
        logger.error(f"Error generating narrative documents: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error generating narrative documents: {str(e)}")


@router.get("/case/{case_id}/narrative/comprehensive")
async def get_comprehensive_narrative_report(case_id: str):
    """
    Generate comprehensive LLM-based narrative report.

    Combines all aspects (profile, eligibility, documents) into a single
    flowing narrative suitable for presenting to management or lenders.

    Args:
        case_id: Case ID

    Returns:
        {
            'success': bool,
            'case_id': str,
            'report_type': 'comprehensive',
            'narrative': str (full report),
            'sections': {
                'executive_summary': str,
                'borrower_profile': str,
                'financial_analysis': str,
                'credit_assessment': str,
                'eligibility_results': str,
                'documentation_review': str,
                'recommendations': str
            },
            'generated_at': str
        }
    """
    logger.info(f"Generating comprehensive narrative report for case {case_id}")

    try:
        report = await llm_report_service.generate_comprehensive_report(case_id)
        return report
    except Exception as e:
        logger.error(f"Error generating comprehensive narrative: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error generating comprehensive narrative: {str(e)}")
