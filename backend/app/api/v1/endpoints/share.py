"""
Share API Endpoints

Endpoints for generating shareable content for WhatsApp, email, etc.
"""

import logging
from typing import Optional, Dict, Any
from urllib.parse import quote
from pydantic import BaseModel

from fastapi import APIRouter, HTTPException

from app.services.llm_report_service import llm_report_service
from app.db.database import get_db_session
from app.core.deps import CurrentUser

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/share", tags=["share"])


# ============================================================
# REQUEST/RESPONSE MODELS
# ============================================================

class WhatsAppShareRequest(BaseModel):
    case_id: str
    share_type: str  # 'profile', 'eligibility', 'comprehensive', 'summary'
    recipient_number: Optional[str] = None  # If provided, send via linked WhatsApp


class WhatsAppShareResponse(BaseModel):
    success: bool
    whatsapp_url: str
    share_text: str
    error: Optional[str] = None


# ============================================================
# WHATSAPP SHARE ENDPOINTS
# ============================================================

@router.post("/whatsapp", response_model=WhatsAppShareResponse)
async def generate_whatsapp_share_link(
    request: WhatsAppShareRequest,
    current_user: CurrentUser
):
    """
    Generate WhatsApp share link with formatted case information.

    Instead of "Copy Text" button, this generates a wa.me link that opens
    WhatsApp with pre-filled message containing the case report.

    Args:
        request: Share request with case_id and share_type
        current_user: Authenticated user

    Returns:
        {
            'success': bool,
            'whatsapp_url': 'https://wa.me/?text=...',
            'share_text': 'Formatted text that will be shared'
        }
    """
    logger.info(f"Generating WhatsApp share link for case {request.case_id}, type: {request.share_type}")

    try:
        # Generate share text based on type
        share_text = await _generate_share_text(request.case_id, request.share_type)

        if not share_text:
            raise HTTPException(status_code=404, detail="Case not found or insufficient data")

        # Encode for URL
        encoded_text = quote(share_text)

        # Generate WhatsApp URL
        if request.recipient_number:
            # Send to specific number
            # Format: https://wa.me/919876543210?text=...
            clean_number = request.recipient_number.replace('+', '').replace(' ', '').replace('-', '')
            whatsapp_url = f"https://wa.me/{clean_number}?text={encoded_text}"
        else:
            # Open WhatsApp with pre-filled text (user chooses recipient)
            whatsapp_url = f"https://wa.me/?text={encoded_text}"

        return WhatsAppShareResponse(
            success=True,
            whatsapp_url=whatsapp_url,
            share_text=share_text
        )

    except Exception as e:
        logger.error(f"Error generating WhatsApp share link: {e}", exc_info=True)
        return WhatsAppShareResponse(
            success=False,
            whatsapp_url="",
            share_text="",
            error=str(e)
        )


@router.get("/whatsapp/{case_id}/{share_type}")
async def get_whatsapp_share_link(
    case_id: str,
    share_type: str,
    recipient_number: Optional[str] = None,
    current_user: CurrentUser = None
):
    """
    GET endpoint for WhatsApp share (for direct browser navigation).

    Args:
        case_id: Case ID
        share_type: Type of share (profile, eligibility, etc.)
        recipient_number: Optional recipient number

    Returns:
        WhatsApp share link response
    """
    request = WhatsAppShareRequest(
        case_id=case_id,
        share_type=share_type,
        recipient_number=recipient_number
    )

    return await generate_whatsapp_share_link(request, current_user)


# ============================================================
# SHARE TEXT GENERATION
# ============================================================

async def _generate_share_text(case_id: str, share_type: str) -> Optional[str]:
    """
    Generate formatted text for WhatsApp sharing based on share type.

    Args:
        case_id: Case ID
        share_type: Type of share

    Returns:
        Formatted text ready for WhatsApp sharing
    """
    if share_type == 'summary':
        return await _generate_summary_share(case_id)
    elif share_type == 'profile':
        return await _generate_profile_share(case_id)
    elif share_type == 'eligibility':
        return await _generate_eligibility_share(case_id)
    elif share_type == 'comprehensive':
        return await _generate_comprehensive_share(case_id)
    else:
        return None


async def _generate_summary_share(case_id: str) -> Optional[str]:
    """
    Generate concise summary for WhatsApp (200-300 characters).

    Example:
    "🏦 Loan Application Update

    Case: CASE-20260210-0001
    Borrower: LAKSHMI TRADERS
    CIBIL: 720 ✅
    Vintage: 1.85 years
    Matched Lenders: 12/45

    Status: Ready for submission to matched lenders.

    📱 View full report: [link]"
    """
    try:
        async with get_db_session() as db:
            query = """
                SELECT
                    c.case_id,
                    c.borrower_name,
                    c.loan_amount_requested,
                    bf.cibil_score,
                    bf.business_vintage_years
                FROM cases c
                LEFT JOIN borrower_features bf ON c.id = bf.case_id
                WHERE c.case_id = $1
            """

            row = await db.fetchrow(query, case_id)

            if not row:
                return None

            # Get eligibility count
            eligibility_query = """
                SELECT COUNT(*) FILTER (WHERE passed = TRUE) as passed_count,
                       COUNT(*) as total_count
                FROM eligibility_results er
                INNER JOIN cases c ON er.case_id = c.id
                WHERE c.case_id = $1
            """

            eligibility_row = await db.fetchrow(eligibility_query, case_id)

            passed = eligibility_row['passed_count'] if eligibility_row else 0
            total = eligibility_row['total_count'] if eligibility_row else 0

            # Format share text
            cibil_indicator = "✅" if row['cibil_score'] and row['cibil_score'] >= 700 else "⚠️"

            amount_str = f"₹{row['loan_amount_requested']:,.0f}" if row['loan_amount_requested'] else 'N/A'

            share_text = f"""🏦 *Loan Application Update*

📋 Case: {row['case_id']}
👤 Borrower: {row['borrower_name'] or 'N/A'}
💰 Amount: {amount_str}
📊 CIBIL: {row['cibil_score'] or 'N/A'} {cibil_indicator}
🏢 Vintage: {row['business_vintage_years'] or 'N/A'} years
🎯 Matched Lenders: {passed}/{total}

Status: {"Ready for submission" if passed > 0 else "Needs improvement"}

_Generated by DSA Case OS_"""

            return share_text

    except Exception as e:
        logger.error(f"Error generating summary share: {e}")
        return None


async def _generate_profile_share(case_id: str) -> Optional[str]:
    """
    Generate profile summary for WhatsApp (500-600 characters).

    Includes key borrower details in a structured format.
    """
    try:
        async with get_db_session() as db:
            query = """
                SELECT
                    c.case_id,
                    c.borrower_name,
                    c.entity_type,
                    c.industry_type,
                    c.pincode,
                    c.loan_amount_requested,
                    bf.business_vintage_years,
                    bf.monthly_turnover,
                    bf.cibil_score,
                    bf.active_loan_count,
                    bf.overdue_count
                FROM cases c
                LEFT JOIN borrower_features bf ON c.id = bf.case_id
                WHERE c.case_id = $1
            """

            row = await db.fetchrow(query, case_id)

            if not row:
                return None

            turnover_str = f"₹{row['monthly_turnover']:,.0f}" if row['monthly_turnover'] else 'N/A'
            amount_str = f"₹{row['loan_amount_requested']:,.0f}" if row['loan_amount_requested'] else 'N/A'

            share_text = f"""🏦 *Borrower Profile*

📋 Case: {row['case_id']}

*Basic Information*
• Name: {row['borrower_name'] or 'N/A'}
• Entity: {row['entity_type'] or 'N/A'}
• Industry: {row['industry_type'] or 'N/A'}
• Location: {row['pincode'] or 'N/A'}

*Business Metrics*
• Vintage: {row['business_vintage_years'] or 'N/A'} years
• Monthly Turnover: {turnover_str}

*Credit Profile*
• CIBIL Score: {row['cibil_score'] or 'N/A'}
• Active Loans: {row['active_loan_count'] or '0'}
• Overdues: {row['overdue_count'] or '0'}

*Loan Request*
• Amount: {amount_str}

_Generated by DSA Case OS_"""

            return share_text

    except Exception as e:
        logger.error(f"Error generating profile share: {e}")
        return None


async def _generate_eligibility_share(case_id: str) -> Optional[str]:
    """
    Generate eligibility summary for WhatsApp.

    Lists matched lenders and key reasons.
    """
    try:
        async with get_db_session() as db:
            # Get eligibility results
            query = """
                SELECT
                    er.lender_name,
                    er.product_name,
                    er.passed,
                    er.score
                FROM eligibility_results er
                INNER JOIN cases c ON er.case_id = c.id
                WHERE c.case_id = $1
                ORDER BY er.passed DESC, er.score DESC
                LIMIT 10
            """

            rows = await db.fetch(query, case_id)

            if not rows:
                return None

            passed_lenders = [r for r in rows if r['passed']]
            total = len(rows)

            share_text = f"""🎯 *Eligibility Results*

📋 Case: {case_id}

*Summary*
• Matched Lenders: {len(passed_lenders)}/{total}
• Pass Rate: {len(passed_lenders)/total*100:.1f}%

*Top Matches*
"""

            for i, lender in enumerate(passed_lenders[:5], 1):
                share_text += f"{i}. {lender['lender_name']} - {lender['product_name']}\n"

            if not passed_lenders:
                share_text += "\nNo lenders matched yet. Consider improving:\n"
                share_text += "• CIBIL score\n"
                share_text += "• Business vintage\n"
                share_text += "• Monthly turnover\n"

            share_text += "\n_Generated by DSA Case OS_"

            return share_text

    except Exception as e:
        logger.error(f"Error generating eligibility share: {e}")
        return None


async def _generate_comprehensive_share(case_id: str) -> Optional[str]:
    """
    Generate comprehensive report for WhatsApp (longer format).

    Uses LLM-generated narrative if available.
    """
    try:
        # Try to get LLM narrative
        report = await llm_report_service.generate_comprehensive_report(case_id)

        if report.get('success') and report.get('narrative'):
            # Use executive summary section if available
            sections = report.get('sections', {})
            executive_summary = sections.get('executive_summary', '')

            if executive_summary:
                share_text = f"""📄 *Comprehensive Case Report*

📋 Case: {case_id}

*Executive Summary*
{executive_summary}

*Full Report*
View complete analysis with all details in the DSA Case OS platform.

_Generated by DSA Case OS_"""

                return share_text

        # Fallback to basic comprehensive share
        return await _generate_fallback_comprehensive_share(case_id)

    except Exception as e:
        logger.error(f"Error generating comprehensive share: {e}")
        return await _generate_fallback_comprehensive_share(case_id)


async def _generate_fallback_comprehensive_share(case_id: str) -> Optional[str]:
    """Fallback comprehensive share without LLM."""
    profile = await _generate_profile_share(case_id)
    eligibility = await _generate_eligibility_share(case_id)

    if profile and eligibility:
        return f"""{profile}

---

{eligibility}"""

    return profile or eligibility
