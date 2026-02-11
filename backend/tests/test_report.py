"""Tests for Stage 5: Case Intelligence Report Generation

Tests cover:
- Report data assembly with complete data
- Report data assembly with partial/missing data
- Strengths and risk detection
- Submission strategy generation
- PDF generation
- WhatsApp summary generation
- API endpoints
"""

import pytest
from datetime import date, datetime
from uuid import uuid4

from app.schemas.shared import (
    BorrowerFeatureVector,
    DocumentChecklist,
    EligibilityResult,
    CaseReportData,
)
from app.core.enums import (
    EntityType,
    ProgramType,
    DocumentType,
    HardFilterStatus,
    ApprovalProbability,
)
from app.services.stages.stage5_report import (
    compute_strengths,
    compute_risk_flags,
    generate_whatsapp_summary,
)
from app.services.stages.stage5_pdf_generator import (
    generate_pdf_report,
)


# ═══════════════════════════════════════════════════════════════
# TEST FIXTURES
# ═══════════════════════════════════════════════════════════════

@pytest.fixture
def strong_borrower():
    """Create a borrower with strong profile."""
    return BorrowerFeatureVector(
        full_name="Rajesh Kumar",
        pan_number="ABCDE1234F",
        entity_type=EntityType.PROPRIETORSHIP,
        business_vintage_years=8.0,
        industry_type="Manufacturing",
        pincode="400001",
        annual_turnover=120.0,  # 1.2 Cr
        cibil_score=780,
        avg_monthly_balance=500000,
        monthly_credit_avg=800000,
        emi_outflow_monthly=150000,
        bounce_count_12m=0,
        cash_deposit_ratio=0.15,
        gstin="27ABCDE1234F1Z5",
        feature_completeness=95.0,
    )


@pytest.fixture
def weak_borrower():
    """Create a borrower with weak profile."""
    return BorrowerFeatureVector(
        full_name="Amit Shah",
        pan_number="XYZAB9876C",
        entity_type=EntityType.PROPRIETORSHIP,
        business_vintage_years=1.5,
        industry_type="Retail",
        pincode="110001",
        annual_turnover=15.0,  # 15 Lakhs
        cibil_score=620,
        avg_monthly_balance=50000,
        monthly_credit_avg=100000,
        emi_outflow_monthly=60000,
        bounce_count_12m=5,
        cash_deposit_ratio=0.55,
        feature_completeness=70.0,
    )


@pytest.fixture
def complete_checklist():
    """Create a complete document checklist."""
    return DocumentChecklist(
        program_type=ProgramType.BANKING,
        available=[
            DocumentType.AADHAAR,
            DocumentType.PAN_PERSONAL,
            DocumentType.BANK_STATEMENT,
            DocumentType.CIBIL_REPORT,
            DocumentType.GST_CERTIFICATE,
        ],
        missing=[],
        unreadable=[],
        optional_present=[DocumentType.PROPERTY_DOCUMENTS],
        completeness_score=100.0,
    )


@pytest.fixture
def incomplete_checklist():
    """Create an incomplete document checklist."""
    return DocumentChecklist(
        program_type=ProgramType.HYBRID,
        available=[
            DocumentType.AADHAAR,
            DocumentType.PAN_PERSONAL,
        ],
        missing=[
            DocumentType.BANK_STATEMENT,
            DocumentType.CIBIL_REPORT,
            DocumentType.ITR,
            DocumentType.GST_RETURNS,
        ],
        unreadable=["corrupted_file.pdf"],
        optional_present=[],
        completeness_score=33.0,
    )


@pytest.fixture
def high_match_lenders():
    """Create eligibility results with high matches."""
    return [
        EligibilityResult(
            lender_name="HDFC Bank",
            product_name="Business Loan",
            hard_filter_status=HardFilterStatus.PASS,
            hard_filter_details={},
            eligibility_score=92.5,
            approval_probability=ApprovalProbability.HIGH,
            expected_ticket_min=15.0,
            expected_ticket_max=30.0,
            confidence=0.95,
            missing_for_improvement=[],
            rank=1,
        ),
        EligibilityResult(
            lender_name="ICICI Bank",
            product_name="SME Loan",
            hard_filter_status=HardFilterStatus.PASS,
            hard_filter_details={},
            eligibility_score=88.0,
            approval_probability=ApprovalProbability.HIGH,
            expected_ticket_min=12.0,
            expected_ticket_max=25.0,
            confidence=0.90,
            missing_for_improvement=[],
            rank=2,
        ),
        EligibilityResult(
            lender_name="Axis Bank",
            product_name="Business Loan",
            hard_filter_status=HardFilterStatus.PASS,
            hard_filter_details={},
            eligibility_score=85.0,
            approval_probability=ApprovalProbability.HIGH,
            expected_ticket_min=10.0,
            expected_ticket_max=22.0,
            confidence=0.88,
            missing_for_improvement=[],
            rank=3,
        ),
        EligibilityResult(
            lender_name="Bajaj Finance",
            product_name="Business Term Loan",
            hard_filter_status=HardFilterStatus.PASS,
            hard_filter_details={},
            eligibility_score=72.0,
            approval_probability=ApprovalProbability.MEDIUM,
            expected_ticket_min=8.0,
            expected_ticket_max=18.0,
            confidence=0.85,
            missing_for_improvement=["Improve CIBIL score"],
            rank=4,
        ),
    ]


@pytest.fixture
def no_match_lenders():
    """Create eligibility results with no matches."""
    return [
        EligibilityResult(
            lender_name="HDFC Bank",
            product_name="Business Loan",
            hard_filter_status=HardFilterStatus.FAIL,
            hard_filter_details={"cibil_score": "620 < required 675"},
            eligibility_score=None,
            approval_probability=None,
            expected_ticket_min=None,
            expected_ticket_max=None,
            confidence=0.70,
            missing_for_improvement=[],
            rank=None,
        ),
        EligibilityResult(
            lender_name="ICICI Bank",
            product_name="SME Loan",
            hard_filter_status=HardFilterStatus.FAIL,
            hard_filter_details={"vintage": "1.5y < required 2y"},
            eligibility_score=None,
            approval_probability=None,
            expected_ticket_min=None,
            expected_ticket_max=None,
            confidence=0.70,
            missing_for_improvement=[],
            rank=None,
        ),
    ]


# ═══════════════════════════════════════════════════════════════
# STRENGTHS & RISKS TESTS
# ═══════════════════════════════════════════════════════════════

def test_compute_strengths_strong_borrower(strong_borrower, high_match_lenders):
    """Test strength detection for a strong borrower."""
    strengths = compute_strengths(strong_borrower, high_match_lenders)

    # Should identify multiple strengths
    assert len(strengths) > 0

    # Check for specific strengths
    strength_text = " ".join(strengths)
    assert "Excellent credit score" in strength_text or "Good credit score" in strength_text
    assert "Strong annual turnover" in strength_text
    assert "Well-established business" in strength_text
    assert "zero bounces" in strength_text
    assert "low cash deposit ratio" in strength_text
    assert "Low existing obligations" in strength_text
    assert "lenders matched with high probability" in strength_text


def test_compute_strengths_weak_borrower(weak_borrower, no_match_lenders):
    """Test strength detection for a weak borrower."""
    strengths = compute_strengths(weak_borrower, no_match_lenders)

    # Should have few or no strengths
    assert len(strengths) <= 2  # Maybe low obligations, but not much else


def test_compute_risk_flags_weak_borrower(weak_borrower, incomplete_checklist, no_match_lenders):
    """Test risk flag detection for a weak borrower."""
    risks = compute_risk_flags(weak_borrower, incomplete_checklist, no_match_lenders)

    # Should identify multiple risks
    assert len(risks) > 0

    # Check for specific risks
    risk_text = " ".join(risks)
    assert "Low credit score" in risk_text
    assert "Low business vintage" in risk_text
    assert "bounced cheques" in risk_text
    assert "High cash deposit ratio" in risk_text
    assert "High existing debt obligations" in risk_text
    assert "Incomplete documentation" in risk_text
    assert "No eligible lenders found" in risk_text


def test_compute_risk_flags_strong_borrower(strong_borrower, complete_checklist, high_match_lenders):
    """Test risk flag detection for a strong borrower."""
    risks = compute_risk_flags(strong_borrower, complete_checklist, high_match_lenders)

    # Should have few or no risks
    assert len(risks) == 0


# ═══════════════════════════════════════════════════════════════
# PDF GENERATION TESTS
# ═══════════════════════════════════════════════════════════════

def test_generate_pdf_complete_data(strong_borrower, complete_checklist, high_match_lenders):
    """Test PDF generation with complete data."""
    # Create report data
    report_data = CaseReportData(
        case_id="CASE-20250210-0001",
        borrower_profile=strong_borrower,
        checklist=complete_checklist,
        strengths=compute_strengths(strong_borrower, high_match_lenders),
        risk_flags=compute_risk_flags(strong_borrower, complete_checklist, high_match_lenders),
        lender_matches=high_match_lenders,
        submission_strategy="**Primary Target:** HDFC Bank - Business Loan\nScore: 92/100",
        missing_data_advisory=[],
        expected_loan_range="₹15.0L - ₹30.0L",
    )

    # Generate PDF
    pdf_bytes = generate_pdf_report(report_data)

    # Verify PDF was generated
    assert pdf_bytes is not None
    assert len(pdf_bytes) > 0

    # Verify PDF header (PDF files start with %PDF-)
    assert pdf_bytes[:4] == b'%PDF'

    # Verify reasonable file size (should be at least a few KB)
    assert len(pdf_bytes) > 5000


def test_generate_pdf_partial_data(weak_borrower, incomplete_checklist, no_match_lenders):
    """Test PDF generation with partial/missing data."""
    # Create report data with missing fields
    report_data = CaseReportData(
        case_id="CASE-20250210-0002",
        borrower_profile=weak_borrower,
        checklist=incomplete_checklist,
        strengths=compute_strengths(weak_borrower, no_match_lenders),
        risk_flags=compute_risk_flags(weak_borrower, incomplete_checklist, no_match_lenders),
        lender_matches=no_match_lenders,
        submission_strategy="No lenders currently match this profile.",
        missing_data_advisory=[
            "CIBIL score not available",
            "Bank Statement document missing",
        ],
        expected_loan_range=None,
    )

    # Generate PDF
    pdf_bytes = generate_pdf_report(report_data)

    # Verify PDF was generated even with partial data
    assert pdf_bytes is not None
    assert len(pdf_bytes) > 0
    assert pdf_bytes[:4] == b'%PDF'


# ═══════════════════════════════════════════════════════════════
# WHATSAPP SUMMARY TESTS
# ═══════════════════════════════════════════════════════════════

def test_whatsapp_summary_strong_case(strong_borrower, complete_checklist, high_match_lenders):
    """Test WhatsApp summary for a strong case."""
    report_data = CaseReportData(
        case_id="CASE-20250210-0001",
        borrower_profile=strong_borrower,
        checklist=complete_checklist,
        strengths=[],
        risk_flags=[],
        lender_matches=high_match_lenders,
        submission_strategy="",
        missing_data_advisory=[],
        expected_loan_range="₹15.0L - ₹30.0L",
    )

    summary = generate_whatsapp_summary(report_data)

    # Verify summary format
    assert "📋 Case: CASE-20250210-0001" in summary
    assert "👤 Borrower:" in summary
    assert "Rajesh Kumar" in summary
    assert "📊 CIBIL: 780" in summary
    assert "Turnover: ₹120.0L" in summary
    assert "✅ Top Match: HDFC Bank" in summary
    assert "HIGH" in summary
    assert "4 lenders matched" in summary
    assert "Best score: 92" in summary or "Best score: 93" in summary


def test_whatsapp_summary_weak_case(weak_borrower, incomplete_checklist, no_match_lenders):
    """Test WhatsApp summary for a weak case."""
    report_data = CaseReportData(
        case_id="CASE-20250210-0002",
        borrower_profile=weak_borrower,
        checklist=incomplete_checklist,
        strengths=[],
        risk_flags=[],
        lender_matches=no_match_lenders,
        submission_strategy="",
        missing_data_advisory=[],
        expected_loan_range=None,
    )

    summary = generate_whatsapp_summary(report_data)

    # Verify summary format
    assert "📋 Case: CASE-20250210-0002" in summary
    assert "👤 Borrower:" in summary
    assert "Amit Shah" in summary
    assert "📊 CIBIL: 620" in summary
    assert "❌ No lenders matched" in summary
    assert "⚠️ Missing:" in summary
    assert "Bank Statement" in summary


def test_whatsapp_summary_missing_data():
    """Test WhatsApp summary with missing borrower data."""
    borrower = BorrowerFeatureVector(
        full_name="Test User",
        # Most fields missing
        feature_completeness=20.0,
    )

    checklist = DocumentChecklist(
        program_type=ProgramType.BANKING,
        available=[],
        missing=[DocumentType.BANK_STATEMENT, DocumentType.CIBIL_REPORT],
        unreadable=[],
        optional_present=[],
        completeness_score=0.0,
    )

    report_data = CaseReportData(
        case_id="CASE-20250210-0003",
        borrower_profile=borrower,
        checklist=checklist,
        strengths=[],
        risk_flags=[],
        lender_matches=[],
        submission_strategy="",
        missing_data_advisory=[],
        expected_loan_range=None,
    )

    summary = generate_whatsapp_summary(report_data)

    # Verify summary handles missing data gracefully
    assert "📋 Case: CASE-20250210-0003" in summary
    assert "Test User" in summary
    assert "N/A" in summary  # For missing fields


# ═══════════════════════════════════════════════════════════════
# EDGE CASES
# ═══════════════════════════════════════════════════════════════

def test_empty_lender_matches():
    """Test report generation with no lender matches at all."""
    borrower = BorrowerFeatureVector(
        full_name="Empty Case",
        feature_completeness=50.0,
    )

    checklist = DocumentChecklist(
        program_type=ProgramType.BANKING,
        available=[],
        missing=[],
        unreadable=[],
        optional_present=[],
        completeness_score=0.0,
    )

    report_data = CaseReportData(
        case_id="CASE-20250210-0004",
        borrower_profile=borrower,
        checklist=checklist,
        strengths=[],
        risk_flags=[],
        lender_matches=[],  # Empty
        submission_strategy="No lenders evaluated",
        missing_data_advisory=["Complete borrower profile"],
        expected_loan_range=None,
    )

    # Should not crash
    pdf_bytes = generate_pdf_report(report_data)
    assert pdf_bytes is not None

    summary = generate_whatsapp_summary(report_data)
    assert summary is not None


def test_large_number_of_lenders():
    """Test PDF generation with many lenders."""
    # Create 50 lender matches
    many_lenders = []
    for i in range(50):
        many_lenders.append(
            EligibilityResult(
                lender_name=f"Lender {i+1}",
                product_name="Business Loan",
                hard_filter_status=HardFilterStatus.PASS,
                hard_filter_details={},
                eligibility_score=90.0 - i,
                approval_probability=ApprovalProbability.HIGH if i < 10 else ApprovalProbability.MEDIUM,
                expected_ticket_min=10.0,
                expected_ticket_max=20.0,
                confidence=0.85,
                missing_for_improvement=[],
                rank=i+1,
            )
        )

    borrower = BorrowerFeatureVector(
        full_name="Many Lenders Case",
        feature_completeness=90.0,
    )

    checklist = DocumentChecklist(
        program_type=ProgramType.BANKING,
        available=[],
        missing=[],
        unreadable=[],
        optional_present=[],
        completeness_score=100.0,
    )

    report_data = CaseReportData(
        case_id="CASE-20250210-0005",
        borrower_profile=borrower,
        checklist=checklist,
        strengths=[],
        risk_flags=[],
        lender_matches=many_lenders,
        submission_strategy="Multiple options available",
        missing_data_advisory=[],
        expected_loan_range="₹10.0L - ₹20.0L",
    )

    # Should handle many lenders gracefully
    pdf_bytes = generate_pdf_report(report_data)
    assert pdf_bytes is not None
    assert len(pdf_bytes) > 10000  # Should be a larger PDF


# ═══════════════════════════════════════════════════════════════
# RUN TESTS
# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("Running report generation tests...")
    print("\nNote: Run with pytest for full test suite:")
    print("  pytest backend/tests/test_report.py -v")
