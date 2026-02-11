#!/usr/bin/env python3
"""
Simple test runner for the classifier (doesn't require pytest).
Runs basic tests to verify the classifier is working correctly.
"""
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.services.stages.stage1_classifier import DocumentClassifier, classify_document
from app.core.enums import DocumentType


# Test texts
TEST_TEXTS = {
    DocumentType.AADHAAR: """
        GOVERNMENT OF INDIA UNIQUE IDENTIFICATION AUTHORITY OF INDIA
        Aadhaar Card Name: RAJESH KUMAR Date of Birth: 15/08/1985
        Address: House No 123, Sector 45, Gurgaon PIN: 122003
        Aadhaar Number: 1234 5678 9012 आधार
    """,
    DocumentType.PAN_PERSONAL: """
        INCOME TAX DEPARTMENT GOVERNMENT OF INDIA
        Permanent Account Number Card Name: RAJESH KUMAR
        Father's Name: SURESH KUMAR PAN: ABCDE1234F NSDL e-Gov
    """,
    DocumentType.PAN_BUSINESS: """
        INCOME TAX DEPARTMENT Permanent Account Number Card
        Name: TECH SOLUTIONS PVT LTD PAN: AAACT1234C
        Application Type: Company NSDL
    """,
    DocumentType.GST_CERTIFICATE: """
        GOVERNMENT OF INDIA GOODS AND SERVICES TAX
        Certificate of Registration GSTIN: 29AAACT1234C1Z5
        Legal Name: TECH SOLUTIONS PRIVATE LIMITED Date of Registration: 01/07/2017
    """,
    DocumentType.GST_RETURNS: """
        GSTR-3B Return Filing Period: July 2023 GSTIN: 29AAACT1234C1Z5
        Taxable Value: 5,00,000 CGST: 45,000 SGST: 45,000
        Filing Status: Filed
    """,
    DocumentType.BANK_STATEMENT: """
        HDFC BANK LIMITED Statement of Account
        Account Number: 1234567890123 IFSC Code: HDFC0001234
        Opening Balance: 5,00,000.00 Closing Balance: 5,50,000.00
        Date | Description | Debit | Credit | Balance
    """,
    DocumentType.ITR: """
        GOVERNMENT OF INDIA INCOME TAX DEPARTMENT
        Income Tax Return Acknowledgement ITR-3
        Assessment Year: 2022-23 PAN: ABCDE1234F Total Income: 12,50,000
        Acknowledgement Number: 123456789012345 Verification
    """,
    DocumentType.FINANCIAL_STATEMENTS: """
        TECH SOLUTIONS PRIVATE LIMITED Balance Sheet as at 31st March 2023
        ASSETS Property, Plant & Equipment: 50,00,000
        LIABILITIES Equity Share Capital: 50,00,000
        Audit Report: True and Fair View For ABC & Associates Chartered Accountants
    """,
    DocumentType.CIBIL_REPORT: """
        TransUnion CIBIL Credit Information Report
        Name: RAJESH KUMAR CIBIL Score: 785
        Credit Score Factors Account Summary Total Accounts: 5
        Enquiry History Credit Exposure
    """,
    DocumentType.UDYAM_SHOP_LICENSE: """
        GOVERNMENT OF INDIA MINISTRY OF MICRO, SMALL & MEDIUM ENTERPRISES
        Udyam Registration Certificate UDYAM-KA-12-1234567
        Name of Enterprise: Tech Solutions Classification: Medium Enterprise
        MSME
    """,
    DocumentType.PROPERTY_DOCUMENTS: """
        SUB-REGISTRAR OFFICE Sale Deed Registration
        Document No: 1234/2023 Plot No: 123 Survey Number: 456/2
        Consideration Amount: Rs. 75,00,000/- Stamp Duty Paid: Rs. 3,75,000
        Registration Fee: Rs. 30,000
    """,
}


def run_tests():
    """Run basic classification tests."""
    print("=" * 80)
    print("Running Document Classifier Tests")
    print("=" * 80)
    print()

    # Initialize classifier
    print("Initializing classifier...")
    classifier = DocumentClassifier(model_path="/tmp/nonexistent_model_path")
    print(f"✓ Classifier initialized (ML available: {classifier.ml_available})")
    print()

    # Test each document type
    print("-" * 80)
    print("Testing classification for each document type...")
    print("-" * 80)
    print()

    passed = 0
    failed = 0
    failed_tests = []

    for expected_type, text in TEST_TEXTS.items():
        result = classifier.classify(text)

        status = "✓ PASS" if result.doc_type == expected_type else "✗ FAIL"
        print(f"{status:8s} {expected_type.value:25s} → {result.doc_type.value:25s} (conf: {result.confidence:.2%})")

        if result.doc_type == expected_type:
            passed += 1
        else:
            failed += 1
            failed_tests.append({
                "expected": expected_type.value,
                "got": result.doc_type.value,
                "confidence": result.confidence
            })

    print()
    print("-" * 80)
    print(f"Results: {passed} passed, {failed} failed")
    print("-" * 80)

    if failed > 0:
        print("\nFailed tests:")
        for test in failed_tests:
            print(f"  Expected: {test['expected']}, Got: {test['got']} (confidence: {test['confidence']:.2%})")

    # Calculate accuracy
    total = passed + failed
    accuracy = (passed / total) * 100 if total > 0 else 0

    print(f"\nOverall Accuracy: {accuracy:.1f}%")

    # Test edge cases
    print("\n" + "=" * 80)
    print("Testing edge cases...")
    print("=" * 80)
    print()

    # Test 1: Empty text
    result = classifier.classify("")
    if result.doc_type == DocumentType.UNKNOWN and result.confidence == 0.0:
        print("✓ PASS Empty text → UNKNOWN")
    else:
        print(f"✗ FAIL Empty text → {result.doc_type.value}")
        failed += 1

    # Test 2: Very short text
    result = classifier.classify("Short")
    if result.doc_type == DocumentType.UNKNOWN and result.confidence == 0.0:
        print("✓ PASS Short text → UNKNOWN")
    else:
        print(f"✗ FAIL Short text → {result.doc_type.value}")
        failed += 1

    # Test 3: Random text
    result = classifier.classify("Lorem ipsum dolor sit amet consectetur adipiscing elit")
    if result.doc_type == DocumentType.UNKNOWN or result.confidence < 0.70:
        print("✓ PASS Random text → UNKNOWN or low confidence")
    else:
        print(f"✗ FAIL Random text → {result.doc_type.value} (conf: {result.confidence:.2%})")
        failed += 1

    # Test 4: PAN business vs personal disambiguation
    business_pan = "INCOME TAX DEPARTMENT Permanent Account Number Name: SHARMA TRADING PARTNERSHIP PAN: AABFS9876D Business Type: Partnership Firm"
    result = classifier.classify(business_pan)
    if result.doc_type == DocumentType.PAN_BUSINESS:
        print("✓ PASS PAN with business terms → PAN_BUSINESS")
    else:
        print(f"✗ FAIL PAN with business terms → {result.doc_type.value}")
        failed += 1

    print()
    print("=" * 80)
    print("Test Summary")
    print("=" * 80)

    if failed == 0:
        print("🎉 All tests passed!")
        return 0
    else:
        print(f"⚠️  Some tests failed ({failed} failures)")
        return 1


def test_convenience_function():
    """Test the convenience function."""
    print("\n" + "=" * 80)
    print("Testing convenience function...")
    print("=" * 80)
    print()

    result = classify_document(TEST_TEXTS[DocumentType.AADHAAR])
    if result.doc_type == DocumentType.AADHAAR:
        print("✓ PASS classify_document() works correctly")
        return 0
    else:
        print(f"✗ FAIL classify_document() returned {result.doc_type.value}")
        return 1


if __name__ == "__main__":
    exit_code = run_tests()
    exit_code += test_convenience_function()

    print("\n" + "=" * 80)
    if exit_code == 0:
        print("✓ All tests completed successfully!")
    else:
        print("✗ Some tests failed")
    print("=" * 80)

    sys.exit(exit_code)
