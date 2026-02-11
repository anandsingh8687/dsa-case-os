#!/usr/bin/env python3
"""
End-to-end verification script for Stage 2 extraction pipeline.
This script validates the entire extraction flow without requiring a running server.
"""
import asyncio
import sys
from datetime import datetime
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent))

from app.services.stages.stage2_extraction import FieldExtractor, get_extractor
from app.services.stages.stage2_features import FeatureAssembler, get_assembler
from app.schemas.shared import ExtractedFieldItem
from app.core.enums import DocumentType


# Sample OCR data for verification
SAMPLE_DOCUMENTS = {
    "PAN_CARD": {
        "type": DocumentType.PAN_PERSONAL,
        "ocr_text": """
        INCOME TAX DEPARTMENT
        GOVT. OF INDIA

        Permanent Account Number Card
        Name: RAJESH KUMAR SHARMA
        Father's Name: MOHAN LAL SHARMA
        Date of Birth: 15/03/1985
        ABCDE1234F
        """,
        "expected_fields": ["pan_number", "full_name", "dob"]
    },
    "AADHAAR": {
        "type": DocumentType.AADHAAR,
        "ocr_text": """
        Government of India
        Aadhaar
        1234 5678 9012

        Name: Priya Singh
        DOB: 22/07/1990
        Address: 123 MG Road
        Bangalore
        Karnataka - 560001
        """,
        "expected_fields": ["aadhaar_number", "full_name", "dob"]
    },
    "GST_CERTIFICATE": {
        "type": DocumentType.GST_CERTIFICATE,
        "ocr_text": """
        GST Registration Certificate

        GSTIN: 29ABCDE1234F1Z5
        Legal Name of Business: TECH SOLUTIONS PRIVATE LIMITED
        Trade Name: Tech Solutions
        Date of Registration: 01/04/2018
        State: Karnataka (29)
        """,
        "expected_fields": ["gstin", "business_name", "gst_registration_date", "state"]
    },
    "CIBIL_REPORT": {
        "type": DocumentType.CIBIL_REPORT,
        "ocr_text": """
        CIBIL TransUnion Score Report
        Credit Score: 756

        Account Summary:
        Active Accounts: 4
        Closed Accounts: 2
        Overdue Accounts: 0

        Credit Enquiries (Last 6 months): 2
        """,
        "expected_fields": ["cibil_score", "active_loan_count", "overdue_count", "enquiry_count_6m"]
    },
    "ITR": {
        "type": DocumentType.ITR,
        "ocr_text": """
        INCOME TAX RETURN
        Assessment Year: 2023-24
        PAN: ABCDE1234F

        Income Details:
        Gross Total Income: Rs. 18,50,000
        Income from Business: Rs. 15,00,000

        Tax Computation:
        Total Tax Paid: Rs. 2,75,000
        """,
        "expected_fields": ["itr_total_income", "itr_assessment_year", "itr_tax_paid", "itr_business_income"]
    }
}


async def verify_extraction():
    """Verify field extraction from sample documents."""
    print("=" * 70)
    print("STAGE 2 EXTRACTION PIPELINE VERIFICATION")
    print("=" * 70)
    print()

    extractor = get_extractor()
    all_passed = True

    for doc_name, doc_data in SAMPLE_DOCUMENTS.items():
        print(f"\n📄 Testing {doc_name}...")
        print("-" * 70)

        try:
            # Extract fields
            fields = await extractor.extract_fields(
                doc_data["ocr_text"],
                doc_data["type"]
            )

            # Validate extraction
            extracted_field_names = [f.field_name for f in fields]

            print(f"✓ Extracted {len(fields)} fields")

            # Check expected fields
            missing_fields = []
            for expected_field in doc_data["expected_fields"]:
                if expected_field in extracted_field_names:
                    field = next(f for f in fields if f.field_name == expected_field)
                    print(f"  ✓ {expected_field}: {field.field_value} (confidence: {field.confidence:.2f})")
                else:
                    missing_fields.append(expected_field)
                    print(f"  ✗ {expected_field}: NOT FOUND")
                    all_passed = False

            if missing_fields:
                print(f"\n❌ Missing fields: {', '.join(missing_fields)}")
            else:
                print(f"\n✅ All expected fields extracted successfully")

        except Exception as e:
            print(f"\n❌ Error during extraction: {str(e)}")
            all_passed = False

    print("\n" + "=" * 70)

    if all_passed:
        print("✅ ALL VERIFICATION TESTS PASSED")
    else:
        print("❌ SOME VERIFICATION TESTS FAILED")

    print("=" * 70)

    return all_passed


async def verify_validation():
    """Verify field validation logic."""
    print("\n" + "=" * 70)
    print("VALIDATION LOGIC VERIFICATION")
    print("=" * 70)
    print()

    extractor = FieldExtractor()
    all_passed = True

    # Test PAN validation
    print("Testing PAN validation...")
    test_cases = [
        ("ABCDE1234F", True, "Valid PAN"),
        ("ABCXE1234F", False, "Invalid entity type"),
        ("ABCDE123", False, "Wrong length"),
        ("123ABCDEFG", False, "Wrong format"),
    ]

    for pan, expected, description in test_cases:
        result = extractor._validate_pan(pan)
        status = "✓" if result == expected else "✗"
        print(f"  {status} {description}: {pan} → {result}")
        if result != expected:
            all_passed = False

    # Test GSTIN validation
    print("\nTesting GSTIN validation...")
    test_cases = [
        ("29ABCDE1234F1Z5", True, "Valid GSTIN"),
        ("99ABCDE1234F1Z5", False, "Invalid state code"),
        ("29ABCDE1234F1Z", False, "Wrong length"),
        ("29ABCXE1234F1Z5", False, "Invalid embedded PAN"),
    ]

    for gstin, expected, description in test_cases:
        result = extractor._validate_gstin(gstin)
        status = "✓" if result == expected else "✗"
        print(f"  {status} {description}: {gstin} → {result}")
        if result != expected:
            all_passed = False

    # Test CIBIL score validation
    print("\nTesting CIBIL score validation...")
    test_cases = [
        ("750", True, "Valid score"),
        ("300", True, "Minimum score"),
        ("900", True, "Maximum score"),
        ("250", False, "Too low"),
        ("950", False, "Too high"),
    ]

    for score, expected, description in test_cases:
        field = ExtractedFieldItem(
            field_name="cibil_score",
            field_value=score,
            confidence=0.9,
            source="extraction"
        )
        result = extractor._validate_field(field)
        status = "✓" if result == expected else "✗"
        print(f"  {status} {description}: {score} → {result}")
        if result != expected:
            all_passed = False

    print("\n" + "=" * 70)

    if all_passed:
        print("✅ ALL VALIDATION TESTS PASSED")
    else:
        print("❌ SOME VALIDATION TESTS FAILED")

    print("=" * 70)

    return all_passed


async def verify_type_conversion():
    """Verify type conversion logic."""
    print("\n" + "=" * 70)
    print("TYPE CONVERSION VERIFICATION")
    print("=" * 70)
    print()

    assembler = FeatureAssembler()
    all_passed = True

    # Test date conversion
    print("Testing date conversion...")
    test_cases = [
        ("15/03/1985", "dob", "Valid date"),
        ("22-07-1990", "dob", "Date with hyphens"),
    ]

    for value, field_name, description in test_cases:
        try:
            result = assembler._convert_field_type(field_name, value)
            print(f"  ✓ {description}: {value} → {result} (type: {type(result).__name__})")
        except Exception as e:
            print(f"  ✗ {description}: {value} → Error: {str(e)}")
            all_passed = False

    # Test numeric conversion
    print("\nTesting numeric conversion...")
    test_cases = [
        ("1,25,00,000", "annual_turnover", "Indian number format"),
        ("12500000", "annual_turnover", "Plain number"),
        ("750", "cibil_score", "Integer field"),
        ("4.0", "active_loan_count", "Float to int conversion"),
    ]

    for value, field_name, description in test_cases:
        try:
            result = assembler._convert_field_type(field_name, value)
            print(f"  ✓ {description}: {value} → {result} (type: {type(result).__name__})")
        except Exception as e:
            print(f"  ✗ {description}: {value} → Error: {str(e)}")
            all_passed = False

    print("\n" + "=" * 70)

    if all_passed:
        print("✅ ALL TYPE CONVERSION TESTS PASSED")
    else:
        print("❌ SOME TYPE CONVERSION TESTS FAILED")

    print("=" * 70)

    return all_passed


async def verify_priority_logic():
    """Verify extraction vs manual priority logic."""
    print("\n" + "=" * 70)
    print("PRIORITY LOGIC VERIFICATION")
    print("=" * 70)
    print()

    assembler = FeatureAssembler()
    all_passed = True

    test_cases = [
        {
            "description": "High-confidence extraction overrides manual",
            "extracted": ExtractedFieldItem(
                field_name="cibil_score",
                field_value="750",
                confidence=0.9,
                source="extraction"
            ),
            "manual": 720,
            "expected": "750"
        },
        {
            "description": "Low-confidence extraction loses to manual",
            "extracted": ExtractedFieldItem(
                field_name="cibil_score",
                field_value="650",
                confidence=0.3,
                source="extraction"
            ),
            "manual": 720,
            "expected": "720"
        },
        {
            "description": "Low-confidence extraction used when no manual",
            "extracted": ExtractedFieldItem(
                field_name="cibil_score",
                field_value="650",
                confidence=0.3,
                source="extraction"
            ),
            "manual": None,
            "expected": "650"
        },
        {
            "description": "Manual value used when no extraction",
            "extracted": None,
            "manual": 720,
            "expected": "720"
        }
    ]

    for test in test_cases:
        result = assembler._resolve_field_value(
            field_name="cibil_score",
            extracted=test["extracted"],
            manual=test["manual"]
        )

        status = "✓" if result == test["expected"] else "✗"
        print(f"{status} {test['description']}")
        print(f"   Expected: {test['expected']}, Got: {result}")

        if result != test["expected"]:
            all_passed = False

    print("\n" + "=" * 70)

    if all_passed:
        print("✅ ALL PRIORITY LOGIC TESTS PASSED")
    else:
        print("❌ SOME PRIORITY LOGIC TESTS FAILED")

    print("=" * 70)

    return all_passed


async def main():
    """Run all verification tests."""
    print("\n")
    print("╔" + "=" * 68 + "╗")
    print("║" + " " * 15 + "STAGE 2 EXTRACTION ENGINE VERIFICATION" + " " * 15 + "║")
    print("╚" + "=" * 68 + "╝")
    print("\nThis script verifies the extraction engine without requiring database setup.")
    print("For full integration tests, run: pytest tests/test_extraction.py")
    print()

    results = []

    # Run all verification tests
    results.append(("Field Extraction", await verify_extraction()))
    results.append(("Field Validation", await verify_validation()))
    results.append(("Type Conversion", await verify_type_conversion()))
    results.append(("Priority Logic", await verify_priority_logic()))

    # Summary
    print("\n" + "=" * 70)
    print("VERIFICATION SUMMARY")
    print("=" * 70)
    print()

    all_passed = True
    for test_name, passed in results:
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{status}: {test_name}")
        if not passed:
            all_passed = False

    print("\n" + "=" * 70)

    if all_passed:
        print("🎉 ALL VERIFICATION TESTS PASSED!")
        print("\nThe extraction engine is working correctly.")
        print("\nNext steps:")
        print("  1. Set up database: createdb dsa_case_os_test")
        print("  2. Install dependencies: pip install -r requirements.txt")
        print("  3. Run full tests: pytest tests/test_extraction.py -v")
        print("  4. Start server and test API endpoints")
        return 0
    else:
        print("⚠️  SOME TESTS FAILED")
        print("\nPlease review the failed tests above and fix the issues.")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
