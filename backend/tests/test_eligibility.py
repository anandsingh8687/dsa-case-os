"""Tests for Stage 4: Eligibility Matching Engine

Tests cover:
1. Hard filter logic with real lender rules
2. Weighted scoring components
3. Ranking and probability assignment
4. End-to-end eligibility matching
5. Edge cases and data quality scenarios
"""

import pytest
from datetime import date, timedelta
from typing import List

from app.schemas.shared import (
    BorrowerFeatureVector,
    LenderProductRule,
    EligibilityResult,
    EligibilityResponse,
)
from app.core.enums import (
    HardFilterStatus,
    ApprovalProbability,
    EntityType,
    ProgramType,
)
from app.services.stages.stage4_eligibility import (
    apply_hard_filters,
    calculate_eligibility_score,
    score_cibil_band,
    score_turnover_band,
    score_business_vintage,
    score_banking_strength,
    score_foir,
    score_documentation,
    determine_approval_probability,
    calculate_ticket_range,
    rank_results,
    calculate_age,
)


# ═══════════════════════════════════════════════════════════════
# FIXTURES: REAL LENDER RULES
# ═══════════════════════════════════════════════════════════════

@pytest.fixture
def bajaj_stbl() -> LenderProductRule:
    """Bajaj STBL - Real lender rule from policy CSV."""
    return LenderProductRule(
        lender_name="Bajaj",
        product_name="STBL",
        program_type=ProgramType.BANKING,
        min_vintage_years=1.0,
        min_cibil_score=685,
        min_turnover_annual=10.0,  # 10L
        max_ticket_size=3.0,  # 3L
        min_abb=8000.0,
        eligible_entity_types=["Proprietorship", "Partnership", "LLP", "Pvt Ltd"],
        age_min=21,
        age_max=65,
        no_30plus_dpd_months=12,
        banking_months_required=6,
        gst_required=True,
        policy_available=True,
        serviceable_pincodes_count=15000
    )


@pytest.fixture
def indifi_bl() -> LenderProductRule:
    """Indifi BL - Higher ticket, stricter requirements."""
    return LenderProductRule(
        lender_name="Indifi",
        product_name="BL",
        program_type=ProgramType.BANKING,
        min_vintage_years=2.0,
        min_cibil_score=700,
        min_turnover_annual=30.0,  # 30L
        max_ticket_size=10.0,  # 10L
        min_abb=15000.0,
        eligible_entity_types=["Partnership", "LLP", "Pvt Ltd"],
        age_min=25,
        age_max=65,
        no_30plus_dpd_months=12,
        banking_months_required=12,
        gst_required=True,
        ownership_proof_required=True,
        policy_available=True,
        serviceable_pincodes_count=8000
    )


@pytest.fixture
def lendingkart_bl() -> LenderProductRule:
    """Lendingkart BL - Mid-tier requirements."""
    return LenderProductRule(
        lender_name="Lendingkart",
        product_name="BL",
        program_type=ProgramType.HYBRID,
        min_vintage_years=1.5,
        min_cibil_score=650,
        min_turnover_annual=15.0,  # 15L
        max_ticket_size=5.0,  # 5L
        min_abb=10000.0,
        eligible_entity_types=["Proprietorship", "Partnership", "LLP", "Pvt Ltd"],
        age_min=21,
        age_max=70,
        no_30plus_dpd_months=6,
        banking_months_required=6,
        gst_required=False,
        policy_available=True,
        serviceable_pincodes_count=12000
    )


@pytest.fixture
def no_policy_lender() -> LenderProductRule:
    """Lender with no policy available - should be filtered out."""
    return LenderProductRule(
        lender_name="NoPolicy Bank",
        product_name="BL",
        program_type=ProgramType.BANKING,
        min_vintage_years=1.0,
        min_cibil_score=650,
        policy_available=False,
        serviceable_pincodes_count=0
    )


# ═══════════════════════════════════════════════════════════════
# FIXTURES: BORROWER PROFILES
# ═══════════════════════════════════════════════════════════════

@pytest.fixture
def strong_borrower() -> BorrowerFeatureVector:
    """Strong borrower - should match most lenders with high scores."""
    return BorrowerFeatureVector(
        full_name="Strong Business Owner",
        pan_number="ABCDE1234F",
        aadhaar_number="123456789012",
        dob=date(1985, 6, 15),  # 40 years old
        entity_type=EntityType.LLP,
        business_vintage_years=5.0,
        gstin="27AABCU9603R1ZM",
        industry_type="Manufacturing",
        pincode="400001",
        annual_turnover=50.0,  # 50L
        avg_monthly_balance=25000.0,
        monthly_credit_avg=8.0,  # 8L/month
        emi_outflow_monthly=1.5,  # 1.5L/month
        bounce_count_12m=0,
        cash_deposit_ratio=0.15,  # 15%
        itr_total_income=45.0,
        cibil_score=750,
        active_loan_count=2,
        overdue_count=0,
        enquiry_count_6m=1,
        feature_completeness=95.0
    )


@pytest.fixture
def weak_borrower() -> BorrowerFeatureVector:
    """Weak borrower - should match few lenders with low scores."""
    return BorrowerFeatureVector(
        full_name="Weak Business Owner",
        pan_number="XYZAB5678G",
        dob=date(1995, 3, 20),  # 30 years old
        entity_type=EntityType.PROPRIETORSHIP,
        business_vintage_years=0.5,  # 6 months
        pincode="400002",
        annual_turnover=5.0,  # 5L
        avg_monthly_balance=5000.0,
        monthly_credit_avg=0.8,  # 80k/month
        emi_outflow_monthly=0.5,  # 50k/month
        bounce_count_12m=3,
        cash_deposit_ratio=0.50,  # 50%
        cibil_score=620,
        active_loan_count=1,
        overdue_count=1,
        enquiry_count_6m=5,
        feature_completeness=60.0
    )


@pytest.fixture
def mid_tier_borrower() -> BorrowerFeatureVector:
    """Mid-tier borrower - should match some lenders with medium scores."""
    return BorrowerFeatureVector(
        full_name="Mid Tier Business Owner",
        pan_number="PQRST9876H",
        aadhaar_number="987654321098",
        dob=date(1988, 9, 10),  # 37 years old
        entity_type=EntityType.PARTNERSHIP,
        business_vintage_years=2.5,
        gstin="29AABCU9603R1ZM",
        industry_type="Trading",
        pincode="400003",
        annual_turnover=20.0,  # 20L
        avg_monthly_balance=12000.0,
        monthly_credit_avg=3.0,  # 3L/month
        emi_outflow_monthly=0.9,  # 90k/month
        bounce_count_12m=1,
        cash_deposit_ratio=0.25,  # 25%
        itr_total_income=18.0,
        cibil_score=690,
        active_loan_count=1,
        overdue_count=0,
        enquiry_count_6m=2,
        feature_completeness=80.0
    )


# ═══════════════════════════════════════════════════════════════
# TEST: HARD FILTERS
# ═══════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_hard_filter_no_policy(strong_borrower, no_policy_lender):
    """Test that lenders with no policy are filtered out."""
    status, details = await apply_hard_filters(strong_borrower, no_policy_lender)

    assert status == HardFilterStatus.FAIL
    assert "policy_available" in details


@pytest.mark.asyncio
async def test_hard_filter_cibil_pass(strong_borrower, bajaj_stbl):
    """Test CIBIL filter passes when score meets requirement."""
    # Strong borrower has CIBIL 750, Bajaj needs 685
    status, details = await apply_hard_filters(strong_borrower, bajaj_stbl)

    # Should pass (assuming pincode check passes - mocked in real scenario)
    # For unit test, we're checking the CIBIL logic specifically
    assert "cibil_score" not in details  # No CIBIL failure


@pytest.mark.asyncio
async def test_hard_filter_cibil_fail(weak_borrower, bajaj_stbl):
    """Test CIBIL filter fails when score below requirement."""
    # Weak borrower has CIBIL 620, Bajaj needs 685
    status, details = await apply_hard_filters(weak_borrower, bajaj_stbl)

    assert status == HardFilterStatus.FAIL
    assert "cibil_score" in details
    assert "620" in details["cibil_score"]


@pytest.mark.asyncio
async def test_hard_filter_entity_type_pass(strong_borrower, bajaj_stbl):
    """Test entity type filter passes when borrower's type is eligible."""
    # Strong borrower is LLP, Bajaj accepts LLP
    status, details = await apply_hard_filters(strong_borrower, bajaj_stbl)

    assert "entity_type" not in details


@pytest.mark.asyncio
async def test_hard_filter_entity_type_fail(strong_borrower, indifi_bl):
    """Test entity type filter fails when borrower's type not eligible."""
    # Create a proprietorship borrower
    proprietor = BorrowerFeatureVector(
        **{**strong_borrower.dict(), "entity_type": EntityType.PROPRIETORSHIP}
    )

    # Indifi BL only accepts Partnership, LLP, Pvt Ltd (not Proprietorship)
    status, details = await apply_hard_filters(proprietor, indifi_bl)

    assert status == HardFilterStatus.FAIL
    assert "entity_type" in details


@pytest.mark.asyncio
async def test_hard_filter_vintage_fail(weak_borrower, indifi_bl):
    """Test vintage filter fails when borrower is too new."""
    # Weak borrower has 0.5 years, Indifi needs 2 years
    status, details = await apply_hard_filters(weak_borrower, indifi_bl)

    assert status == HardFilterStatus.FAIL
    assert "vintage" in details


@pytest.mark.asyncio
async def test_hard_filter_turnover_fail(weak_borrower, indifi_bl):
    """Test turnover filter fails when borrower's turnover too low."""
    # Weak borrower has 5L, Indifi needs 30L
    status, details = await apply_hard_filters(weak_borrower, indifi_bl)

    assert status == HardFilterStatus.FAIL
    assert "turnover" in details


@pytest.mark.asyncio
async def test_hard_filter_age_calculation():
    """Test age calculation from DOB."""
    # DOB 40 years ago
    dob = date.today() - timedelta(days=40*365)
    age = calculate_age(dob)

    assert age >= 39 and age <= 40  # Account for leap years


@pytest.mark.asyncio
async def test_hard_filter_abb_fail(weak_borrower, indifi_bl):
    """Test ABB filter fails when average balance too low."""
    # Weak borrower has 5000, Indifi needs 15000
    status, details = await apply_hard_filters(weak_borrower, indifi_bl)

    assert status == HardFilterStatus.FAIL
    assert "abb" in details


# ═══════════════════════════════════════════════════════════════
# TEST: SCORING COMPONENTS
# ═══════════════════════════════════════════════════════════════

def test_score_cibil_band():
    """Test CIBIL scoring bands."""
    assert score_cibil_band(760) == 100.0
    assert score_cibil_band(750) == 100.0
    assert score_cibil_band(730) == 90.0
    assert score_cibil_band(710) == 75.0
    assert score_cibil_band(680) == 60.0
    assert score_cibil_band(660) == 40.0
    assert score_cibil_band(640) == 20.0
    assert score_cibil_band(None) is None


def test_score_turnover_band():
    """Test turnover scoring based on ratio."""
    # 30L turnover, 10L minimum
    assert score_turnover_band(30.0, 10.0) == 100.0  # 3x
    assert score_turnover_band(25.0, 10.0) == 80.0   # 2.5x
    assert score_turnover_band(17.0, 10.0) == 60.0   # 1.7x
    assert score_turnover_band(12.0, 10.0) == 40.0   # 1.2x
    assert score_turnover_band(8.0, 10.0) == 20.0    # 0.8x
    assert score_turnover_band(None, 10.0) is None


def test_score_business_vintage():
    """Test business vintage scoring."""
    assert score_business_vintage(5.0) == 100.0
    assert score_business_vintage(8.0) == 100.0
    assert score_business_vintage(4.0) == 80.0
    assert score_business_vintage(2.5) == 60.0
    assert score_business_vintage(1.5) == 40.0
    assert score_business_vintage(0.5) == 20.0
    assert score_business_vintage(None) is None


def test_score_banking_strength():
    """Test banking strength composite score."""
    # Perfect banking: high balance, no bounces, low cash ratio
    score = score_banking_strength(
        avg_balance=30000.0,
        bounce_count=0,
        cash_ratio=0.10,
        min_abb=15000.0
    )
    assert score == 100.0

    # Weak banking: low balance, bounces, high cash
    score = score_banking_strength(
        avg_balance=8000.0,
        bounce_count=4,
        cash_ratio=0.50,
        min_abb=15000.0
    )
    assert score == 30.0


def test_score_foir():
    """Test FOIR (Fixed Obligation to Income Ratio) scoring."""
    assert score_foir(1.5, 8.0) == 100.0  # 18.75% FOIR
    assert score_foir(2.5, 8.0) == 75.0   # 31.25% FOIR
    assert score_foir(4.0, 8.0) == 50.0   # 50% FOIR
    assert score_foir(5.0, 8.0) == 30.0   # 62.5% FOIR
    assert score_foir(6.0, 8.0) == 0.0    # 75% FOIR
    assert score_foir(None, 8.0) is None


def test_score_documentation(strong_borrower, bajaj_stbl):
    """Test documentation scoring."""
    # Strong borrower has PAN, Aadhaar, GST
    score = score_documentation(strong_borrower, bajaj_stbl)

    # Bajaj requires GST, and likely PAN/Aadhaar for KYC
    assert score >= 50.0  # Should have at least some docs


def test_documentation_no_requirements():
    """Test documentation scoring when lender requires no docs."""
    borrower = BorrowerFeatureVector()
    lender = LenderProductRule(
        lender_name="Test",
        product_name="Test",
        gst_required=False,
        ownership_proof_required=False,
        kyc_documents=""
    )

    score = score_documentation(borrower, lender)
    assert score == 100.0  # No requirements = perfect score


# ═══════════════════════════════════════════════════════════════
# TEST: COMPOSITE ELIGIBILITY SCORING
# ═══════════════════════════════════════════════════════════════

def test_eligibility_score_strong_borrower(strong_borrower, bajaj_stbl):
    """Test that strong borrower gets high eligibility score."""
    score = calculate_eligibility_score(strong_borrower, bajaj_stbl)

    assert score >= 80.0  # Strong borrower should score high
    assert score <= 100.0


def test_eligibility_score_weak_borrower(weak_borrower, bajaj_stbl):
    """Test that weak borrower gets low eligibility score."""
    score = calculate_eligibility_score(weak_borrower, bajaj_stbl)

    assert score <= 50.0  # Weak borrower should score low


def test_eligibility_score_mid_tier(mid_tier_borrower, lendingkart_bl):
    """Test mid-tier borrower gets medium score."""
    score = calculate_eligibility_score(mid_tier_borrower, lendingkart_bl)

    assert score >= 50.0 and score <= 75.0  # Mid-range score


# ═══════════════════════════════════════════════════════════════
# TEST: RANKING & PROBABILITY
# ═══════════════════════════════════════════════════════════════

def test_approval_probability():
    """Test approval probability assignment."""
    assert determine_approval_probability(85.0) == ApprovalProbability.HIGH
    assert determine_approval_probability(75.0) == ApprovalProbability.HIGH
    assert determine_approval_probability(65.0) == ApprovalProbability.MEDIUM
    assert determine_approval_probability(50.0) == ApprovalProbability.MEDIUM
    assert determine_approval_probability(40.0) == ApprovalProbability.LOW


def test_ticket_range_calculation(strong_borrower, bajaj_stbl):
    """Test expected ticket size calculation."""
    min_ticket, max_ticket = calculate_ticket_range(
        strong_borrower, bajaj_stbl, score=85.0
    )

    # Bajaj max is 3L
    assert max_ticket == 3.0
    assert min_ticket is not None
    assert min_ticket < max_ticket


def test_ticket_range_turnover_based(strong_borrower):
    """Test ticket range when lender has no max ticket size."""
    lender = LenderProductRule(
        lender_name="Test",
        product_name="Test",
        max_ticket_size=None  # No max defined
    )

    min_ticket, max_ticket = calculate_ticket_range(
        strong_borrower, lender, score=80.0
    )

    # Should use turnover-based calculation
    # Strong borrower has 50L turnover, so ~25% = 12.5L for high score
    assert max_ticket is not None
    assert max_ticket > 0


def test_rank_results():
    """Test ranking of eligibility results."""
    results = [
        EligibilityResult(
            lender_name="Lender A",
            product_name="BL",
            hard_filter_status=HardFilterStatus.PASS,
            eligibility_score=60.0,
            rank=None
        ),
        EligibilityResult(
            lender_name="Lender B",
            product_name="STBL",
            hard_filter_status=HardFilterStatus.PASS,
            eligibility_score=85.0,
            rank=None
        ),
        EligibilityResult(
            lender_name="Lender C",
            product_name="BL",
            hard_filter_status=HardFilterStatus.PASS,
            eligibility_score=70.0,
            rank=None
        ),
    ]

    ranked = rank_results(results)

    assert ranked[0].lender_name == "Lender B"  # Highest score
    assert ranked[0].rank == 1
    assert ranked[1].lender_name == "Lender C"
    assert ranked[1].rank == 2
    assert ranked[2].lender_name == "Lender A"  # Lowest score
    assert ranked[2].rank == 3


# ═══════════════════════════════════════════════════════════════
# TEST: MISSING FOR IMPROVEMENT
# ═══════════════════════════════════════════════════════════════

def test_missing_for_improvement_passed_high_score(strong_borrower):
    """Test that high-scoring passed borrowers get minimal suggestions."""
    from app.services.stages.stage4_eligibility import identify_missing_for_improvement

    missing = identify_missing_for_improvement(
        strong_borrower,
        HardFilterStatus.PASS,
        score=85.0
    )

    # Strong borrower with high score should have minimal missing items
    assert len(missing) <= 1


def test_missing_for_improvement_passed_low_score(weak_borrower):
    """Test that low-scoring passed borrowers get improvement suggestions."""
    from app.services.stages.stage4_eligibility import identify_missing_for_improvement

    missing = identify_missing_for_improvement(
        weak_borrower,
        HardFilterStatus.PASS,
        score=45.0
    )

    # Weak borrower should have multiple suggestions
    assert len(missing) >= 2


def test_missing_for_improvement_failed():
    """Test that failed borrowers get hard filter message."""
    from app.services.stages.stage4_eligibility import identify_missing_for_improvement

    missing = identify_missing_for_improvement(
        BorrowerFeatureVector(),
        HardFilterStatus.FAIL,
        score=0.0
    )

    assert "hard filter" in missing[0].lower()


# ═══════════════════════════════════════════════════════════════
# TEST: EDGE CASES
# ═══════════════════════════════════════════════════════════════

def test_scoring_with_missing_data():
    """Test eligibility scoring when borrower has incomplete data."""
    sparse_borrower = BorrowerFeatureVector(
        cibil_score=700,
        entity_type=EntityType.PROPRIETORSHIP,
        business_vintage_years=2.0,
        # Missing: turnover, banking data, etc.
        feature_completeness=30.0
    )

    lender = LenderProductRule(
        lender_name="Test",
        product_name="Test",
        min_cibil_score=650,
        min_vintage_years=1.0
    )

    score = calculate_eligibility_score(sparse_borrower, lender)

    # Should still calculate a score, but may be lower due to missing components
    assert score >= 0.0
    assert score <= 100.0


def test_scoring_with_none_values():
    """Test that None values don't crash scoring."""
    borrower = BorrowerFeatureVector(
        cibil_score=None,
        annual_turnover=None,
        business_vintage_years=None,
        feature_completeness=0.0
    )

    lender = LenderProductRule(
        lender_name="Test",
        product_name="Test"
    )

    score = calculate_eligibility_score(borrower, lender)

    # Should return 0 or very low score when no data available
    assert score >= 0.0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
