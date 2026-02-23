"""Stage 5: Case Intelligence Report Generation

Assembles all data (borrower features, documents, eligibility results) into a
structured report with strengths analysis, risk flags, and submission strategy.

This is the PRIMARY PAID DELIVERABLE for DSAs.
"""

import logging
import asyncio
from typing import List, Optional, Tuple
from uuid import UUID
from datetime import datetime

from openai import AsyncOpenAI

from app.schemas.shared import (
    BorrowerFeatureVector,
    DocumentChecklist,
    EligibilityResult,
    CaseReportData,
)
from app.core.enums import HardFilterStatus, ApprovalProbability, DocumentType, ProgramType
from app.db.database import get_db_session
from app.core.config import settings
from app.services.rag_service import search_relevant_lender_chunks

logger = logging.getLogger(__name__)
LLM_STRATEGY_TIMEOUT_SECONDS = 6.0


# ═══════════════════════════════════════════════════════════════
# DATA ASSEMBLY
# ═══════════════════════════════════════════════════════════════

async def load_borrower_features(case_id: UUID) -> Optional[BorrowerFeatureVector]:
    """Load borrower feature vector from database.

    Args:
        case_id: The case UUID

    Returns:
        BorrowerFeatureVector or None if not found
    """
    async with get_db_session() as db:
        row = await db.fetchrow(
            "SELECT * FROM borrower_features WHERE case_id = $1",
            case_id
        )

        if not row:
            return None

        # Convert row to dict
        data = dict(row)

        # Remove id and case_id fields
        data.pop('id', None)
        data.pop('case_id', None)
        data.pop('last_updated', None)

        return BorrowerFeatureVector(**data)


async def load_document_checklist(case_id: UUID) -> Optional[DocumentChecklist]:
    """Load document checklist for a case.

    This reconstructs the DocumentChecklist from the documents table.
    In production, this might be cached in a separate table.

    Args:
        case_id: The case UUID

    Returns:
        DocumentChecklist or None
    """
    async with get_db_session() as db:
        # Get case program type
        case_row = await db.fetchrow(
            "SELECT program_type FROM cases WHERE id = $1",
            case_id
        )

        if not case_row or not case_row['program_type']:
            return None

        program_type = ProgramType(case_row['program_type'])

        # Get all documents for this case
        docs = await db.fetch(
            """
            SELECT doc_type, status, original_filename
            FROM documents
            WHERE case_id = $1 AND status != 'failed'
            """,
            case_id
        )

        # Categorize documents
        available = []
        unreadable = []

        for doc in docs:
            try:
                doc_type = DocumentType(doc['doc_type'])
                if doc_type != DocumentType.UNKNOWN:
                    available.append(doc_type)
                else:
                    if doc['original_filename']:
                        unreadable.append(doc['original_filename'])
            except:
                if doc['original_filename']:
                    unreadable.append(doc['original_filename'])

        # Define required documents based on program type
        required = get_required_documents(program_type)

        # Calculate missing
        missing = [doc for doc in required if doc not in available]

        # Optional documents present
        all_optional = [
            DocumentType.PROPERTY_DOCUMENTS,
            DocumentType.FINANCIAL_STATEMENTS,
            DocumentType.UDYAM_SHOP_LICENSE,
        ]
        optional_present = [doc for doc in available if doc in all_optional]

        # Calculate completeness score
        if required:
            completeness_score = (len([d for d in required if d in available]) / len(required)) * 100
        else:
            completeness_score = 100.0

        return DocumentChecklist(
            program_type=program_type,
            available=available,
            missing=missing,
            unreadable=unreadable,
            optional_present=optional_present,
            completeness_score=round(completeness_score, 2)
        )


def get_required_documents(program_type: ProgramType) -> List[DocumentType]:
    """Get required documents for a program type."""
    common = [
        DocumentType.AADHAAR,
        DocumentType.PAN_PERSONAL,
        DocumentType.BANK_STATEMENT,
    ]

    if program_type == ProgramType.BANKING:
        return common + [DocumentType.BANK_STATEMENT]  # Emphasized
    elif program_type == ProgramType.INCOME:
        return common + [
            DocumentType.ITR,
            DocumentType.GST_RETURNS,
        ]
    else:  # HYBRID
        return common + [
            DocumentType.BANK_STATEMENT,
            DocumentType.ITR,
            DocumentType.GST_RETURNS,
        ]


async def load_eligibility_results(case_id: UUID) -> List[EligibilityResult]:
    """Load ranked eligibility results from database.

    Args:
        case_id: The case UUID

    Returns:
        List of EligibilityResult sorted by rank
    """
    async with get_db_session() as db:
        results_query = """
            SELECT
                er.*,
                l.lender_name,
                lp.product_name
            FROM eligibility_results er
            INNER JOIN lender_products lp ON er.lender_product_id = lp.id
            INNER JOIN lenders l ON lp.lender_id = l.id
            WHERE er.case_id = $1
            ORDER BY er.rank NULLS LAST, er.eligibility_score DESC NULLS LAST
        """

        rows = await db.fetch(results_query, case_id)

        results = []
        for row in rows:
            import json

            hard_status = HardFilterStatus(row['hard_filter_status'])

            result = EligibilityResult(
                lender_name=row['lender_name'],
                product_name=row['product_name'],
                hard_filter_status=hard_status,
                hard_filter_details=json.loads(row['hard_filter_details']) if row['hard_filter_details'] else {},
                eligibility_score=row['eligibility_score'],
                approval_probability=ApprovalProbability(row['approval_probability']) if row['approval_probability'] else None,
                expected_ticket_min=row['expected_ticket_min'],
                expected_ticket_max=row['expected_ticket_max'],
                confidence=row['confidence'],
                missing_for_improvement=json.loads(row['missing_for_improvement']) if row['missing_for_improvement'] else [],
                rank=row['rank']
            )
            results.append(result)

        return results


# ═══════════════════════════════════════════════════════════════
# STRENGTHS & RISK FLAGS ANALYSIS
# ═══════════════════════════════════════════════════════════════

def compute_strengths(
    borrower: BorrowerFeatureVector,
    lender_matches: List[EligibilityResult]
) -> List[str]:
    """Detect and list borrower strengths.

    Args:
        borrower: The borrower feature vector
        lender_matches: List of eligibility results

    Returns:
        List of strength statements
    """
    strengths = []

    # CIBIL Score strength
    if borrower.cibil_score:
        if borrower.cibil_score >= 750:
            strengths.append(f"Excellent credit score ({borrower.cibil_score})")
        elif borrower.cibil_score >= 700:
            strengths.append(f"Good credit score ({borrower.cibil_score})")

    # Turnover strength
    if borrower.annual_turnover:
        if borrower.annual_turnover > 50:
            strengths.append(f"Strong annual turnover (₹{borrower.annual_turnover:.1f}L)")

    # Business vintage strength
    if borrower.business_vintage_years:
        if borrower.business_vintage_years > 5:
            strengths.append(f"Well-established business ({borrower.business_vintage_years:.1f} years)")

    # Banking - zero bounces
    if borrower.bounce_count_12m is not None and borrower.bounce_count_12m == 0:
        strengths.append("Clean banking — zero bounces in 12 months")

    # Cash deposit ratio
    if borrower.cash_deposit_ratio is not None:
        if borrower.cash_deposit_ratio < 0.20:  # <20%
            strengths.append("Healthy banking — low cash deposit ratio")

    # FOIR (Fixed Obligation to Income Ratio)
    if borrower.emi_outflow_monthly and borrower.monthly_credit_avg:
        foir = (borrower.emi_outflow_monthly / borrower.monthly_credit_avg) * 100
        if foir < 40:
            strengths.append("Low existing obligations")

    # Multiple lenders matched
    high_prob_count = len([
        lm for lm in lender_matches
        if lm.approval_probability == ApprovalProbability.HIGH
    ])
    if high_prob_count >= 3:
        strengths.append(f"Strong profile — {high_prob_count} lenders matched with high probability")

    return strengths


def compute_risk_flags(
    borrower: BorrowerFeatureVector,
    checklist: Optional[DocumentChecklist],
    lender_matches: List[EligibilityResult]
) -> List[str]:
    """Detect and list risk flags.

    Args:
        borrower: The borrower feature vector
        checklist: Document checklist
        lender_matches: List of eligibility results

    Returns:
        List of risk flag statements
    """
    risks = []

    # Low CIBIL
    if borrower.cibil_score:
        if borrower.cibil_score < 650:
            risks.append(f"Low credit score ({borrower.cibil_score}) — limits lender options")

    # Low vintage
    if borrower.business_vintage_years:
        if borrower.business_vintage_years < 2:
            risks.append(f"Low business vintage ({borrower.business_vintage_years:.1f} years)")

    # Banking issues - bounces
    if borrower.bounce_count_12m and borrower.bounce_count_12m > 3:
        risks.append(f"Banking concern — {borrower.bounce_count_12m} bounced cheques in 12 months")

    # High cash deposit ratio
    if borrower.cash_deposit_ratio:
        if borrower.cash_deposit_ratio > 0.40:  # >40%
            pct = int(borrower.cash_deposit_ratio * 100)
            risks.append(f"High cash deposit ratio ({pct}%) — some lenders may flag this")

    # High FOIR
    if borrower.emi_outflow_monthly and borrower.monthly_credit_avg:
        foir = (borrower.emi_outflow_monthly / borrower.monthly_credit_avg) * 100
        if foir > 55:
            risks.append(f"High existing debt obligations (FOIR: {foir:.0f}%)")

    # Incomplete documentation
    if checklist and checklist.missing:
        missing_count = len(checklist.missing)
        if missing_count > 0:
            risks.append(f"Incomplete documentation — {missing_count} required docs missing")

    # No lenders matched
    passed_count = len([
        lm for lm in lender_matches
        if lm.hard_filter_status == HardFilterStatus.PASS
    ])
    if passed_count == 0:
        suggestions = suggest_improvements(borrower)
        risks.append(f"No eligible lenders found — consider improving {suggestions}")

    return risks


def suggest_improvements(borrower: BorrowerFeatureVector) -> str:
    """Suggest areas for improvement when no lenders match."""
    suggestions = []

    if borrower.cibil_score and borrower.cibil_score < 675:
        suggestions.append("credit score")
    if borrower.business_vintage_years and borrower.business_vintage_years < 2:
        suggestions.append("business vintage")
    if not borrower.gstin:
        suggestions.append("GST registration")
    if borrower.bounce_count_12m and borrower.bounce_count_12m > 2:
        suggestions.append("banking behavior")

    if suggestions:
        return ", ".join(suggestions)
    else:
        return "overall profile"


# ═══════════════════════════════════════════════════════════════
# SUBMISSION STRATEGY
# ═══════════════════════════════════════════════════════════════

async def generate_submission_strategy(
    borrower: BorrowerFeatureVector,
    lender_matches: List[EligibilityResult],
    organization_id: Optional[UUID] = None,
) -> str:
    """Generate LLM-based narrative submission strategy.

    Uses Kimi 2.5 API to generate a professional 2-3 paragraph narrative
    instead of bullet points.

    Args:
        borrower: The borrower feature vector
        lender_matches: List of eligibility results (already ranked)

    Returns:
        Strategy text in narrative format
    """
    # Filter to passed lenders only
    passed = [lm for lm in lender_matches if lm.hard_filter_status == HardFilterStatus.PASS]

    if not passed:
        return ("No lenders currently match this profile. "
                "Focus on improving the identified risk areas before submission.")

    # Get top lender
    top_lender = passed[0]

    # Get special requirements for top lender
    special_notes = await get_lender_special_requirements(top_lender.lender_name)

    def _safe_score(value: Optional[float]) -> str:
        if value is None:
            return "N/A"
        return f"{value:.0f}/100"

    def _safe_ticket_range(min_ticket: Optional[float], max_ticket: Optional[float]) -> str:
        if min_ticket is not None and max_ticket is not None:
            return f"₹{min_ticket:.1f}L-₹{max_ticket:.1f}L"
        if max_ticket is not None:
            return f"Up to ₹{max_ticket:.1f}L"
        if min_ticket is not None:
            return f"From ₹{min_ticket:.1f}L"
        return "Policy based"

    top_ticket_text = _safe_ticket_range(top_lender.expected_ticket_min, top_lender.expected_ticket_max)
    top_score_text = _safe_score(top_lender.eligibility_score)

    # Build lender list for context (top 5)
    lender_context = []
    for idx, lender in enumerate(passed[:5], start=1):
        lender_info = (
            f"{idx}. {lender.lender_name} - {lender.product_name}: "
            f"Score {_safe_score(lender.eligibility_score)}, "
            f"Probability {lender.approval_probability.value.upper()}, "
            f"Ticket {_safe_ticket_range(lender.expected_ticket_min, lender.expected_ticket_max)}"
        )
        lender_context.append(lender_info)

    rag_context_blocks: list[str] = []
    if organization_id:
        try:
            prompt_query = (
                f"{top_lender.lender_name} {top_lender.product_name} policy "
                f"CIBIL {borrower.cibil_score or 'unknown'} "
                f"entity {borrower.entity_type or 'unknown'}"
            )
            rag_chunks = await search_relevant_lender_chunks(
                organization_id=organization_id,
                query=prompt_query,
                top_k=settings.RAG_TOP_K,
            )
            for idx, chunk in enumerate(rag_chunks[: settings.RAG_TOP_K], start=1):
                snippet = (chunk.get("chunk_text") or "").strip()
                if not snippet:
                    continue
                rag_context_blocks.append(
                    f"{idx}. {chunk.get('lender_name') or 'Unknown'} | "
                    f"{chunk.get('product_type') or 'Unknown'} | "
                    f"{chunk.get('section_title') or 'Section'}\n{snippet[:1000]}"
                )
        except Exception as rag_error:  # noqa: BLE001
            logger.warning("Report RAG retrieval failed: %s", rag_error)

    # If LLM API is not configured, use fallback format
    if not settings.LLM_API_KEY:
        logger.warning("LLM_API_KEY not configured, using fallback bullet format")
        return await _generate_fallback_strategy(borrower, passed, special_notes)

    # Call Kimi 2.5 API for narrative generation
    try:
        client = AsyncOpenAI(
            api_key=settings.LLM_API_KEY,
            base_url=settings.LLM_BASE_URL,
            timeout=LLM_STRATEGY_TIMEOUT_SECONDS,
            max_retries=0,
        )

        # Build borrower story elements
        credit_profile = "excellent" if borrower.cibil_score and borrower.cibil_score >= 750 else "good" if borrower.cibil_score and borrower.cibil_score >= 700 else "moderate"
        business_maturity = "well-established" if borrower.business_vintage_years and borrower.business_vintage_years >= 5 else "growing" if borrower.business_vintage_years and borrower.business_vintage_years >= 2 else "emerging"

        prompt = f"""You are a senior business loan consultant crafting a strategic submission plan. Write a compelling, story-driven narrative that guides the DSA through the optimal approach.

**THE BORROWER'S STORY:**
{borrower.full_name or 'The borrower'} operates as a {borrower.entity_type or 'business entity'} with {borrower.business_vintage_years or 'N/A'} years of market presence, representing a {business_maturity} enterprise in the {borrower.industry_type or 'business'} sector. Their financial profile shows:
- Credit standing: {credit_profile} (CIBIL: {borrower.cibil_score or 'pending'})
- Monthly cash flow: ₹{(borrower.monthly_turnover or borrower.monthly_credit_avg or 0) / 100000:.2f} Lakhs
- Banking relationship strength: Average balance of ₹{(borrower.avg_monthly_balance or 0) / 100000:.2f} Lakhs
- Growth ambition: Seeking ₹{getattr(borrower, 'loan_amount_requested', 'N/A')} Lakhs to fuel expansion

**THE OPPORTUNITY LANDSCAPE:**
Our eligibility analysis has identified {len(passed)} compatible lenders, ranked by match strength:
{chr(10).join(lender_context)}

**SPECIAL CONSIDERATIONS FOR PRIMARY TARGET:**
{special_notes or 'No special requirements noted'}

**POLICY REFERENCE CONTEXT (from lender policy documents):**
{chr(10).join(rag_context_blocks) if rag_context_blocks else 'No additional policy snippets available for this org.'}

**YOUR TASK - Write a Strategic Narrative:**
Craft a 3-4 paragraph strategic story that:

PARAGRAPH 1 - THE PERFECT MATCH:
Start with why {top_lender.lender_name}'s {top_lender.product_name} product is the ideal first move for this borrower. Paint a picture of the alignment between the borrower's profile and this lender's appetite. Mention the strong eligibility score ({top_score_text}) and {top_lender.approval_probability.value} approval probability, explaining what this means in practical terms. Describe the realistic ticket range ({top_ticket_text}) and how it fits the borrower's needs.

PARAGRAPH 2 - THE STRATEGIC APPROACH:
Detail the submission playbook. What documents should be prepared? What story should the application tell? Any specific requirements (video KYC, ownership proof, GST compliance) that need attention? Build confidence by explaining the borrower's competitive advantages and how to position them.

PARAGRAPH 3 - THE BACKUP PLAN:
Describe the 2-3 alternative lenders as strategic fallbacks, not just options. Explain when and why to pivot to each one. Create a decision tree in narrative form - "if X happens, then approach Y because..."

PARAGRAPH 4 - THE WINNING MINDSET (optional, if there are risk mitigation steps):
If there are any profile weaknesses, address them proactively. Turn them into opportunities by suggesting tactical moves that strengthen the application.

**CRITICAL REQUIREMENTS:**
- Write in flowing narrative prose, NO bullet points or lists
- Use storytelling language that builds confidence and clarity
- Be specific about numbers, requirements, and timelines
- Make it feel like strategic advice from a trusted advisor
- Keep professional but conversational tone
- Total length: 250-350 words (3-4 rich paragraphs)"""

        response = await asyncio.wait_for(
            client.chat.completions.create(
                model=settings.LLM_MODEL,
                max_tokens=550,
                # Kimi 2.5 on this deployment currently accepts only temperature=1.
                temperature=1.0,
                messages=[
                    {
                        "role": "system",
                        "content": "You are a seasoned business loan strategist with 15+ years of experience. You craft compelling, story-driven submission plans that combine data-driven insights with strategic storytelling. Your narratives build confidence, provide clarity, and turn complex eligibility analysis into actionable wisdom."
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ]
            ),
            timeout=LLM_STRATEGY_TIMEOUT_SECONDS,
        )

        narrative = response.choices[0].message.content.strip()
        logger.info(f"Generated LLM narrative strategy ({len(narrative)} chars)")
        return narrative

    except Exception as e:
        logger.error(f"Error calling Kimi API for strategy: {e}", exc_info=True)
        # Fallback to bullet format if LLM call fails
        return await _generate_fallback_strategy(borrower, passed, special_notes)


async def _generate_fallback_strategy(
    borrower: BorrowerFeatureVector,
    passed: List[EligibilityResult],
    special_notes: Optional[str]
) -> str:
    """Generate fallback bullet-point strategy when LLM is unavailable.

    Args:
        borrower: Borrower feature vector
        passed: List of passed lenders
        special_notes: Special requirements for top lender

    Returns:
        Bullet-point formatted strategy
    """
    top_lender = passed[0]

    score_text = (
        f"{top_lender.eligibility_score:.0f}/100"
        if top_lender.eligibility_score is not None
        else "N/A"
    )
    probability_text = (
        top_lender.approval_probability.value.upper()
        if top_lender.approval_probability
        else "N/A"
    )
    if top_lender.expected_ticket_min is not None and top_lender.expected_ticket_max is not None:
        ticket_text = f"₹{top_lender.expected_ticket_min:.1f}L - ₹{top_lender.expected_ticket_max:.1f}L"
    elif top_lender.expected_ticket_max is not None:
        ticket_text = f"Up to ₹{top_lender.expected_ticket_max:.1f}L"
    elif top_lender.expected_ticket_min is not None:
        ticket_text = f"From ₹{top_lender.expected_ticket_min:.1f}L"
    else:
        ticket_text = "Policy based"

    strategy_parts = []

    # Primary recommendation
    strategy_parts.append(
        f"**Primary Target:** {top_lender.lender_name} - {top_lender.product_name}\n"
        f"- Eligibility Score: {score_text}\n"
        f"- Approval Probability: {probability_text}\n"
        f"- Expected Ticket: {ticket_text}\n"
    )

    if special_notes:
        strategy_parts.append(f"- **Note:** {special_notes}\n")

    # Suggested approach order (top 3-5)
    approach_order = passed[1:min(5, len(passed))]
    if approach_order:
        strategy_parts.append("\n**Suggested Approach Order:**")
        for idx, lender in enumerate(approach_order, start=2):
            lender_score = (
                f"{lender.eligibility_score:.0f}"
                if lender.eligibility_score is not None
                else "N/A"
            )
            lender_prob = (
                lender.approval_probability.value.upper()
                if lender.approval_probability
                else "N/A"
            )
            strategy_parts.append(
                f"\n{idx}. {lender.lender_name} - {lender.product_name} "
                f"(Score: {lender_score}, "
                f"Probability: {lender_prob})"
            )

    # General advice
    strategy_parts.append(
        "\n\n**General Strategy:**\n"
        "- Submit to the primary target first for best chances\n"
        "- Prepare all required documents before submission\n"
        "- If rejected, address feedback before approaching backup lenders"
    )

    return "".join(strategy_parts)


async def get_lender_special_requirements(lender_name: str) -> Optional[str]:
    """Get special requirements/notes for a lender.

    Args:
        lender_name: Name of the lender

    Returns:
        Special requirements text or None
    """
    async with get_db_session() as db:
        row = await db.fetchrow(
            """
            SELECT
                video_kyc_required,
                ownership_proof_required,
                gst_required,
                tele_pd_required,
                fi_required
            FROM lender_products lp
            INNER JOIN lenders l ON lp.lender_id = l.id
            WHERE LOWER(l.lender_name) = LOWER($1)
            LIMIT 1
            """,
            lender_name
        )

        if not row:
            return None

        notes = []
        if row['video_kyc_required']:
            notes.append("requires Video KYC")
        if row['ownership_proof_required']:
            notes.append("needs ownership proof")
        if row['gst_required']:
            notes.append("GST mandatory")
        if row['tele_pd_required']:
            notes.append("telephonic verification required")
        if row['fi_required']:
            notes.append("field investigation required")

        return ", ".join(notes) if notes else None


# ═══════════════════════════════════════════════════════════════
# MAIN ASSEMBLY FUNCTION
# ═══════════════════════════════════════════════════════════════

async def assemble_case_report(case_uuid: UUID) -> Optional[CaseReportData]:
    """Assemble complete case report data.

    This is the main function that orchestrates data gathering and analysis.

    Args:
        case_uuid: The case UUID

    Returns:
        CaseReportData or None if data is insufficient
    """
    logger.info(f"Assembling case report for case {case_uuid}")

    # Get case_id string
    async with get_db_session() as db:
        case_row = await db.fetchrow(
            "SELECT case_id, organization_id FROM cases WHERE id = $1",
            case_uuid
        )

        if not case_row:
            logger.error(f"Case {case_uuid} not found")
            return None

        case_id_str = case_row['case_id']
        case_org_id = case_row.get("organization_id")

    # Load all data
    borrower = await load_borrower_features(case_uuid)
    if not borrower:
        logger.warning(f"No borrower features found for case {case_uuid}")
        # Create empty feature vector
        borrower = BorrowerFeatureVector()

    checklist = await load_document_checklist(case_uuid)
    lender_matches = await load_eligibility_results(case_uuid)

    # Compute analysis
    strengths = compute_strengths(borrower, lender_matches)
    risk_flags = compute_risk_flags(borrower, checklist, lender_matches)
    submission_strategy = await generate_submission_strategy(
        borrower,
        lender_matches,
        organization_id=case_org_id,
    )

    # Missing data advisory
    missing_data_advisory = []
    if not borrower.cibil_score:
        missing_data_advisory.append("CIBIL score not available")
    if not borrower.annual_turnover:
        missing_data_advisory.append("Annual turnover not available")
    if not borrower.business_vintage_years:
        missing_data_advisory.append("Business vintage not available")
    if checklist and checklist.missing:
        for doc in checklist.missing:
            missing_data_advisory.append(f"{doc.value.replace('_', ' ').title()} document missing")

    # Expected loan range
    expected_loan_range = None
    passed = [lm for lm in lender_matches if lm.hard_filter_status == HardFilterStatus.PASS]
    if passed:
        top = passed[0]
        if top.expected_ticket_min and top.expected_ticket_max:
            expected_loan_range = f"₹{top.expected_ticket_min:.1f}L - ₹{top.expected_ticket_max:.1f}L"

    report = CaseReportData(
        case_id=case_id_str,
        borrower_profile=borrower,
        checklist=checklist or DocumentChecklist(
            program_type=ProgramType.BANKING,
            available=[],
            missing=[],
            unreadable=[],
            optional_present=[],
            completeness_score=0.0
        ),
        strengths=strengths,
        risk_flags=risk_flags,
        lender_matches=lender_matches,
        submission_strategy=submission_strategy,
        missing_data_advisory=missing_data_advisory,
        expected_loan_range=expected_loan_range
    )

    logger.info(
        f"Report assembled: {len(strengths)} strengths, "
        f"{len(risk_flags)} risks, {len(lender_matches)} lenders evaluated"
    )

    return report


# ═══════════════════════════════════════════════════════════════
# DATABASE PERSISTENCE
# ═══════════════════════════════════════════════════════════════

async def save_report_to_db(
    case_uuid: UUID,
    report_data: CaseReportData,
    storage_key: Optional[str] = None
) -> UUID:
    """Save report data to database.

    Args:
        case_uuid: The case UUID
        report_data: The assembled report data
        storage_key: Optional S3 key or file path for PDF

    Returns:
        Report UUID
    """
    import json
    from uuid import uuid4

    async with get_db_session() as db:
        case_row = await db.fetchrow("SELECT organization_id FROM cases WHERE id = $1", case_uuid)
        organization_id = case_row["organization_id"] if case_row else None

        # Convert report to JSON
        report_json = report_data.model_dump_json()

        # Insert report
        report_id = uuid4()
        await db.execute(
            """
            INSERT INTO case_reports (id, case_id, organization_id, report_type, storage_key, report_data, generated_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7)
            """,
            report_id,
            case_uuid,
            organization_id,
            'full',
            storage_key,
            report_json,
            datetime.utcnow()
        )

        logger.info(f"Saved report {report_id} to database")

        return report_id


async def load_report_from_db(case_uuid: UUID) -> Optional[CaseReportData]:
    """Load most recent report from database.

    Args:
        case_uuid: The case UUID

    Returns:
        CaseReportData or None
    """
    import json

    async with get_db_session() as db:
        row = await db.fetchrow(
            """
            SELECT report_data
            FROM case_reports
            WHERE case_id = $1 AND report_type = 'full'
            ORDER BY generated_at DESC
            LIMIT 1
            """,
            case_uuid
        )

        if not row or not row['report_data']:
            return None

        # Parse JSON back to CaseReportData
        report_dict = json.loads(row['report_data']) if isinstance(row['report_data'], str) else row['report_data']
        return CaseReportData(**report_dict)


# ═══════════════════════════════════════════════════════════════
# WHATSAPP SUMMARY GENERATOR
# ═══════════════════════════════════════════════════════════════

def generate_whatsapp_summary(report_data: CaseReportData) -> str:
    """Generate comprehensive WhatsApp-friendly summary matching PDF report structure.

    Args:
        report_data: The case report data

    Returns:
        WhatsApp summary text with full report details
    """
    try:
        borrower = report_data.borrower_profile

        # Header
        lines = [
            f"📄 *CASE: {report_data.case_id}*",
            "━━━━━━━━━━━━━━━━━━━━",
            ""
        ]

        # Borrower info
        name = borrower.full_name or "N/A"
        entity = borrower.entity_type.value if borrower.entity_type else "N/A"
        vintage = f"{borrower.business_vintage_years:.1f}yr" if borrower.business_vintage_years else "N/A"

        lines.append(f"👤 *BORROWER*")
        lines.append(f"{name}")
        lines.append(f"{entity} | {vintage}")
        lines.append("")

        # Financial snapshot
        cibil = borrower.cibil_score if borrower.cibil_score else "N/A"
        turnover = f"₹{borrower.annual_turnover:.1f}L" if borrower.annual_turnover else "N/A"
        abb = f"₹{borrower.avg_monthly_balance/100000:.1f}L" if borrower.avg_monthly_balance else "N/A"

        lines.append(f"📊 *FINANCIAL SNAPSHOT*")
        lines.append(f"• CIBIL: {cibil}")
        lines.append(f"• Turnover: {turnover}")
        lines.append(f"• ABB: {abb}")
        lines.append("")

        # ===== STRENGTHS =====
        if report_data.strengths and len(report_data.strengths) > 0:
            lines.append("💪 *STRENGTHS*")
            for strength in report_data.strengths:
                lines.append(f"✓ {strength}")
            lines.append("")

        # ===== RISK FLAGS =====
        if report_data.risk_flags and len(report_data.risk_flags) > 0:
            lines.append("⚠️ *RISK FLAGS*")
            for risk in report_data.risk_flags:
                lines.append(f"• {risk}")
            lines.append("")

        # ===== SUBMISSION STRATEGY =====
        if report_data.submission_strategy:
            lines.append("📋 *SUBMISSION STRATEGY*")
            lines.append(report_data.submission_strategy)
            lines.append("")

        # ===== TOP LENDER MATCHES =====
        passed = [lm for lm in report_data.lender_matches if lm.hard_filter_status == HardFilterStatus.PASS]

        if passed:
            lines.append(f"🎯 *TOP MATCHES ({len(passed)} lenders)*")
            lines.append("")

            # Show top 5 matches with detailed info
            for idx, lm in enumerate(passed[:5], 1):
                # Safely get probability
                prob = "N/A"
                if hasattr(lm, 'approval_probability') and lm.approval_probability:
                    prob = str(lm.approval_probability.value).upper()

                # Safely get score
                score = "N/A"
                if hasattr(lm, 'eligibility_score') and lm.eligibility_score is not None:
                    score = f"{int(lm.eligibility_score)}/100"

                # Format ticket range (only if attributes exist)
                ticket = None
                if hasattr(lm, 'min_ticket_size') and hasattr(lm, 'max_ticket_size'):
                    if lm.min_ticket_size and lm.max_ticket_size:
                        ticket = f"₹{lm.min_ticket_size:.1f}L-₹{lm.max_ticket_size:.1f}L"

                # Build lender line
                lines.append(f"*{idx}. {lm.lender_name}* - {lm.product_name}")

                # Only show fields that are available
                details = []
                if score != "N/A":
                    details.append(f"Score: {score}")
                if prob != "N/A":
                    details.append(f"Probability: {prob}")

                if details:
                    lines.append(f"   {' | '.join(details)}")

                if ticket:
                    lines.append(f"   Expected Ticket: {ticket}")

                lines.append("")

            # Show remaining count if more than 5
            if len(passed) > 5:
                lines.append(f"   ...and {len(passed) - 5} more lenders")
                lines.append("")
        else:
            lines.append("❌ No lenders matched — profile needs improvement")
            lines.append("")

        # ===== MISSING DOCUMENTS =====
        if hasattr(report_data.checklist, 'missing') and report_data.checklist.missing:
            lines.append("📎 *MISSING DOCUMENTS*")
            missing_docs = [doc.value.replace('_', ' ').title() for doc in report_data.checklist.missing[:5]]
            for doc in missing_docs:
                lines.append(f"• {doc}")

            if len(report_data.checklist.missing) > 5:
                lines.append(f"_...and {len(report_data.checklist.missing) - 5} more_")
            lines.append("")

        # Footer
        lines.append("━━━━━━━━━━━━━━━━━━━━")
        lines.append("💡 _Complete report in dashboard_")

        return "\n".join(lines)

    except Exception as e:
        # Fallback to basic summary if comprehensive version fails
        import logging
        import traceback
        error_msg = f"Error in WhatsApp summary: {str(e)}"
        logging.error(error_msg)
        logging.error(traceback.format_exc())

        # Return basic summary
        borrower = report_data.borrower_profile
        name = borrower.full_name or "N/A"
        return f"📄 *CASE: {report_data.case_id}*\n\n👤 Borrower: {name}\n\n⚠️ Report generated successfully.\n💡 View full details in dashboard."
