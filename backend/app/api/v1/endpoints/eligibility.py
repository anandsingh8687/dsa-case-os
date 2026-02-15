"""Eligibility Scoring Endpoints

Provides REST API for eligibility matching:
- POST /eligibility/case/{case_id}/score - Score a case against all lenders
- GET /eligibility/case/{case_id}/results - Get saved eligibility results
"""

import logging
from typing import Any, Dict, List
from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from uuid import UUID

from app.schemas.shared import EligibilityResponse, BorrowerFeatureVector
from app.db.database import get_db
from app.models.case import Case, BorrowerFeature
from app.services.stages.stage4_eligibility import (
    score_case_eligibility,
    save_eligibility_results,
    load_eligibility_results
)
from app.core.enums import CaseStatus

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/eligibility", tags=["eligibility"])


def _summarize_eligibility(response: EligibilityResponse) -> Dict[str, Any]:
    """Build a user-facing explanation payload for BRE clarity."""
    passed = [r for r in response.results if r.hard_filter_status.value == "pass"]
    failed = [r for r in response.results if r.hard_filter_status.value == "fail"]

    executive_summary = (
        f"Matched {response.lenders_passed} out of {response.total_lenders_evaluated} lenders. "
        "Focus on top-ranked lenders for immediate submission."
        if response.lenders_passed > 0
        else f"No lenders matched currently across {response.total_lenders_evaluated} evaluations. "
        "Use the suggested actions to unlock more lenders."
    )

    passed_insights: List[Dict[str, Any]] = []
    for item in passed[:5]:
        details = item.hard_filter_details or {}
        matched_signals = details.get("matched_signals") if isinstance(details, dict) else []
        passed_insights.append(
            {
                "lender_name": item.lender_name,
                "product_name": item.product_name,
                "score": item.eligibility_score,
                "probability": item.approval_probability.value if item.approval_probability else None,
                "max_ticket": item.expected_ticket_max,
                "why_matched": matched_signals[:3] if isinstance(matched_signals, list) else [],
            }
        )

    failed_insights: List[Dict[str, Any]] = []
    for item in failed[:10]:
        details = item.hard_filter_details or {}
        if isinstance(details, dict):
            reasons = [str(v) for v in details.values()]
        else:
            reasons = [str(details)]
        failed_insights.append(
            {
                "lender_name": item.lender_name,
                "product_name": item.product_name,
                "primary_reason": reasons[0] if reasons else "Hard filter not met",
                "all_reasons": reasons,
            }
        )

    top_actions = response.suggested_actions or []
    if not top_actions and response.dynamic_recommendations:
        for rec in response.dynamic_recommendations[:4]:
            action = rec.get("action") or rec.get("recommendation") or rec.get("title")
            if action:
                top_actions.append(str(action))

    return {
        "case_id": response.case_id,
        "executive_summary": executive_summary,
        "top_actions": top_actions[:5],
        "passed_lender_insights": passed_insights,
        "rejected_lender_insights": failed_insights,
        "dynamic_recommendations": response.dynamic_recommendations[:5],
    }


@router.post("/case/{case_id}/score", response_model=EligibilityResponse)
async def score_eligibility(
    case_id: str,
    db: AsyncSession = Depends(get_db)
):
    """Score eligibility for a case against all active lenders.

    Steps:
    1. Fetch case and borrower feature vector
    2. Run eligibility matching against all lenders
    3. Save results to database
    4. Update case status to 'eligibility_scored'
    5. Return ranked results
    """
    logger.info(f"Scoring eligibility for case {case_id}")

    # 1. Fetch case
    result = await db.execute(
        select(Case).where(Case.case_id == case_id)
    )
    case = result.scalar_one_or_none()

    if not case:
        raise HTTPException(status_code=404, detail=f"Case {case_id} not found")

    # 2. Fetch borrower feature vector
    result = await db.execute(
        select(BorrowerFeature).where(BorrowerFeature.case_id == case.id)
    )
    borrower_db = result.scalar_one_or_none()

    if not borrower_db:
        raise HTTPException(
            status_code=400,
            detail="Borrower feature vector not built. Please run Stage 2 first."
        )

    # Convert DB model to Pydantic schema
    borrower = BorrowerFeatureVector(
        full_name=borrower_db.full_name,
        pan_number=borrower_db.pan_number,
        aadhaar_number=borrower_db.aadhaar_number,
        dob=borrower_db.dob,
        entity_type=borrower_db.entity_type,
        business_vintage_years=borrower_db.business_vintage_years,
        gstin=borrower_db.gstin,
        industry_type=borrower_db.industry_type,
        pincode=borrower_db.pincode,
        annual_turnover=borrower_db.annual_turnover,
        avg_monthly_balance=borrower_db.avg_monthly_balance,
        monthly_credit_avg=borrower_db.monthly_credit_avg,
        emi_outflow_monthly=borrower_db.emi_outflow_monthly,
        bounce_count_12m=borrower_db.bounce_count_12m,
        cash_deposit_ratio=borrower_db.cash_deposit_ratio,
        itr_total_income=borrower_db.itr_total_income,
        cibil_score=borrower_db.cibil_score,
        active_loan_count=borrower_db.active_loan_count,
        overdue_count=borrower_db.overdue_count,
        enquiry_count_6m=borrower_db.enquiry_count_6m,
        feature_completeness=borrower_db.feature_completeness
    )

    # 3. Run eligibility scoring (evaluate ALL lenders regardless of program type)
    eligibility_response = await score_case_eligibility(
        borrower=borrower,
        program_type=None  # Changed: Evaluate ALL lenders, not filtered by program type
    )

    # Set case_id in response
    eligibility_response.case_id = case_id

    # 4. Save results to database
    await save_eligibility_results(
        case_id=case.id,
        results=eligibility_response.results
    )

    # 5. Update case status
    case.status = CaseStatus.ELIGIBILITY_SCORED.value
    await db.commit()

    logger.info(
        f"Eligibility scoring complete for case {case_id}: "
        f"{eligibility_response.lenders_passed}/{eligibility_response.total_lenders_evaluated} passed"
    )

    return eligibility_response


@router.get("/case/{case_id}/results", response_model=EligibilityResponse)
async def get_eligibility_results(
    case_id: str,
    db: AsyncSession = Depends(get_db)
):
    """Get saved eligibility results for a case.

    Returns:
        Previously computed eligibility results
    """
    logger.info(f"Fetching eligibility results for case {case_id}")

    # Fetch case
    result = await db.execute(
        select(Case).where(Case.case_id == case_id)
    )
    case = result.scalar_one_or_none()

    if not case:
        raise HTTPException(status_code=404, detail=f"Case {case_id} not found")

    # Load eligibility results
    eligibility_response = await load_eligibility_results(case.id)

    if not eligibility_response:
        raise HTTPException(
            status_code=404,
            detail=f"No eligibility results found for case {case_id}. Please run scoring first."
        )

    logger.info(
        f"Retrieved eligibility results for case {case_id}: "
        f"{eligibility_response.lenders_passed}/{eligibility_response.total_lenders_evaluated} lenders"
    )

    return eligibility_response


@router.get("/case/{case_id}/explain")
async def explain_eligibility(
    case_id: str,
    db: AsyncSession = Depends(get_db),
):
    """
    Return a lender-by-lender explainability payload for UI and DSA communication.

    This endpoint is designed for Fix 4 (BRE Clarity): it converts scoring output
    into concise explanations and actionable next steps.
    """
    result = await db.execute(select(Case).where(Case.case_id == case_id))
    case = result.scalar_one_or_none()
    if not case:
        raise HTTPException(status_code=404, detail=f"Case {case_id} not found")

    eligibility_response = await load_eligibility_results(case.id)
    if not eligibility_response:
        raise HTTPException(
            status_code=404,
            detail=f"No eligibility results found for case {case_id}. Please run scoring first.",
        )

    return _summarize_eligibility(eligibility_response)
