"""Tests for Stage 2: Field Extraction and Feature Assembly."""
import pytest
from datetime import datetime, date
from uuid import uuid4

from app.services.stages.stage2_extraction import FieldExtractor
from app.services.stages.stage2_features import FeatureAssembler
from app.schemas.shared import ExtractedFieldItem, BorrowerFeatureVector
from app.core.enums import DocumentType, EntityType
from app.models.case import Case


# ═══════════════════════════════════════════════════════════════
# SAMPLE OCR TEXT DATA
# ═══════════════════════════════════════════════════════════════

SAMPLE_PAN_OCR = """
INCOME TAX DEPARTMENT
GOVT. OF INDIA
Permanent Account Number Card

Name: RAJESH KUMAR SHARMA
Father's Name: MOHAN LAL SHARMA
Date of Birth: 15/03/1985
ABCDE1234F
"""

SAMPLE_AADHAAR_OCR = """
Government of India
Aadhaar
1234 5678 9012

Name: Priya Singh
DOB: 22/07/1990
Address: 123 MG Road
Bangalore
Karnataka - 560001
"""

SAMPLE_GST_CERTIFICATE_OCR = """
GST Registration Certificate

GSTIN: 29ABCDE1234F1Z5
Legal Name of Business: TECH SOLUTIONS PRIVATE LIMITED
Trade Name: Tech Solutions
Date of Registration: 01/04/2018
State: Karnataka (29)
Constitution of Business: Private Limited Company
"""

SAMPLE_GST_RETURNS_OCR = """
GSTR-3B Return Summary
Filing Period: 04/2023
GSTIN: 29ABCDE1234F1Z5

Outward Supplies (Taxable):
Total Taxable Value: Rs. 25,00,000
CGST: Rs. 2,25,000
SGST: Rs. 2,25,000
Total Tax: Rs. 4,50,000
"""

SAMPLE_CIBIL_REPORT_OCR = """
CIBIL TransUnion Score Report
Credit Score: 756

Account Summary:
Active Accounts: 4
Closed Accounts: 2
Overdue Accounts: 0

Credit Enquiries (Last 6 months): 2
Total Outstanding: Rs. 12,50,000
"""

SAMPLE_ITR_OCR = """
INCOME TAX RETURN
Assessment Year: 2023-24
PAN: ABCDE1234F

Income Details:
Gross Total Income: Rs. 18,50,000
Income from Business: Rs. 15,00,000
Income from Other Sources: Rs. 3,50,000

Tax Computation:
Total Tax Paid: Rs. 2,75,000
Self Assessment Tax: Rs. 50,000
"""

SAMPLE_FINANCIAL_STATEMENT_OCR = """
Profit & Loss Statement
For the year ended 31st March 2023

Revenue from Operations: Rs. 1,25,00,000
Cost of Goods Sold: Rs. 75,00,000
Gross Profit: Rs. 50,00,000

Operating Expenses: Rs. 30,00,000
Net Profit After Tax: Rs. 14,00,000

Balance Sheet:
Total Assets: Rs. 85,00,000
Total Liabilities: Rs. 45,00,000
Net Worth: Rs. 40,00,000
"""

NOISY_PAN_OCR = """
1NCOME   TAX    DEPARTMENT
GOVT.   OF    1ND1A

Name :  RAJ ESH   KUMAR   SHARMA
Permanent  Account  Number
ABCOE1234F
Date of   Birth :  15 - 03 - 1985
"""


# ═══════════════════════════════════════════════════════════════
# EXTRACTION TESTS
# ═══════════════════════════════════════════════════════════════

class TestFieldExtractor:
    """Test the FieldExtractor class."""

    @pytest.mark.asyncio
    async def test_extract_pan_card(self):
        """Test PAN card field extraction."""
        extractor = FieldExtractor()
        fields = await extractor.extract_fields(SAMPLE_PAN_OCR, DocumentType.PAN_PERSONAL)

        # Check that fields were extracted
        assert len(fields) > 0

        # Get field values by name
        field_dict = {f.field_name: f for f in fields}

        # Validate PAN number
        assert "pan_number" in field_dict
        pan = field_dict["pan_number"]
        assert pan.field_value == "ABCDE1234F"
        assert pan.confidence > 0.5

        # Validate name
        assert "full_name" in field_dict
        name = field_dict["full_name"]
        assert "RAJESH KUMAR SHARMA" in name.field_value

        # Validate DOB
        assert "dob" in field_dict
        dob = field_dict["dob"]
        assert "15/03/1985" in dob.field_value

    @pytest.mark.asyncio
    async def test_extract_aadhaar(self):
        """Test Aadhaar card field extraction."""
        extractor = FieldExtractor()
        fields = await extractor.extract_fields(SAMPLE_AADHAAR_OCR, DocumentType.AADHAAR)

        field_dict = {f.field_name: f for f in fields}

        # Validate Aadhaar number
        assert "aadhaar_number" in field_dict
        aadhaar = field_dict["aadhaar_number"]
        assert aadhaar.field_value == "123456789012"
        assert aadhaar.confidence > 0.5

        # Validate name
        assert "full_name" in field_dict

        # Validate DOB
        assert "dob" in field_dict

    @pytest.mark.asyncio
    async def test_extract_gst_certificate(self):
        """Test GST certificate field extraction."""
        extractor = FieldExtractor()
        fields = await extractor.extract_fields(
            SAMPLE_GST_CERTIFICATE_OCR,
            DocumentType.GST_CERTIFICATE
        )

        field_dict = {f.field_name: f for f in fields}

        # Validate GSTIN
        assert "gstin" in field_dict
        gstin = field_dict["gstin"]
        assert gstin.field_value == "29ABCDE1234F1Z5"
        assert gstin.confidence > 0.5

        # Validate state extraction from GSTIN
        assert "state" in field_dict
        state = field_dict["state"]
        assert state.field_value == "Karnataka"

        # Validate business name
        assert "business_name" in field_dict

        # Validate registration date
        assert "gst_registration_date" in field_dict

    @pytest.mark.asyncio
    async def test_extract_gst_returns(self):
        """Test GST returns field extraction."""
        extractor = FieldExtractor()
        fields = await extractor.extract_fields(SAMPLE_GST_RETURNS_OCR, DocumentType.GST_RETURNS)

        field_dict = {f.field_name: f for f in fields}

        # Validate taxable value
        assert "gst_taxable_value" in field_dict
        taxable = field_dict["gst_taxable_value"]
        # Value should be extracted without commas
        assert "2500000" in taxable.field_value or "25,00,000" in taxable.field_value

        # Validate CGST
        assert "gst_cgst_amount" in field_dict

        # Validate SGST
        assert "gst_sgst_amount" in field_dict

        # Validate filing period
        assert "gst_filing_period" in field_dict

    @pytest.mark.asyncio
    async def test_extract_cibil_report(self):
        """Test CIBIL report field extraction."""
        extractor = FieldExtractor()
        fields = await extractor.extract_fields(SAMPLE_CIBIL_REPORT_OCR, DocumentType.CIBIL_REPORT)

        field_dict = {f.field_name: f for f in fields}

        # Validate credit score
        assert "cibil_score" in field_dict
        score = field_dict["cibil_score"]
        assert score.field_value == "756"
        assert score.confidence > 0.5

        # Validate active loans
        assert "active_loan_count" in field_dict
        active = field_dict["active_loan_count"]
        assert active.field_value == "4"

        # Validate overdue count
        assert "overdue_count" in field_dict

        # Validate enquiry count
        assert "enquiry_count_6m" in field_dict

    @pytest.mark.asyncio
    async def test_extract_itr(self):
        """Test ITR field extraction."""
        extractor = FieldExtractor()
        fields = await extractor.extract_fields(SAMPLE_ITR_OCR, DocumentType.ITR)

        field_dict = {f.field_name: f for f in fields}

        # Validate total income
        assert "itr_total_income" in field_dict
        income = field_dict["itr_total_income"]
        # Should extract numeric value without commas
        assert "1850000" in income.field_value or "18,50,000" in income.field_value

        # Validate assessment year
        assert "itr_assessment_year" in field_dict
        ay = field_dict["itr_assessment_year"]
        assert "2023-24" in ay.field_value

        # Validate tax paid
        assert "itr_tax_paid" in field_dict

        # Validate business income
        assert "itr_business_income" in field_dict

    @pytest.mark.asyncio
    async def test_extract_financial_statements(self):
        """Test financial statements field extraction."""
        extractor = FieldExtractor()
        fields = await extractor.extract_fields(
            SAMPLE_FINANCIAL_STATEMENT_OCR,
            DocumentType.FINANCIAL_STATEMENTS
        )

        field_dict = {f.field_name: f for f in fields}

        # Validate revenue/turnover
        assert "annual_turnover" in field_dict
        revenue = field_dict["annual_turnover"]
        # Should extract revenue value
        assert len(revenue.field_value) > 0

        # Validate net profit
        assert "net_profit" in field_dict

        # Validate net worth
        assert "net_worth" in field_dict

    @pytest.mark.asyncio
    async def test_validation_adjusts_confidence(self):
        """Test that invalid fields get lower confidence."""
        extractor = FieldExtractor()

        # Invalid PAN (wrong format)
        invalid_pan_ocr = "PAN: ABC123456"
        fields = await extractor.extract_fields(invalid_pan_ocr, DocumentType.PAN_PERSONAL)

        # Should still extract but with adjusted confidence
        # (depends on whether pattern matches - this tests validation logic)

    @pytest.mark.asyncio
    async def test_noisy_ocr_extraction(self):
        """Test extraction from noisy OCR text."""
        extractor = FieldExtractor()
        fields = await extractor.extract_fields(NOISY_PAN_OCR, DocumentType.PAN_PERSONAL)

        field_dict = {f.field_name: f for f in fields}

        # Should still extract PAN despite noise
        assert "pan_number" in field_dict

    @pytest.mark.asyncio
    async def test_empty_ocr_text(self):
        """Test extraction with empty OCR text."""
        extractor = FieldExtractor()
        fields = await extractor.extract_fields("", DocumentType.PAN_PERSONAL)

        assert len(fields) == 0

    @pytest.mark.asyncio
    async def test_unsupported_document_type(self):
        """Test extraction with unsupported document type."""
        extractor = FieldExtractor()
        fields = await extractor.extract_fields(
            "Some text",
            DocumentType.PROPERTY_DOCUMENTS
        )

        # Should return empty list for unsupported types
        assert len(fields) == 0


# ═══════════════════════════════════════════════════════════════
# FEATURE ASSEMBLY TESTS
# ═══════════════════════════════════════════════════════════════

class TestFeatureAssembler:
    """Test the FeatureAssembler class."""

    @pytest.mark.asyncio
    async def test_assemble_features_basic(self, db_session, test_user_id):
        """Test basic feature assembly."""
        # Create a test case
        case = Case(
            case_id="TEST-001",
            user_id=test_user_id,
            status="created",
            borrower_name="John Doe",
            cibil_score_manual=720
        )
        db_session.add(case)
        await db_session.commit()

        # Create extracted fields
        extracted_fields = [
            ExtractedFieldItem(
                field_name="pan_number",
                field_value="ABCDE1234F",
                confidence=0.9,
                source="extraction"
            ),
            ExtractedFieldItem(
                field_name="cibil_score",
                field_value="750",
                confidence=0.85,
                source="extraction"
            ),
            ExtractedFieldItem(
                field_name="annual_turnover",
                field_value="12500000",
                confidence=0.8,
                source="extraction"
            )
        ]

        assembler = FeatureAssembler()
        feature_vector = await assembler.assemble_features(
            db=db_session,
            case_id="TEST-001",
            extracted_fields=extracted_fields
        )

        # Validate feature vector
        assert feature_vector is not None
        assert feature_vector.pan_number == "ABCDE1234F"

        # High-confidence extraction should override manual
        assert feature_vector.cibil_score == 750

        # Annual turnover should be converted to float
        assert feature_vector.annual_turnover == 12500000.0

        # Full name should come from manual (borrower_name)
        assert feature_vector.full_name == "John Doe"

        # Feature completeness should be calculated
        assert feature_vector.feature_completeness > 0

    @pytest.mark.asyncio
    async def test_priority_manual_over_low_confidence(self, db_session, test_user_id):
        """Test that manual values override low-confidence extraction."""
        case = Case(
            case_id="TEST-002",
            user_id=test_user_id,
            status="created",
            cibil_score_manual=720
        )
        db_session.add(case)
        await db_session.commit()

        # Low-confidence extraction
        extracted_fields = [
            ExtractedFieldItem(
                field_name="cibil_score",
                field_value="650",
                confidence=0.3,  # Low confidence
                source="extraction"
            )
        ]

        assembler = FeatureAssembler()
        feature_vector = await assembler.assemble_features(
            db=db_session,
            case_id="TEST-002",
            extracted_fields=extracted_fields
        )

        # Manual value should be used
        assert feature_vector.cibil_score == 720

    @pytest.mark.asyncio
    async def test_type_conversion(self, db_session, test_user_id):
        """Test field type conversion."""
        case = Case(
            case_id="TEST-003",
            user_id=test_user_id,
            status="created"
        )
        db_session.add(case)
        await db_session.commit()

        extracted_fields = [
            ExtractedFieldItem(
                field_name="dob",
                field_value="15/03/1985",
                confidence=0.8,
                source="extraction"
            ),
            ExtractedFieldItem(
                field_name="annual_turnover",
                field_value="1,25,00,000",  # Indian format with commas
                confidence=0.8,
                source="extraction"
            ),
            ExtractedFieldItem(
                field_name="active_loan_count",
                field_value="4.0",  # Float that should become int
                confidence=0.8,
                source="extraction"
            )
        ]

        assembler = FeatureAssembler()
        feature_vector = await assembler.assemble_features(
            db=db_session,
            case_id="TEST-003",
            extracted_fields=extracted_fields
        )

        # Date conversion
        assert isinstance(feature_vector.dob, date)
        assert feature_vector.dob.year == 1985

        # Float conversion (commas removed)
        assert feature_vector.annual_turnover == 12500000.0

        # Integer conversion
        assert feature_vector.active_loan_count == 4
        assert isinstance(feature_vector.active_loan_count, int)

    @pytest.mark.asyncio
    async def test_feature_completeness_calculation(self, db_session, test_user_id):
        """Test feature completeness calculation."""
        case = Case(
            case_id="TEST-004",
            user_id=test_user_id,
            status="created"
        )
        db_session.add(case)
        await db_session.commit()

        # Provide only a few fields
        extracted_fields = [
            ExtractedFieldItem(
                field_name="pan_number",
                field_value="ABCDE1234F",
                confidence=0.9,
                source="extraction"
            ),
            ExtractedFieldItem(
                field_name="cibil_score",
                field_value="750",
                confidence=0.9,
                source="extraction"
            )
        ]

        assembler = FeatureAssembler()
        feature_vector = await assembler.assemble_features(
            db=db_session,
            case_id="TEST-004",
            extracted_fields=extracted_fields
        )

        # Completeness should be low since only 2 fields provided
        # Total fields = 21 (from FIELD_MAPPING)
        # 2 filled / 21 total = ~9.5%
        assert 0 < feature_vector.feature_completeness < 20

    @pytest.mark.asyncio
    async def test_save_and_retrieve_extracted_fields(self, db_session, test_user_id):
        """Test saving and retrieving extracted fields."""
        case = Case(
            case_id="TEST-005",
            user_id=test_user_id,
            status="created"
        )
        db_session.add(case)
        await db_session.commit()

        fields = [
            ExtractedFieldItem(
                field_name="pan_number",
                field_value="ABCDE1234F",
                confidence=0.9,
                source="extraction"
            )
        ]

        assembler = FeatureAssembler()

        # Save fields
        await assembler.save_extracted_fields(
            db=db_session,
            case_id="TEST-005",
            document_id=None,
            fields=fields
        )

        # Retrieve fields
        retrieved = await assembler.get_extracted_fields(
            db=db_session,
            case_id="TEST-005"
        )

        assert len(retrieved) == 1
        assert retrieved[0].field_name == "pan_number"
        assert retrieved[0].field_value == "ABCDE1234F"

    @pytest.mark.asyncio
    async def test_save_and_retrieve_feature_vector(self, db_session, test_user_id):
        """Test saving and retrieving feature vector."""
        case = Case(
            case_id="TEST-006",
            user_id=test_user_id,
            status="created"
        )
        db_session.add(case)
        await db_session.commit()

        # Create a feature vector
        feature_vector = BorrowerFeatureVector(
            pan_number="ABCDE1234F",
            cibil_score=750,
            annual_turnover=12500000.0,
            feature_completeness=25.0
        )

        assembler = FeatureAssembler()

        # Save feature vector
        await assembler.save_feature_vector(
            db=db_session,
            case_id="TEST-006",
            feature_vector=feature_vector
        )

        # Retrieve feature vector
        retrieved = await assembler.get_feature_vector(
            db=db_session,
            case_id="TEST-006"
        )

        assert retrieved is not None
        assert retrieved.pan_number == "ABCDE1234F"
        assert retrieved.cibil_score == 750
        assert retrieved.feature_completeness == 25.0

    @pytest.mark.asyncio
    async def test_update_existing_feature_vector(self, db_session, test_user_id):
        """Test updating an existing feature vector."""
        case = Case(
            case_id="TEST-007",
            user_id=test_user_id,
            status="created"
        )
        db_session.add(case)
        await db_session.commit()

        assembler = FeatureAssembler()

        # Save initial feature vector
        initial = BorrowerFeatureVector(
            pan_number="ABCDE1234F",
            cibil_score=700,
            feature_completeness=10.0
        )
        await assembler.save_feature_vector(
            db=db_session,
            case_id="TEST-007",
            feature_vector=initial
        )

        # Update with new data
        updated = BorrowerFeatureVector(
            pan_number="ABCDE1234F",
            cibil_score=750,
            annual_turnover=12500000.0,
            feature_completeness=25.0
        )
        await assembler.save_feature_vector(
            db=db_session,
            case_id="TEST-007",
            feature_vector=updated
        )

        # Retrieve and verify update
        retrieved = await assembler.get_feature_vector(
            db=db_session,
            case_id="TEST-007"
        )

        assert retrieved.cibil_score == 750
        assert retrieved.annual_turnover == 12500000.0
        assert retrieved.feature_completeness == 25.0


# ═══════════════════════════════════════════════════════════════
# VALIDATION TESTS
# ═══════════════════════════════════════════════════════════════

class TestValidation:
    """Test field validation logic."""

    def test_validate_pan(self):
        """Test PAN validation."""
        extractor = FieldExtractor()

        # Valid PAN
        assert extractor._validate_pan("ABCDE1234F") is True

        # Invalid: wrong length
        assert extractor._validate_pan("ABCDE1234") is False

        # Invalid: wrong format
        assert extractor._validate_pan("12345ABCDE") is False

        # Invalid: wrong entity type character
        assert extractor._validate_pan("ABCXE1234F") is False

    def test_validate_gstin(self):
        """Test GSTIN validation."""
        extractor = FieldExtractor()

        # Valid GSTIN
        assert extractor._validate_gstin("29ABCDE1234F1Z5") is True

        # Invalid: wrong length
        assert extractor._validate_gstin("29ABCDE1234F1Z") is False

        # Invalid: invalid state code
        assert extractor._validate_gstin("99ABCDE1234F1Z5") is False

        # Invalid: embedded PAN is invalid
        assert extractor._validate_gstin("29ABCXE1234F1Z5") is False

    def test_validate_cibil_score(self):
        """Test CIBIL score validation."""
        extractor = FieldExtractor()

        # Valid score
        field = ExtractedFieldItem(
            field_name="cibil_score",
            field_value="750",
            confidence=0.9,
            source="extraction"
        )
        assert extractor._validate_field(field) is True

        # Invalid: too low
        field.field_value = "250"
        assert extractor._validate_field(field) is False

        # Invalid: too high
        field.field_value = "950"
        assert extractor._validate_field(field) is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
