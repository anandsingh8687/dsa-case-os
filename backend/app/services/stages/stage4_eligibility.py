"""Stage 4: Eligibility Matching Engine

Matches borrower feature vectors against lender product rules to produce ranked eligibility results.

Architecture:
- Layer 1: Hard Filters (Pass/Fail) - eliminates ineligible lenders
- Layer 2: Weighted Scoring (0-100) - scores eligible lenders
- Layer 3: Ranking & Output - sorts and formats results
"""

import logging
import re
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

ENTITY_EQUIVALENCE_MAP = {
    "proprietorship": {"proprietorship", "proprietor", "sole_proprietorship", "individual", "self_employed", "self_employed_non_professional"},
    "partnership": {"partnership", "partnership_firm", "firm"},
    "llp": {"llp", "limited_liability_partnership"},
    "pvt_ltd": {"pvt_ltd", "private_limited", "private_limited_company", "opc", "one_person_company", "company"},
    "public_ltd": {"public_ltd", "public_limited", "public_limited_company"},
    "trust": {"trust"},
    "society": {"society", "ngo"},
    "huf": {"huf"},
}

PRODUCT_TERMS_FALLBACKS = {
    "bl": {
        "interest_rate_range": "14% - 30%",
        "processing_fee_pct": 2.0,
        "expected_tat_days": 5,
        "tenor_min_months": 12,
        "tenor_max_months": 48,
    },
    "stbl": {
        "interest_rate_range": "13% - 26%",
        "processing_fee_pct": 1.5,
        "expected_tat_days": 4,
        "tenor_min_months": 12,
        "tenor_max_months": 60,
    },
    "sbl": {
        "interest_rate_range": "15% - 28%",
        "processing_fee_pct": 2.0,
        "expected_tat_days": 4,
        "tenor_min_months": 12,
        "tenor_max_months": 60,
    },
    "mtbl": {
        "interest_rate_range": "15% - 30%",
        "processing_fee_pct": 2.5,
        "expected_tat_days": 5,
        "tenor_min_months": 12,
        "tenor_max_months": 60,
    },
    "htbl": {
        "interest_rate_range": "10% - 16%",
        "processing_fee_pct": 1.0,
        "expected_tat_days": 7,
        "tenor_min_months": 60,
        "tenor_max_months": 300,
    },
    "pl": {
        "interest_rate_range": "11% - 28%",
        "processing_fee_pct": 2.0,
        "expected_tat_days": 3,
        "tenor_min_months": 12,
        "tenor_max_months": 60,
    },
    "hl": {
        "interest_rate_range": "8.5% - 11.5%",
        "processing_fee_pct": 0.5,
        "expected_tat_days": 10,
        "tenor_min_months": 60,
        "tenor_max_months": 360,
    },
    "lap": {
        "interest_rate_range": "10.5% - 16%",
        "processing_fee_pct": 1.0,
        "expected_tat_days": 8,
        "tenor_min_months": 36,
        "tenor_max_months": 180,
    },
    "od": {
        "interest_rate_range": "11% - 18%",
        "processing_fee_pct": 1.0,
        "expected_tat_days": 3,
        "tenor_min_months": 12,
        "tenor_max_months": 36,
    },
    "cc": {
        "interest_rate_range": "11% - 17%",
        "processing_fee_pct": 1.0,
        "expected_tat_days": 3,
        "tenor_min_months": 12,
        "tenor_max_months": 36,
    },
    "digital": {
        "interest_rate_range": "16% - 36%",
        "processing_fee_pct": 2.5,
        "expected_tat_days": 2,
        "tenor_min_months": 3,
        "tenor_max_months": 36,
    },
    "default": {
        "interest_rate_range": "12% - 24%",
        "processing_fee_pct": 1.5,
        "expected_tat_days": 5,
        "tenor_min_months": 12,
        "tenor_max_months": 60,
    },
}

LENDER_TERMS_OVERRIDES = {
    "arthmate": {"interest_rate_range": "18% - 30%", "processing_fee_pct": 2.5, "expected_tat_days": 3},
    "abfl": {"interest_rate_range": "14% - 26%", "processing_fee_pct": 2.0, "expected_tat_days": 5},
    "bajaj": {"interest_rate_range": "13% - 30%", "processing_fee_pct": 2.0, "expected_tat_days": 3},
    "clix": {"interest_rate_range": "14% - 30%", "processing_fee_pct": 2.5, "expected_tat_days": 4},
    "credit saison": {"interest_rate_range": "16% - 28%", "processing_fee_pct": 2.0, "expected_tat_days": 5},
    "godrej": {"interest_rate_range": "13% - 24%", "processing_fee_pct": 1.5, "expected_tat_days": 4},
    "iifl": {"interest_rate_range": "14% - 28%", "processing_fee_pct": 2.0, "expected_tat_days": 4},
    "indifi": {"interest_rate_range": "16% - 30%", "processing_fee_pct": 2.5, "expected_tat_days": 3},
    "lendingkart": {"interest_rate_range": "18% - 36%", "processing_fee_pct": 2.5, "expected_tat_days": 2},
    "neogrowth": {"interest_rate_range": "16% - 30%", "processing_fee_pct": 2.5, "expected_tat_days": 2},
    "protium": {"interest_rate_range": "14% - 28%", "processing_fee_pct": 2.0, "expected_tat_days": 4},
    "tata": {"interest_rate_range": "12% - 28%", "processing_fee_pct": 2.0, "expected_tat_days": 3},
    "ambit": {"interest_rate_range": "14% - 26%", "processing_fee_pct": 2.0, "expected_tat_days": 5},
    "flexiloans": {"interest_rate_range": "18% - 34%", "processing_fee_pct": 2.5, "expected_tat_days": 2},
}


def _normalize_entity_value(value: Optional[str]) -> str:
    if value is None:
        return ""
    normalized = str(value).strip().lower()
    normalized = normalized.replace("&", "and")
    normalized = re.sub(r"[^a-z0-9]+", "_", normalized)
    normalized = re.sub(r"_+", "_", normalized).strip("_")
    return normalized


def _entity_variants(value: Optional[str]) -> set[str]:
    normalized = _normalize_entity_value(value)
    if not normalized:
        return set()
    variants = {normalized}
    for canonical, aliases in ENTITY_EQUIVALENCE_MAP.items():
        if normalized == canonical or normalized in aliases:
            variants.add(canonical)
            variants.update(aliases)
    return variants


def _resolve_product_terms_bucket(product_name: Optional[str]) -> str:
    normalized = (product_name or "").strip().lower()
    for key in (
        "stbl",
        "htbl",
        "mtbl",
        "sbl",
        "bl",
        "pl",
        "hl",
        "lap",
        "od",
        "cc",
        "digital",
    ):
        if key in normalized:
            return key
    return "default"


def _build_lender_terms(
    lender_name: Optional[str],
    product_name: Optional[str],
    existing_terms: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Fill lender terms with resilient fallback values when policy columns are sparse."""
    terms = dict(existing_terms or {})
    product_terms = PRODUCT_TERMS_FALLBACKS.get(
        _resolve_product_terms_bucket(product_name),
        PRODUCT_TERMS_FALLBACKS["default"],
    )

    lender_key = (lender_name or "").strip().lower()
    lender_overrides: Dict[str, Any] = {}
    for token, value in LENDER_TERMS_OVERRIDES.items():
        if token in lender_key:
            lender_overrides = value
            break

    if not terms.get("interest_rate_range"):
        terms["interest_rate_range"] = lender_overrides.get("interest_rate_range") or product_terms["interest_rate_range"]
    if terms.get("processing_fee_pct") is None:
        terms["processing_fee_pct"] = lender_overrides.get("processing_fee_pct", product_terms["processing_fee_pct"])
    if terms.get("expected_tat_days") is None:
        terms["expected_tat_days"] = lender_overrides.get("expected_tat_days", product_terms["expected_tat_days"])

    min_tenor = terms.get("tenor_min_months")
    max_tenor = terms.get("tenor_max_months")
    if min_tenor is None:
        min_tenor = product_terms["tenor_min_months"]
    if max_tenor is None:
        max_tenor = product_terms["tenor_max_months"]
    if min_tenor and max_tenor and min_tenor > max_tenor:
        min_tenor, max_tenor = max_tenor, min_tenor

    terms["tenor_min_months"] = min_tenor
    terms["tenor_max_months"] = max_tenor
    return terms


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
        borrower_entity = borrower.entity_type.value if isinstance(borrower.entity_type, EntityType) else str(borrower.entity_type)
        borrower_variants = _entity_variants(borrower_entity)

        eligible_variants = set()
        for raw_type in lender.eligible_entity_types:
            eligible_variants.update(_entity_variants(raw_type))

        if borrower_variants.isdisjoint(eligible_variants):
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
    age_min = lender.age_min
    age_max = lender.age_max
    if age_min is not None and age_max is not None:
        if age_min > age_max:
            age_min, age_max = age_max, age_min
        if age_min == age_max:
            # Defensive normalization for malformed policy rows like "60-60".
            if age_min >= 45:
                age_min = None
            else:
                age_max = None

    if borrower.dob and (age_min is not None or age_max is not None):
        age = calculate_age(borrower.dob)
        if age_min is not None and age < age_min:
            failures["age"] = (
                f"Age {age} outside minimum {age_min}"
            )
        elif age_max is not None and age > age_max:
            failures["age"] = (
                f"Age {age} outside maximum {age_max}"
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

    score, _ = calculate_eligibility_score_with_breakdown(borrower, lender)
    return score


def calculate_eligibility_score_with_breakdown(
    borrower: BorrowerFeatureVector,
    lender: LenderProductRule
) -> Tuple[float, List[Dict[str, Any]]]:
    """Calculate score and return component-level breakdown for explainability."""
    components: List[Dict[str, Any]] = []

    def add_component(component_key: str, label: str, weight: int, raw_score: Optional[float], note: str):
        if raw_score is None:
            return
        components.append({
            "component": component_key,
            "label": label,
            "weight": weight,
            "score": round(float(raw_score), 2),
            "weighted_contribution": round((float(raw_score) * weight) / 100.0, 2),
            "note": note,
        })

    # Component 1: CIBIL Band (25%)
    cibil_score = score_cibil_band(borrower.cibil_score)
    add_component(
        "cibil_band",
        "CIBIL Band",
        25,
        cibil_score,
        f"CIBIL considered: {borrower.cibil_score if borrower.cibil_score is not None else 'N/A'}",
    )

    # Component 2: Turnover Band (20%)
    turnover_score = score_turnover_band(borrower.annual_turnover, lender.min_turnover_annual)
    add_component(
        "turnover_band",
        "Turnover Band",
        20,
        turnover_score,
        f"Annual turnover: {borrower.annual_turnover if borrower.annual_turnover is not None else 'N/A'}",
    )

    # Component 3: Business Vintage (15%)
    vintage_score = score_business_vintage(borrower.business_vintage_years)
    add_component(
        "business_vintage",
        "Business Vintage",
        15,
        vintage_score,
        f"Vintage (years): {borrower.business_vintage_years if borrower.business_vintage_years is not None else 'N/A'}",
    )

    # Component 4: Banking Strength (20%)
    banking_score = score_banking_strength(
        borrower.avg_monthly_balance,
        borrower.bounce_count_12m,
        borrower.cash_deposit_ratio,
        lender.min_abb
    )
    add_component(
        "banking_strength",
        "Banking Strength",
        20,
        banking_score,
        "Based on average balance, bounce count, and cash deposit ratio",
    )

    # Component 5: FOIR (10%)
    foir_score = score_foir(borrower.emi_outflow_monthly, borrower.monthly_credit_avg)
    add_component(
        "foir",
        "FOIR",
        10,
        foir_score,
        "Fixed obligations vs monthly inflow",
    )

    # Component 6: Documentation (10%)
    doc_score = score_documentation(borrower, lender)
    add_component(
        "documentation",
        "Documentation",
        10,
        doc_score,
        "Required document coverage for this lender",
    )

    if not components:
        return 0.0, []

    total_weight = sum(item["weight"] for item in components)
    weighted_sum = sum(item["score"] * item["weight"] for item in components)
    final_score = round(weighted_sum / total_weight, 2)

    return final_score, components


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
            score, score_breakdown = calculate_eligibility_score_with_breakdown(borrower, lender)

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
                hard_filter_details={
                    "score_breakdown": score_breakdown,
                    "matched_signals": [
                        f"Entity type: {borrower.entity_type.value if isinstance(borrower.entity_type, EntityType) else (borrower.entity_type or 'N/A')}",
                        f"CIBIL: {borrower.cibil_score if borrower.cibil_score is not None else 'N/A'}",
                        f"Business vintage: {borrower.business_vintage_years if borrower.business_vintage_years is not None else 'N/A'} years",
                        f"Pincode: {borrower.pincode or 'N/A'}",
                    ],
                    "lender_thresholds": {
                        "min_cibil_score": lender.min_cibil_score,
                        "min_vintage_years": lender.min_vintage_years,
                        "min_turnover_annual": lender.min_turnover_annual,
                        "max_ticket_size": lender.max_ticket_size,
                        "min_abb": lender.min_abb,
                    },
                    "lender_terms": {
                        **_build_lender_terms(
                            lender_name=lender.lender_name,
                            product_name=lender.product_name,
                            existing_terms={
                                "interest_rate_range": lender.interest_rate_range,
                                "processing_fee_pct": lender.processing_fee_pct,
                                "expected_tat_days": lender.expected_tat_days,
                                "tenor_min_months": lender.tenor_min_months,
                                "tenor_max_months": lender.tenor_max_months,
                            },
                        )
                    },
                },
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


def _build_default_matched_signals(
    borrower: Optional[BorrowerFeatureVector],
    score: Optional[float],
) -> List[str]:
    """Build resilient lender-match explanations when legacy rows lack details."""
    if not borrower:
        if score is not None:
            return [f"Composite eligibility score: {round(float(score))}/100."]
        return ["All hard filters satisfied for this lender profile."]

    entity = borrower.entity_type.value if isinstance(borrower.entity_type, EntityType) else borrower.entity_type
    signals = []
    if entity:
        signals.append(f"Entity type accepted: {entity}")
    if borrower.cibil_score is not None:
        signals.append(f"CIBIL within lender threshold: {borrower.cibil_score}")
    if borrower.business_vintage_years is not None:
        signals.append(f"Business vintage considered: {borrower.business_vintage_years} years")
    if borrower.annual_turnover is not None:
        signals.append(f"Annual turnover considered: ₹{borrower.annual_turnover}L")
    if borrower.pincode:
        signals.append(f"Pincode serviceability passed: {borrower.pincode}")
    if score is not None:
        signals.append(f"Composite eligibility score: {round(float(score))}/100")

    return signals[:6] if signals else ["All hard filters satisfied for this lender profile."]


def _normalize_pass_result_details(
    result: EligibilityResult,
    borrower: Optional[BorrowerFeatureVector] = None,
) -> EligibilityResult:
    """Ensure matched lenders always have explainability-safe payload keys."""
    details = result.hard_filter_details if isinstance(result.hard_filter_details, dict) else {}
    matched_signals = details.get("matched_signals")

    if not isinstance(matched_signals, list) or len(matched_signals) == 0:
        details["matched_signals"] = _build_default_matched_signals(
            borrower=borrower,
            score=result.eligibility_score,
        )

    if not isinstance(details.get("score_breakdown"), list):
        details["score_breakdown"] = []
    if not isinstance(details.get("lender_thresholds"), dict):
        details["lender_thresholds"] = {}
    if not isinstance(details.get("lender_terms"), dict):
        details["lender_terms"] = {}
    details["lender_terms"] = _build_lender_terms(
        lender_name=result.lender_name,
        product_name=result.product_name,
        existing_terms=details.get("lender_terms"),
    )

    result.hard_filter_details = details
    return result


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
        case_row = await db.fetchrow("SELECT organization_id FROM cases WHERE id = $1", case_id)
        organization_id = case_row["organization_id"] if case_row else None

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
                    organization_id,
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
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
                """,
                case_id,
                organization_id,
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

        borrower: Optional[BorrowerFeatureVector] = None
        borrower_row = await db.fetchrow(
            """
            SELECT
                full_name, pan_number, aadhaar_number, dob,
                entity_type, business_vintage_years, gstin, industry_type, pincode,
                annual_turnover, avg_monthly_balance, monthly_credit_avg, monthly_turnover,
                emi_outflow_monthly, bounce_count_12m, cash_deposit_ratio, itr_total_income,
                cibil_score, active_loan_count, overdue_count, enquiry_count_6m,
                feature_completeness
            FROM borrower_features
            WHERE case_id = $1
            """,
            case_id
        )
        if borrower_row:
            try:
                borrower = BorrowerFeatureVector(**dict(borrower_row))
            except Exception as e:
                logger.warning(f"Could not load borrower vector for explainability fallback {case_id_str}: {e}")

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
            if hard_status == HardFilterStatus.PASS:
                result = _normalize_pass_result_details(result, borrower=borrower)
            results.append(result)

        rejection_reasons: List[str] = []
        suggested_actions: List[str] = []
        dynamic_recommendations: List[Dict[str, Any]] = []

        # Re-compute advisory blocks on load so UI can always explain results.
        if borrower:
            try:
                failed_results = [r for r in results if r.hard_filter_status == HardFilterStatus.FAIL]

                if passed_count == 0 and failed_results:
                    rejection_reasons, suggested_actions = generate_rejection_analysis(
                        borrower,
                        failed_results
                    )

                dynamic_recommendations = generate_dynamic_recommendations(
                    borrower,
                    results
                )
            except Exception as e:
                logger.warning(f"Could not recompute advisory blocks for case {case_id_str}: {e}")

        return EligibilityResponse(
            case_id=case_id_str,
            total_lenders_evaluated=len(results),
            lenders_passed=passed_count,
            results=results,
            rejection_reasons=rejection_reasons,
            suggested_actions=suggested_actions,
            dynamic_recommendations=dynamic_recommendations
        )
