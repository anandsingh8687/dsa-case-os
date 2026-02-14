"""Stage 4: Eligibility Matching Engine

Matches borrower feature vectors against lender product rules to produce ranked eligibility results.

Architecture:
- Layer 1: Hard Filters (Pass/Fail) - eliminates ineligible lenders
- Layer 2: Weighted Scoring (0-100) - scores eligible lenders
- Layer 3: Ranking & Output - sorts and formats results
"""

import logging
from typing import List, Dict, Any, Optional, Tuple
from datetime import date, datetime
from uuid import UUID

from app.schemas.shared import (
    BorrowerFeatureVector,
    LenderProductRule,
    EligibilityResult,
    EligibilityResponse,
)
from app.core.enums import HardFilterStatus, ApprovalProbability, EntityType
from app.services.lender_service import get_all_products_for_scoring
from app.db.database import get_db_session

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════
# LAYER 1: HARD FILTERS
# ═══════════════════════════════════════════════════════════════

async def apply_hard_filters(
    borrower: BorrowerFeatureVector,
    lender: LenderProductRule
) -> Tuple[HardFilterStatus, Dict[str, Any]]:
    """Apply hard filters to determine if lender is eligible.

    Returns:
        (status, details) where:
        - status: PASS or FAIL
        - details: dict of {filter_name: reason} for failures
    """
    failures = {}

    # Filter 0: Skip lenders with no policy
    if not lender.policy_available:
        failures["policy_available"] = "Policy not available"
        return HardFilterStatus.FAIL, failures

    # Filter 1: Pincode serviceability
    if borrower.pincode:
        is_serviceable = await check_pincode_serviceability(
            lender.lender_name,
            borrower.pincode
        )
        if not is_serviceable:
            failures["pincode"] = f"Pincode {borrower.pincode} not serviceable"

    # Filter 2: CIBIL score
    if lender.min_cibil_score and borrower.cibil_score:
        if borrower.cibil_score < lender.min_cibil_score:
            failures["cibil_score"] = (
                f"CIBIL {borrower.cibil_score} < required {lender.min_cibil_score}"
            )

    # Filter 3: Entity type
    if lender.eligible_entity_types and borrower.entity_type:
        # Normalize entity type for comparison
        borrower_entity = borrower.entity_type.value if isinstance(borrower.entity_type, EntityType) else str(borrower.entity_type)

        # Check if borrower's entity type is in the eligible list (case-insensitive)
        eligible_types_lower = [et.lower() for et in lender.eligible_entity_types]
        if borrower_entity.lower() not in eligible_types_lower:
            failures["entity_type"] = (
                f"{borrower_entity} not in eligible types: {', '.join(lender.eligible_entity_types)}"
            )

    # Filter 4: Business vintage
    if lender.min_vintage_years and borrower.business_vintage_years:
        if borrower.business_vintage_years < lender.min_vintage_years:
            failures["vintage"] = (
                f"{borrower.business_vintage_years}y < required {lender.min_vintage_years}y"
            )

    # Filter 5: Annual turnover
    if lender.min_turnover_annual and borrower.annual_turnover:
        if borrower.annual_turnover < lender.min_turnover_annual:
            failures["turnover"] = (
                f"₹{borrower.annual_turnover}L < required ₹{lender.min_turnover_annual}L"
            )

    # Filter 6: Age (calculate from DOB if available)
    if lender.age_min and lender.age_max and borrower.dob:
        age = calculate_age(borrower.dob)
        if age < lender.age_min or age > lender.age_max:
            failures["age"] = (
                f"Age {age} outside range {lender.age_min}-{lender.age_max}"
            )

    # Filter 7: Average Bank Balance (ABB)
    if lender.min_abb and borrower.avg_monthly_balance:
        if borrower.avg_monthly_balance < lender.min_abb:
            failures["abb"] = (
                f"Avg balance ₹{borrower.avg_monthly_balance:,.0f} < required ₹{lender.min_abb:,.0f}"
            )

    # Determine status
    status = HardFilterStatus.FAIL if failures else HardFilterStatus.PASS

    return status, failures


async def check_pincode_serviceability(lender_name: str, pincode: str) -> bool:
    """Check if a lender services a specific pincode.

    Args:
        lender_name: Name of the lender
        pincode: 6-digit pincode

    Returns:
        True if serviceable, False otherwise
    """
    async with get_db_session() as db:
        count = await db.fetchval(
            """
            SELECT COUNT(*) as count
            FROM lender_pincodes lpc
            INNER JOIN lenders l ON lpc.lender_id = l.id
            WHERE LOWER(l.lender_name) = LOWER($1)
              AND lpc.pincode = $2
            """,
            lender_name,
            pincode
        )
        return count > 0 if count is not None else False


def calculate_age(dob: date) -> int:
    """Calculate age from date of birth."""
    today = date.today()
    return today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))


# ═══════════════════════════════════════════════════════════════
# LAYER 2: WEIGHTED SCORING
# ═══════════════════════════════════════════════════════════════

def calculate_eligibility_score(
    borrower: BorrowerFeatureVector,
    lender: LenderProductRule
) -> float:
    """Calculate composite eligibility score (0-100) using weighted components.

    Components:
    - CIBIL Band (25%)
    - Turnover Band (20%)
    - Business Vintage (15%)
    - Banking Strength (20%)
    - FOIR (10%)
    - Documentation (10%)
    """

    scores = []
    weights = []

    # Component 1: CIBIL Band (25%)
    cibil_score = score_cibil_band(borrower.cibil_score)
    if cibil_score is not None:
        scores.append(cibil_score)
        weights.append(25)

    # Component 2: Turnover Band (20%)
    turnover_score = score_turnover_band(
        borrower.annual_turnover,
        lender.min_turnover_annual
    )
    if turnover_score is not None:
        scores.append(turnover_score)
        weights.append(20)

    # Component 3: Business Vintage (15%)
    vintage_score = score_business_vintage(borrower.business_vintage_years)
    if vintage_score is not None:
        scores.append(vintage_score)
        weights.append(15)

    # Component 4: Banking Strength (20%)
    banking_score = score_banking_strength(
        borrower.avg_monthly_balance,
        borrower.bounce_count_12m,
        borrower.cash_deposit_ratio,
        lender.min_abb
    )
    if banking_score is not None:
        scores.append(banking_score)
        weights.append(20)

    # Component 5: FOIR (10%)
    foir_score = score_foir(
        borrower.emi_outflow_monthly,
        borrower.monthly_credit_avg
    )
    if foir_score is not None:
        scores.append(foir_score)
        weights.append(10)

    # Component 6: Documentation (10%)
    doc_score = score_documentation(borrower, lender)
    if doc_score is not None:
        scores.append(doc_score)
        weights.append(10)

    # Calculate weighted average
    if not scores:
        return 0.0

    total_weight = sum(weights)
    weighted_sum = sum(s * w for s, w in zip(scores, weights))

    return round(weighted_sum / total_weight, 2)


def score_cibil_band(cibil: Optional[int]) -> Optional[float]:
    """Score CIBIL based on bands.

    750+ = 100, 725-749 = 90, 700-724 = 75,
    675-699 = 60, 650-674 = 40, <650 = 20
    """
    if cibil is None:
        return None

    if cibil >= 750:
        return 100.0
    elif cibil >= 725:
        return 90.0
    elif cibil >= 700:
        return 75.0
    elif cibil >= 675:
        return 60.0
    elif cibil >= 650:
        return 40.0
    else:
        return 20.0


def score_turnover_band(
    annual_turnover: Optional[float],
    min_turnover: Optional[float]
) -> Optional[float]:
    """Score turnover based on ratio to minimum requirement.

    >3x = 100, 2-3x = 80, 1.5-2x = 60, 1-1.5x = 40
    """
    if annual_turnover is None or min_turnover is None or min_turnover == 0:
        return None

    ratio = annual_turnover / min_turnover

    if ratio >= 3.0:
        return 100.0
    elif ratio >= 2.0:
        return 80.0
    elif ratio >= 1.5:
        return 60.0
    elif ratio >= 1.0:
        return 40.0
    else:
        return 20.0


def score_business_vintage(vintage_years: Optional[float]) -> Optional[float]:
    """Score business vintage.

    5+ yrs = 100, 3-5 = 80, 2-3 = 60, 1-2 = 40
    """
    if vintage_years is None:
        return None

    if vintage_years >= 5.0:
        return 100.0
    elif vintage_years >= 3.0:
        return 80.0
    elif vintage_years >= 2.0:
        return 60.0
    elif vintage_years >= 1.0:
        return 40.0
    else:
        return 20.0


def score_banking_strength(
    avg_balance: Optional[float],
    bounce_count: Optional[int],
    cash_ratio: Optional[float],
    min_abb: Optional[float]
) -> Optional[float]:
    """Score banking strength composite.

    Combines: avg_balance vs ABB requirement, bounce_count, cash_deposit_ratio
    """
    sub_scores = []

    # Sub-component 1: Average balance vs requirement
    if avg_balance is not None and min_abb is not None and min_abb > 0:
        ratio = avg_balance / min_abb
        if ratio >= 2.0:
            sub_scores.append(100.0)
        elif ratio >= 1.5:
            sub_scores.append(80.0)
        elif ratio >= 1.0:
            sub_scores.append(60.0)
        else:
            sub_scores.append(30.0)

    # Sub-component 2: Bounce count
    if bounce_count is not None:
        if bounce_count == 0:
            sub_scores.append(100.0)
        elif bounce_count <= 2:
            sub_scores.append(70.0)
        else:
            sub_scores.append(30.0)

    # Sub-component 3: Cash deposit ratio
    if cash_ratio is not None:
        if cash_ratio < 0.20:  # <20%
            sub_scores.append(100.0)
        elif cash_ratio < 0.40:  # 20-40%
            sub_scores.append(60.0)
        else:  # >40%
            sub_scores.append(30.0)

    if not sub_scores:
        return None

    return sum(sub_scores) / len(sub_scores)


def score_foir(
    emi_outflow: Optional[float],
    monthly_credit: Optional[float]
) -> Optional[float]:
    """Score Fixed Obligation to Income Ratio (FOIR).

    <30% = 100, 30-45% = 75, 45-55% = 50, 55-65% = 30, >65% = 0
    """
    if emi_outflow is None or monthly_credit is None or monthly_credit == 0:
        return None

    foir = emi_outflow / monthly_credit

    if foir < 0.30:
        return 100.0
    elif foir < 0.45:
        return 75.0
    elif foir < 0.55:
        return 50.0
    elif foir < 0.65:
        return 30.0
    else:
        return 0.0


def score_documentation(
    borrower: BorrowerFeatureVector,
    lender: LenderProductRule
) -> Optional[float]:
    """Score documentation completeness.

    Returns % of lender's required docs that borrower has.
    """
    required_docs = []
    available_docs = []

    # Check GST
    if lender.gst_required:
        required_docs.append("GST")
        if borrower.gstin:
            available_docs.append("GST")

    # Check ownership proof
    if lender.ownership_proof_required:
        required_docs.append("Ownership")
        # We don't have ownership proof in feature vector, assume not available

    # Check KYC (PAN, Aadhaar)
    if lender.kyc_documents:
        if "PAN" in lender.kyc_documents.upper():
            required_docs.append("PAN")
            if borrower.pan_number:
                available_docs.append("PAN")

        if "AADHAAR" in lender.kyc_documents.upper() or "AADHAR" in lender.kyc_documents.upper():
            required_docs.append("Aadhaar")
            if borrower.aadhaar_number:
                available_docs.append("Aadhaar")

    if not required_docs:
        return 100.0  # No docs required = perfect score

    completion_pct = (len(available_docs) / len(required_docs)) * 100
    return round(completion_pct, 2)


# ═══════════════════════════════════════════════════════════════
# LAYER 3: RANKING & OUTPUT FORMATTING
# ═══════════════════════════════════════════════════════════════

def determine_approval_probability(score: float) -> ApprovalProbability:
    """Convert eligibility score to approval probability category."""
    if score >= 75:
        return ApprovalProbability.HIGH
    elif score >= 50:
        return ApprovalProbability.MEDIUM
    else:
        return ApprovalProbability.LOW


def calculate_ticket_range(
    borrower: BorrowerFeatureVector,
    lender: LenderProductRule,
    score: float
) -> Tuple[Optional[float], Optional[float]]:
    """Calculate expected ticket size range based on score and lender limits.

    Returns:
        (min_ticket, max_ticket) in Lakhs
    """
    max_ticket = lender.max_ticket_size

    # If no max ticket size defined, use turnover-based estimate
    if max_ticket is None:
        if borrower.annual_turnover:
            # Typical lending is 10-25% of annual turnover
            if score >= 75:
                max_ticket = borrower.annual_turnover * 0.25
            elif score >= 50:
                max_ticket = borrower.annual_turnover * 0.15
            else:
                max_ticket = borrower.annual_turnover * 0.10
        else:
            max_ticket = None
    else:
        # Cap at turnover-based limit if lower
        if borrower.annual_turnover:
            turnover_limit = borrower.annual_turnover * 0.25
            max_ticket = min(max_ticket, turnover_limit)

    # Min ticket is typically 10-20% of max
    min_ticket = max_ticket * 0.15 if max_ticket else None

    return min_ticket, max_ticket


def identify_missing_for_improvement(
    borrower: BorrowerFeatureVector,
    hard_filter_status: HardFilterStatus,
    score: float
) -> List[str]:
    """Identify what's missing or could be improved."""
    missing = []

    # If failed hard filters, those are the priority
    if hard_filter_status == HardFilterStatus.FAIL:
        return ["Review hard filter failures"]

    # For passed lenders, suggest improvements
    if score < 75:
        # Check weak areas
        if borrower.cibil_score and borrower.cibil_score < 725:
            missing.append("Improve CIBIL score (currently {})".format(borrower.cibil_score))

        if borrower.business_vintage_years and borrower.business_vintage_years < 3:
            missing.append("Business vintage < 3 years")

        if borrower.bounce_count_12m and borrower.bounce_count_12m > 2:
            missing.append("Reduce EMI bounces (currently {})".format(borrower.bounce_count_12m))

        if not borrower.gstin:
            missing.append("Add GST registration")

        if borrower.cash_deposit_ratio and borrower.cash_deposit_ratio > 0.40:
            missing.append("High cash deposit ratio (>40%)")

    return missing


def rank_results(results: List[EligibilityResult]) -> List[EligibilityResult]:
    """Rank eligible lenders by eligibility score (descending)."""
    # Sort by score descending (None scores go to end)
    sorted_results = sorted(
        results,
        key=lambda r: (r.eligibility_score if r.eligibility_score is not None else -1),
        reverse=True
    )

    # Assign ranks
    for idx, result in enumerate(sorted_results, start=1):
        result.rank = idx

    return sorted_results


# ═══════════════════════════════════════════════════════════════
# MAIN SCORING FUNCTION
# ═══════════════════════════════════════════════════════════════

async def score_case_eligibility(
    borrower: BorrowerFeatureVector,
    program_type: Optional[str] = None
) -> EligibilityResponse:
    """Score a borrower against all active lenders.

    Args:
        borrower: The borrower feature vector
        program_type: Filter lenders by program type (banking, income, hybrid)

    Returns:
        EligibilityResponse with ranked results
    """
    logger.info(f"Scoring eligibility for borrower (program_type={program_type})")

    # Get all active lender products
    lenders = await get_all_products_for_scoring(
        program_type=program_type,
        active_only=True
    )

    logger.info(f"Evaluating against {len(lenders)} lender products")

    results = []
    passed_count = 0

    for lender in lenders:
        # Layer 1: Apply hard filters
        hard_status, hard_details = await apply_hard_filters(borrower, lender)

        # Layer 2 & 3: Score and format (only for passed lenders)
        if hard_status == HardFilterStatus.PASS:
            passed_count += 1

            # Calculate eligibility score
            score = calculate_eligibility_score(borrower, lender)

            # Determine probability
            probability = determine_approval_probability(score)

            # Calculate ticket range
            min_ticket, max_ticket = calculate_ticket_range(borrower, lender, score)

            # Identify improvements
            missing = identify_missing_for_improvement(borrower, hard_status, score)

            # Confidence based on feature completeness
            confidence = borrower.feature_completeness / 100.0

            result = EligibilityResult(
                lender_name=lender.lender_name,
                product_name=lender.product_name,
                hard_filter_status=hard_status,
                hard_filter_details={},
                eligibility_score=score,
                approval_probability=probability,
                expected_ticket_min=min_ticket,
                expected_ticket_max=max_ticket,
                confidence=confidence,
                missing_for_improvement=missing,
                rank=None  # Will be set in ranking
            )
        else:
            # Failed hard filters
            result = EligibilityResult(
                lender_name=lender.lender_name,
                product_name=lender.product_name,
                hard_filter_status=hard_status,
                hard_filter_details=hard_details,
                eligibility_score=None,
                approval_probability=None,
                expected_ticket_min=None,
                expected_ticket_max=None,
                confidence=borrower.feature_completeness / 100.0,
                missing_for_improvement=[],
                rank=None
            )

        results.append(result)

    # Rank the passed results
    passed_results = [r for r in results if r.hard_filter_status == HardFilterStatus.PASS]
    ranked_passed = rank_results(passed_results)

    # Combine ranked passed + failed (unranked)
    failed_results = [r for r in results if r.hard_filter_status == HardFilterStatus.FAIL]
    final_results = ranked_passed + failed_results

    logger.info(
        f"Eligibility scoring complete: {passed_count}/{len(lenders)} lenders passed"
    )

    # Generate rejection analysis if no lenders passed
    rejection_reasons = []
    suggested_actions = []
    if passed_count == 0:
        rejection_reasons, suggested_actions = generate_rejection_analysis(
            borrower, failed_results
        )

    # Generate dynamic recommendations (for all cases, not just when passed_count = 0)
    dynamic_recommendations = generate_dynamic_recommendations(borrower, results)

    return EligibilityResponse(
        case_id="",  # Will be filled by caller
        total_lenders_evaluated=len(lenders),
        lenders_passed=passed_count,
        results=final_results,
        rejection_reasons=rejection_reasons,
        suggested_actions=suggested_actions,
        dynamic_recommendations=dynamic_recommendations
    )


def generate_rejection_analysis(
    borrower: BorrowerFeatureVector,
    failed_results: List[EligibilityResult]
) -> Tuple[List[str], List[str]]:
    """Analyze why lenders rejected and suggest improvements.

    Args:
        borrower: The borrower feature vector
        failed_results: List of failed eligibility results

    Returns:
        (rejection_reasons, suggested_actions)
    """
    reason_counts = {}
    reasons_list = []
    actions_set = set()

    # Count failures by reason
    for result in failed_results:
        for reason_key, reason_detail in result.hard_filter_details.items():
            if reason_key not in reason_counts:
                reason_counts[reason_key] = {
                    'count': 0,
                    'detail': reason_detail,
                    'lenders': []
                }
            reason_counts[reason_key]['count'] += 1
            reason_counts[reason_key]['lenders'].append(result.lender_name)

    # Generate human-readable reasons sorted by frequency
    sorted_reasons = sorted(reason_counts.items(), key=lambda x: x[1]['count'], reverse=True)

    for reason_key, data in sorted_reasons:
        count = data['count']
        detail = data['detail']
        lenders = data['lenders'][:3]  # Show first 3 lenders

        if count == len(failed_results):
            reasons_list.append(f"❌ {detail} (All lenders)")
        else:
            lender_str = ', '.join(lenders)
            if count > 3:
                lender_str += f" and {count - 3} more"
            reasons_list.append(f"❌ {detail} ({lender_str})")

        # Generate suggested actions
        if reason_key == "cibil_score":
            if borrower.cibil_score:
                target = extract_number_from_string(detail)
                if target and target > borrower.cibil_score:
                    actions_set.add(f"💡 Improve CIBIL score to {target}+ (currently {borrower.cibil_score})")
                else:
                    actions_set.add("💡 Improve CIBIL score above 700")
            else:
                actions_set.add("💡 Get CIBIL report and work on improving credit score")

        elif reason_key == "vintage":
            if borrower.business_vintage_years:
                target = extract_number_from_string(detail)
                if target and target > borrower.business_vintage_years:
                    gap = target - borrower.business_vintage_years
                    actions_set.add(f"💡 Business needs {gap:.1f} more years of operation (currently {borrower.business_vintage_years:.1f}y)")
            else:
                actions_set.add("💡 Establish business for minimum 2-3 years before applying")

        elif reason_key == "turnover":
            if borrower.annual_turnover:
                target = extract_number_from_string(detail)
                if target and target > borrower.annual_turnover:
                    actions_set.add(f"💡 Increase annual turnover to ₹{target}L+ (currently ₹{borrower.annual_turnover}L)")
            else:
                actions_set.add("💡 Work on increasing business revenue/turnover")

        elif reason_key == "entity_type":
            actions_set.add("💡 Consider changing entity structure or target lenders accepting your entity type")

        elif reason_key == "pincode":
            actions_set.add("💡 Expand business to serviceable locations or check with local lenders")

        elif reason_key == "age":
            actions_set.add("💡 Wait until you meet the age requirement for lenders")

    # Add general suggestions if applicable
    if borrower.feature_completeness < 80:
        actions_set.add("📄 Upload missing documents (CIBIL, bank statements, GST) for better matching")

    if not borrower.cibil_score:
        actions_set.add("📊 Get CIBIL report - this is critical for eligibility")

    if not borrower.business_vintage_years:
        actions_set.add("🏢 Provide GST certificate or business registration proof")

    return reasons_list, list(actions_set)


def generate_dynamic_recommendations(
    borrower: BorrowerFeatureVector,
    all_results: List[EligibilityResult]
) -> List[Dict[str, Any]]:
    """Generate dynamic prioritized recommendations based on rejection analysis.

    Analyzes ALL lenders (not just failures) to determine which improvements
    would unlock the most lenders.

    Args:
        borrower: The borrower feature vector
        all_results: List of ALL eligibility results (passed + failed)

    Returns:
        List of recommendations sorted by impact (highest first)
    """
    failed_results = [r for r in all_results if r.hard_filter_status == HardFilterStatus.FAIL]

    if not failed_results:
        return []

    # Count rejection reasons and track targets
    rejection_analysis = {}

    for result in failed_results:
        for reason_key, reason_detail in result.hard_filter_details.items():
            if reason_key not in rejection_analysis:
                rejection_analysis[reason_key] = {
                    'count': 0,
                    'lenders': [],
                    'targets': [],
                    'detail': reason_detail
                }
            rejection_analysis[reason_key]['count'] += 1
            rejection_analysis[reason_key]['lenders'].append(result.lender_name)

            # Extract target value from detail string
            target_val = extract_number_from_string(reason_detail)
            if target_val:
                rejection_analysis[reason_key]['targets'].append(target_val)

    # Build prioritized recommendations
    recommendations = []

    for reason_key, data in rejection_analysis.items():
        count = data['count']
        lenders = data['lenders']
        targets = data['targets']

        recommendation = {
            'priority': count,  # Higher count = higher priority
            'issue': '',
            'current': None,
            'target': None,
            'impact': f"Would unlock {count} more lender{'s' if count > 1 else ''}",
            'action': '',
            'lenders_affected': lenders[:5]  # Show first 5
        }

        # Generate specific recommendation based on reason
        if reason_key == "cibil_score":
            recommendation['issue'] = "CIBIL Score Too Low"
            recommendation['current'] = borrower.cibil_score if borrower.cibil_score else "Not available"
            # Use most common target or max target
            recommendation['target'] = max(targets) if targets else 700
            recommendation['action'] = "Pay off existing dues, reduce credit utilization, dispute errors on credit report"

        elif reason_key == "vintage":
            recommendation['issue'] = "Business Vintage Below Requirement"
            recommendation['current'] = f"{borrower.business_vintage_years:.1f} years" if borrower.business_vintage_years else "Not available"
            recommendation['target'] = f"{max(targets):.1f} years" if targets else "3 years"
            recommendation['action'] = "Wait for business to reach minimum vintage or provide older business registration documents"

        elif reason_key == "turnover":
            recommendation['issue'] = "Annual Turnover Below Requirement"
            recommendation['current'] = f"₹{borrower.annual_turnover}L" if borrower.annual_turnover else "Not available"
            recommendation['target'] = f"₹{max(targets)}L" if targets else "₹15L"
            recommendation['action'] = "Grow business revenue, consolidate turnover from multiple entities, or provide ITR showing higher income"

        elif reason_key == "abb":
            recommendation['issue'] = "Average Bank Balance Too Low"
            recommendation['current'] = f"₹{borrower.avg_monthly_balance:,.0f}" if borrower.avg_monthly_balance else "Not available"
            recommendation['target'] = f"₹{max(targets):,.0f}" if targets else "₹100,000"
            recommendation['action'] = "Maintain higher minimum balance, reduce unnecessary outflows, consolidate funds from multiple accounts"

        elif reason_key == "entity_type":
            recommendation['issue'] = "Entity Type Not Accepted"
            recommendation['current'] = borrower.entity_type.value if borrower.entity_type else "Not available"
            recommendation['target'] = "Proprietorship, Partnership, or Pvt Ltd"
            recommendation['action'] = "Consider restructuring business entity or target lenders that accept your entity type"

        elif reason_key == "pincode":
            recommendation['issue'] = "Location Not Serviceable"
            recommendation['current'] = borrower.pincode if borrower.pincode else "Not available"
            recommendation['target'] = "Serviceable location"
            recommendation['action'] = "Expand business to metro cities, register office in serviceable pincode, or check regional lenders"

        elif reason_key == "age":
            age = calculate_age(borrower.dob) if borrower.dob else None
            recommendation['issue'] = "Age Outside Accepted Range"
            recommendation['current'] = f"{age} years" if age else "Not available"
            recommendation['target'] = "21-65 years"
            recommendation['action'] = "Wait until you meet age requirement or apply through co-applicant/guarantor"

        else:
            # Generic recommendation for unknown reason
            recommendation['issue'] = reason_key.replace('_', ' ').title()
            recommendation['action'] = f"Address: {data['detail']}"

        recommendations.append(recommendation)

    # Sort by priority (count) descending
    recommendations.sort(key=lambda x: x['priority'], reverse=True)

    # Add priority rank (1, 2, 3...)
    for idx, rec in enumerate(recommendations, 1):
        rec['priority_rank'] = idx

    return recommendations


def extract_number_from_string(text: str) -> Optional[float]:
    """Extract first number from string like '750 < required 700'."""
    import re
    matches = re.findall(r'(\d+\.?\d*)', text)
    if len(matches) >= 2:
        # Usually format is "actual < required target", so target is second number
        try:
            return float(matches[1])
        except:
            return None
    return None


# ═══════════════════════════════════════════════════════════════
# DATABASE PERSISTENCE
# ═══════════════════════════════════════════════════════════════

async def save_eligibility_results(
    case_id: UUID,
    results: List[EligibilityResult]
) -> None:
    """Save eligibility results to the database.

    Args:
        case_id: The case UUID
        results: List of eligibility results to save
    """
    async with get_db_session() as db:
        # Delete existing results for this case
        await db.execute(
            "DELETE FROM eligibility_results WHERE case_id = $1",
            case_id
        )

        # Insert new results
        for result in results:
            # Get lender_product_id from lender name and product name
            lp_row = await db.fetchrow(
                """
                SELECT lp.id
                FROM lender_products lp
                INNER JOIN lenders l ON lp.lender_id = l.id
                WHERE LOWER(l.lender_name) = LOWER($1)
                  AND LOWER(lp.product_name) = LOWER($2)
                LIMIT 1
                """,
                result.lender_name,
                result.product_name
            )

            if not lp_row:
                logger.warning(
                    f"Could not find lender_product for {result.lender_name} - {result.product_name}"
                )
                continue

            lender_product_id = lp_row['id']

            # Convert missing_for_improvement to JSON
            import json
            missing_json = json.dumps(result.missing_for_improvement)
            hard_details_json = json.dumps(result.hard_filter_details)

            # Insert result
            await db.execute(
                """
                INSERT INTO eligibility_results (
                    case_id,
                    lender_product_id,
                    hard_filter_status,
                    hard_filter_details,
                    eligibility_score,
                    approval_probability,
                    expected_ticket_min,
                    expected_ticket_max,
                    confidence,
                    missing_for_improvement,
                    rank
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
                """,
                case_id,
                lender_product_id,
                result.hard_filter_status.value,
                hard_details_json,
                result.eligibility_score,
                result.approval_probability.value if result.approval_probability else None,
                result.expected_ticket_min,
                result.expected_ticket_max,
                result.confidence,
                missing_json,
                result.rank
            )

        logger.info(f"Saved {len(results)} eligibility results for case {case_id}")


async def load_eligibility_results(case_id: UUID) -> Optional[EligibilityResponse]:
    """Load eligibility results from the database.

    Args:
        case_id: The case UUID

    Returns:
        EligibilityResponse or None if not found
    """
    async with get_db_session() as db:
        # Get case_id string
        case_row = await db.fetchrow(
            "SELECT case_id FROM cases WHERE id = $1",
            case_id
        )

        if not case_row:
            return None

        case_id_str = case_row['case_id']

        # Get results
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

        if not rows:
            return None

        # Convert rows to EligibilityResult objects
        results = []
        passed_count = 0

        for row in rows:
            import json

            hard_status = HardFilterStatus(row['hard_filter_status'])
            if hard_status == HardFilterStatus.PASS:
                passed_count += 1

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

        return EligibilityResponse(
            case_id=case_id_str,
            total_lenders_evaluated=len(results),
            lenders_passed=passed_count,
            results=results,
            dynamic_recommendations=[]  # Will be empty for loaded results, only computed on fresh scoring
        )
