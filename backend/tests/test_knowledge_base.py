"""Tests for Lender Knowledge Base (Stage 3)

Tests cover:
- CSV parsing utilities
- Lender name normalization
- Lender policy ingestion
- Pincode serviceability ingestion
- Lender CRUD operations
- Pincode queries
- Edge cases and error handling
"""

import pytest
from app.services.stages.stage3_ingestion import (
    parse_float_value,
    parse_integer_value,
    parse_months,
    parse_age_range,
    parse_entity_types,
    parse_boolean,
    normalize_lender_name,
    check_policy_available,
    _parse_lender_policy_row
)


# ═══════════════════════════════════════════════════════════════
# PARSING UTILITY TESTS
# ═══════════════════════════════════════════════════════════════

class TestParseFloatValue:
    """Test float value parsing with various formats."""

    def test_parse_lakhs(self):
        assert parse_float_value("30L") == 30.0
        assert parse_float_value("3.5L") == 3.5
        assert parse_float_value("100L") == 100.0

    def test_parse_thousands(self):
        assert parse_float_value("25K") == 0.25  # 25K = 0.25L
        assert parse_float_value("10k") == 0.10
        assert parse_float_value("15K") == 0.15

    def test_parse_with_operators(self):
        assert parse_float_value(">=25k") == 0.25
        assert parse_float_value(">10L") == 10.0
        assert parse_float_value("<=5L") == 5.0

    def test_parse_direct_numbers(self):
        assert parse_float_value("2.5") == 2.5
        assert parse_float_value("100") == 100.0

    def test_parse_empty_or_na(self):
        assert parse_float_value("") is None
        assert parse_float_value("NA") is None
        assert parse_float_value("N/A") is None
        assert parse_float_value("-") is None
        assert parse_float_value("nil") is None

    def test_parse_complex_text(self):
        # Should extract first number
        assert parse_float_value("GST active - 2 years otherwise 3 years") == 2.0
        assert parse_float_value("Minimum 5.5L required") == 5.5


class TestParseIntegerValue:
    """Test integer value parsing."""

    def test_parse_integers(self):
        assert parse_integer_value("750") == 750
        assert parse_integer_value("650") == 650

    def test_parse_with_operators(self):
        assert parse_integer_value(">=700") == 700
        assert parse_integer_value(">600") == 600

    def test_parse_empty_or_na(self):
        assert parse_integer_value("") is None
        assert parse_integer_value("NA") is None


class TestParseMonths:
    """Test parsing months from text."""

    def test_parse_month_text(self):
        assert parse_months("6 months") == 6
        assert parse_months("12 month") == 12
        assert parse_months("24 mon") == 24

    def test_parse_years_to_months(self):
        assert parse_months("2 years") == 24
        assert parse_months("1 yr") == 12

    def test_parse_direct_number(self):
        assert parse_months("6") == 6

    def test_parse_empty(self):
        assert parse_months("") is None
        assert parse_months("NA") is None


class TestParseAgeRange:
    """Test age range parsing."""

    def test_parse_range(self):
        assert parse_age_range("22-65") == (22, 65)
        assert parse_age_range("21 to 70") == (21, 70)

    def test_parse_single_age(self):
        assert parse_age_range("25") == (25, 25)

    def test_parse_empty(self):
        assert parse_age_range("") == (None, None)
        assert parse_age_range("NA") == (None, None)


class TestParseEntityTypes:
    """Test entity type parsing and normalization."""

    def test_parse_single_entity(self):
        assert parse_entity_types("Pvt Ltd") == ["pvt_ltd"]
        assert parse_entity_types("LLP") == ["llp"]
        assert parse_entity_types("Proprietorship") == ["proprietorship"]

    def test_parse_multiple_entities(self):
        result = parse_entity_types("Pvt Ltd, LLP, Proprietorship")
        assert "pvt_ltd" in result
        assert "llp" in result
        assert "proprietorship" in result

    def test_parse_variations(self):
        assert "pvt_ltd" in parse_entity_types("Private Limited")
        assert "partnership" in parse_entity_types("Partnership Firm")

    def test_parse_empty(self):
        assert parse_entity_types("") == []
        assert parse_entity_types("NA") == []


class TestParseBoolean:
    """Test boolean parsing."""

    def test_parse_yes_variations(self):
        assert parse_boolean("Yes") is True
        assert parse_boolean("Mandatory") is True
        assert parse_boolean("Required") is True
        assert parse_boolean("Y") is True

    def test_parse_no_variations(self):
        assert parse_boolean("No") is False
        assert parse_boolean("NA") is False
        assert parse_boolean("") is False


class TestNormalizeLenderName:
    """Test lender name normalization."""

    def test_normalize_standard_names(self):
        assert normalize_lender_name("GODREJ") == "Godrej"
        assert normalize_lender_name("LENDINGKART") == "Lendingkart"
        assert normalize_lender_name("BAJAJ") == "Bajaj"

    def test_normalize_variations(self):
        assert normalize_lender_name("TATA PL") == "Tata Capital"
        assert normalize_lender_name("TATA BL") == "Tata Capital"
        assert normalize_lender_name("USFB PL") == "Unity Small Finance Bank"

    def test_normalize_unknown_lender(self):
        # Unknown lenders should be title-cased
        result = normalize_lender_name("NEW LENDER")
        assert result == "New Lender"


class TestCheckPolicyAvailable:
    """Test policy availability detection."""

    def test_policy_available(self):
        row = {
            "Lender": "Indifi",
            "Product Program": "BL",
            "Min. Vintage": "2 years"
        }
        assert check_policy_available(row) is True

    def test_policy_not_available(self):
        row = {
            "Lender": "FT Cash",
            "Product Program": "Policy not available",
            "Min. Vintage": ""
        }
        assert check_policy_available(row) is False

        row2 = {
            "Lender": "ICICI",
            "Notes": "Policy not available"
        }
        assert check_policy_available(row2) is False


# ═══════════════════════════════════════════════════════════════
# LENDER POLICY ROW PARSING TESTS
# ═══════════════════════════════════════════════════════════════

class TestParseLenderPolicyRow:
    """Test parsing a full lender policy row."""

    def test_parse_complete_row(self):
        """Test parsing a row with all fields populated."""
        row = {
            "Lender": "Indifi",
            "Product Program": "BL",
            "Min. Vintage": "2 years",
            "Min. Score": "650",
            "Min. Turnover": "24L",
            "Max Ticket size": "30L",
            "ABB": ">=25k or 15% of EMI",
            "Entity": "Pvt Ltd, LLP, Proprietorship",
            "Age": "22-65",
            "No 30+": "6 months",
            "60+": "12 months",
            "90+": "12 months",
            "Enquiries": "Max 5 in 6 months",
            "EMI bounce": "Max 2 in 12 months",
            "Banking Statement": "6 months",
            "Bank Source": "AA, PDF",
            "GST": "Mandatory",
            "Tele PD": "Yes",
            "Video KYC": "No",
            "FI": "NA",
            "Tenor Min": "12",
            "Tenor Max": "36"
        }

        data = _parse_lender_policy_row(row, "Indifi")

        assert data["product_name"] == "BL"
        assert data["min_vintage_years"] == 2.0
        assert data["min_cibil_score"] == 650
        assert data["min_turnover_annual"] == 24.0
        assert data["max_ticket_size"] == 30.0
        assert data["min_abb"] == 0.25  # 25K
        assert data["abb_to_emi_ratio"] == "15% of EMI"
        assert "pvt_ltd" in data["eligible_entity_types"]
        assert data["age_min"] == 22
        assert data["age_max"] == 65
        assert data["no_30plus_dpd_months"] == 6
        assert data["banking_months_required"] == 6
        assert data["gst_required"] is True
        assert data["tele_pd_required"] is True
        assert data["video_kyc_required"] is False
        assert data["tenor_min_months"] == 12
        assert data["tenor_max_months"] == 36

    def test_parse_row_with_missing_fields(self):
        """Test parsing a row with many missing fields."""
        row = {
            "Lender": "Test Lender",
            "Product Program": "STBL",
            "Min. Score": "700",
            "Max Ticket size": "50L"
        }

        data = _parse_lender_policy_row(row, "Test Lender")

        assert data["product_name"] == "STBL"
        assert data["min_cibil_score"] == 700
        assert data["max_ticket_size"] == 50.0
        assert data["min_vintage_years"] is None
        assert data["eligible_entity_types"] == []

    def test_program_type_inference(self):
        """Test program type inference from product name."""
        # Banking program
        row1 = {"Product Program": "Digital"}
        data1 = _parse_lender_policy_row(row1, "Lender")
        assert data1["program_type"] == "banking"

        # Income program
        row2 = {"Product Program": "Income Based"}
        data2 = _parse_lender_policy_row(row2, "Lender")
        assert data2["program_type"] == "income"

        # Hybrid (default)
        row3 = {"Product Program": "BL"}
        data3 = _parse_lender_policy_row(row3, "Lender")
        assert data3["program_type"] == "hybrid"


# ═══════════════════════════════════════════════════════════════
# INTEGRATION TESTS (require database)
# ═══════════════════════════════════════════════════════════════

# Note: These would be marked with @pytest.mark.asyncio and would test:
# - ingest_lender_policy_csv() with a sample CSV file
# - ingest_pincode_csv() with a sample CSV file
# - lender_service functions (list_lenders, get_products, etc.)
# - Pincode queries
# - Edge cases (duplicates, missing lenders, invalid data)

# Example structure:
"""
@pytest.mark.asyncio
async def test_ingest_lender_policy_csv():
    # Create a sample CSV file
    csv_content = '''Lender,Product Program,Min. Score,Max Ticket size
Indifi,BL,650,30L
Bajaj,STBL,700,50L'''

    # Write to temp file
    # Call ingest_lender_policy_csv()
    # Verify lenders and products were created in DB
    pass


@pytest.mark.asyncio
async def test_list_lenders():
    # Call lender_service.list_lenders()
    # Verify structure and content
    pass


@pytest.mark.asyncio
async def test_find_lenders_by_pincode():
    # Set up test data
    # Query by pincode
    # Verify correct lenders returned
    pass
"""


# ═══════════════════════════════════════════════════════════════
# EDGE CASE TESTS
# ═══════════════════════════════════════════════════════════════

class TestEdgeCases:
    """Test edge cases and error conditions."""

    def test_parse_float_with_ranges(self):
        # Some fields might have range values
        value = "25-30L"
        # Should extract first number
        result = parse_float_value(value)
        assert result == 25.0

    def test_parse_complex_abb_rule(self):
        """Test parsing complex ABB rules."""
        row = {
            "ABB": ">=50k or 20% of EMI, whichever is higher"
        }
        data = _parse_lender_policy_row(row, "Lender")
        # Should parse the numeric part
        assert data["min_abb"] is not None

    def test_entity_types_case_insensitive(self):
        """Test entity types are normalized consistently."""
        result1 = parse_entity_types("PVT LTD")
        result2 = parse_entity_types("pvt ltd")
        result3 = parse_entity_types("Pvt Ltd")

        assert result1 == result2 == result3

    def test_empty_product_name(self):
        """Test handling of missing product name."""
        row = {
            "Product Program": "",
            "Min. Score": "700"
        }
        data = _parse_lender_policy_row(row, "Lender")
        # Should default to "BL"
        assert data["product_name"] == "BL"

    def test_malformed_age_range(self):
        """Test handling of malformed age ranges."""
        assert parse_age_range("invalid") == (None, None)
        assert parse_age_range("21-70-80") == (21, 70)  # Takes first two numbers


# ═══════════════════════════════════════════════════════════════
# SAMPLE DATA FOR MANUAL TESTING
# ═══════════════════════════════════════════════════════════════

SAMPLE_LENDER_POLICY_CSV = """Lender,Product Program,Min. Vintage,Min. Score,Min. Turnover,Max Ticket size,Disb Till date,ABB,Entity,Age,Minimum Turnover,No 30+,60+,90+,Enquiries,No Overdues,EMI bounce,Bureau Check,Banking Statement,Bank Source,Ownership Proof,GST,Tele PD,Video KYC,FI,KYC Doc,Tenor Min,Tenor Max
Indifi,BL,2,650,24L,30L,500,>=25k,Pvt Ltd LLP Proprietorship,22-65,24L,6 months,12 months,12 months,Max 5 in 6m,NA,Max 2,Standard,6 months,AA PDF,NA,Mandatory,Yes,No,NA,PAN Aadhaar,12,36
Bajaj,STBL,2,700,36L,50L,1000,>=50k,Pvt Ltd LLP,21-65,36L,6 months,12 months,12 months,Max 3,NA,Max 1,Strict,12 months,AA,Yes,Mandatory,Yes,Yes,Yes,PAN Aadhaar Udyam,12,48
Credit Saison,Digital,1.5,680,18L,25L,300,>=30k,All,22-60,18L,6 months,12 months,12 months,Max 4,NA,Max 2,Standard,6 months,AA PDF Scorme,NA,Yes,Yes,No,NA,PAN Aadhaar,6,36
FT Cash,BL,Policy not available,NA,NA,NA,NA,NA,NA,NA,NA,NA,NA,NA,NA,NA,NA,NA,NA,NA,NA,NA,NA,NA,NA,NA,NA,NA"""

SAMPLE_PINCODE_CSV = """GODREJ,LENDINGKART,FLEXILOANS,INDIFI,BAJAJ
110001,110001,110001,110001,110001
110002,110002,110002,110002,110002
400001,400001,400001,400001,400001
Mumbai,Delhi,Bangalore,Chennai,Pune
560001,560001,560001,560001,560001"""
