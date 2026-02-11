"""Eligibility Scoring Endpoints

Provides REST API for eligibility matching:
- POST /eligibility/case/{case_id}/score - Score a case against all lenders
- GET /eligibility/case/{case_id}/results - Get saved eligibility results
"""

import logging
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
