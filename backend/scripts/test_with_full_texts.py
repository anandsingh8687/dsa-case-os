#!/usr/bin/env python3
"""Test with full comprehensive texts."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.services.stages.stage1_classifier import DocumentClassifier
from app.core.enums import DocumentType

# Full comprehensive test texts (from test_classifier.py)
TEST_TEXTS = {
    DocumentType.AADHAAR: """
        GOVERNMENT OF INDIA
        UNIQUE IDENTIFICATION AUTHORITY OF INDIA
        Aadhaar Card
        Name: RAJESH KUMAR
        Father's Name: SURESH KUMAR
        Date of Birth: 15/08/1985
        Address: House No 123, Sector 45, Gurgaon, Haryana PIN: 122003
        Aadhaar Number: 1234 5678 9012
        VID: 1234567890123456
        आधार
        Help@uidai.gov.in
    """,
    DocumentType.BANK_STATEMENT: """
        HDFC BANK LIMITED
        Statement of Account
        Account Number: 1234567890123
        Account Holder: TECH SOLUTIONS PVT LTD
        Branch: MG Road, Bangalore
        IFSC Code: HDFC0001234
        Statement Period: 01/01/2023 to 31/01/2023
        Opening Balance: 5,00,000.00
        Date | Description | Debit | Credit | Balance
        02/01/2023 | NEFT Transfer | 50,000.00 | | 4,50,000.00
        05/01/2023 | Payment Received | | 1,00,000.00 | 5,50,000.00
        Closing Balance: 5,50,000.00
    """,
    DocumentType.GST_CERTIFICATE: """
        GOVERNMENT OF INDIA
        GOODS AND SERVICES TAX
        Certificate of Registration
        Registration Number (GSTIN): 29AAACT1234C1Z5
        Legal Name: TECH SOLUTIONS PRIVATE LIMITED
        Trade Name: Tech Solutions
        Date of Registration: 01/07/2017
        State: Karnataka
        Tax Payer Type: Regular
        Address: 123 MG Road, Bangalore - 560001
    """,
}

print("Testing with comprehensive texts...")
print("=" * 80)

classifier = DocumentClassifier(model_path="/tmp/nonexistent")

passed = 0
total = 0

for expected_type, text in TEST_TEXTS.items():
    result = classifier.classify(text)
    total += 1
    status = "✓" if result.doc_type == expected_type else "✗"
    if result.doc_type == expected_type:
        passed += 1
    print(f"{status} Expected: {expected_type.value:25s} Got: {result.doc_type.value:25s} Conf: {result.confidence:.2%}")

print("=" * 80)
print(f"Passed: {passed}/{total} ({(passed/total*100):.1f}%)")
