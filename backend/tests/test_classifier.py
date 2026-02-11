"""
Tests for the Document Classifier.
Tests both keyword-based and ML-based classification.
"""
import pytest
from pathlib import Path
import sys

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.services.stages.stage1_classifier import (
    DocumentClassifier,
    ClassificationResult,
    classify_document,
)
from app.core.enums import DocumentType


# ─── Test Data ────────────────────────────────────────────────────────────────

# Synthetic test texts for each document type
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
    DocumentType.PAN_PERSONAL: """
        INCOME TAX DEPARTMENT
        GOVERNMENT OF INDIA
        Permanent Account Number Card
        Name: RAJESH KUMAR
        Father's Name: SURESH KUMAR
        Date of Birth: 15/08/1985
        PAN: ABCDE1234F
        Signature
        NSDL e-Gov
    """,
    DocumentType.PAN_BUSINESS: """
        INCOME TAX DEPARTMENT
        Permanent Account Number Card
        Name: TECH SOLUTIONS PVT LTD
        PAN: AAACT1234C
        Application Type: Company
        Date of Incorporation: 01/04/2010
        NSDL
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
    DocumentType.GST_RETURNS: """
        GSTR-3B
        Return Filing Period: July 2023
        GSTIN: 29AAACT1234C1Z5
        Legal Name: TECH SOLUTIONS PVT LTD
        Outward Supplies
        Taxable Value: 5,00,000
        CGST: 45,000
        SGST: 45,000
        Total Tax: 90,000
        Filing Status: Filed
        Date of Filing: 20/08/2023
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
    DocumentType.ITR: """
        GOVERNMENT OF INDIA
        INCOME TAX DEPARTMENT
        Income Tax Return Acknowledgement
        ITR-3
        For Assessment Year: 2022-23
        PAN: ABCDE1234F
        Name: RAJESH KUMAR
        Filing Date: 31/07/2022
        Acknowledgement Number: 123456789012345
        Total Income: 12,50,000
        Tax Payable: 1,87,500
        Verification: I, RAJESH KUMAR, verify that the information given in this return is correct and complete
    """,
    DocumentType.FINANCIAL_STATEMENTS: """
        TECH SOLUTIONS PRIVATE LIMITED
        Balance Sheet as at 31st March 2023
        ASSETS
        Non-Current Assets
        Property, Plant & Equipment: 50,00,000
        Current Assets
        Inventories: 25,00,000
        Trade Receivables: 35,00,000
        Cash and Bank: 15,00,000
        Total Assets: 1,25,00,000
        LIABILITIES
        Equity Share Capital: 50,00,000
        Reserves and Surplus: 40,00,000
        Current Liabilities
        Trade Payables: 25,00,000
        Short-term Borrowings: 10,00,000
        Total Equity and Liabilities: 1,25,00,000
        For ABC & Associates Chartered Accountants
        Audit Report: True and Fair View
    """,
    DocumentType.CIBIL_REPORT: """
        TransUnion CIBIL
        Credit Information Report
        Report Date: 15/08/2023
        Name: RAJESH KUMAR
        PAN: ABCDE1234F
        Date of Birth: 15/08/1985
        CIBIL Score: 785
        Credit Score Factors:
        1. Good payment history
        2. Low credit utilization
        Account Summary
        Total Accounts: 5
        Active Accounts: 3
        Closed Accounts: 2
        Credit History Length: 8 years
        Enquiry History
        Last 6 months: 2 enquiries
        Credit Exposure
        Total Amount: 15,00,000
        Outstanding: 3,50,000
    """,
    DocumentType.UDYAM_SHOP_LICENSE: """
        GOVERNMENT OF INDIA
        MINISTRY OF MICRO, SMALL & MEDIUM ENTERPRISES
        Udyam Registration Certificate
        Udyam Registration Number: UDYAM-KA-12-1234567
        Name of Enterprise: Tech Solutions
        Type of Organisation: Private Limited Company
        Date of Commencement: 01/04/2010
        Major Activity: Manufacturing
        Classification: Medium Enterprise
        Official Email: info@techsolutions.com
        Mobile: +91-9876543210
        This is a system generated certificate and does not require signature
    """,
    DocumentType.PROPERTY_DOCUMENTS: """
        SUB-REGISTRAR OFFICE
        Sale Deed Registration
        Document No: 1234/2023
        Date of Registration: 15/03/2023
        This Sale Deed is executed on 15th March 2023
        BETWEEN
        Vendor: SURESH KUMAR S/o RAM KUMAR
        AND
        Purchaser: RAJESH KUMAR S/o SURESH KUMAR
        Property Details:
        Plot No: 123
        Survey Number: 456/2
        Location: Sector 45, Gurgaon, Haryana
        Area: 200 Sq Yards
        Consideration Amount: Rs. 75,00,000/-
        Stamp Duty Paid: Rs. 3,75,000
        Registration Fee: Rs. 30,000
        Sub-Registrar Signature and Seal
    """,
}


# ─── Test Cases ───────────────────────────────────────────────────────────────

class TestKeywordClassifier:
    """Test keyword-based classification."""

    def setup_method(self):
        """Create a classifier instance for testing."""
        # Create classifier without ML model (keyword-only)
        self.classifier = DocumentClassifier(model_path="/tmp/nonexistent_model_path")
        assert not self.classifier.ml_available, "ML should not be available for keyword tests"

    def test_aadhaar_classification(self):
        """Test Aadhaar card classification."""
        result = self.classifier.classify(TEST_TEXTS[DocumentType.AADHAAR])
        assert result.doc_type == DocumentType.AADHAAR
        assert result.confidence >= 0.80
        assert result.method == "keyword"

    def test_pan_personal_classification(self):
        """Test personal PAN card classification."""
        result = self.classifier.classify(TEST_TEXTS[DocumentType.PAN_PERSONAL])
        assert result.doc_type == DocumentType.PAN_PERSONAL
        assert result.confidence >= 0.80
        assert result.method == "keyword"

    def test_pan_business_classification(self):
        """Test business PAN card classification."""
        result = self.classifier.classify(TEST_TEXTS[DocumentType.PAN_BUSINESS])
        assert result.doc_type == DocumentType.PAN_BUSINESS
        assert result.confidence >= 0.80
        assert result.method == "keyword"

    def test_gst_certificate_classification(self):
        """Test GST certificate classification."""
        result = self.classifier.classify(TEST_TEXTS[DocumentType.GST_CERTIFICATE])
        assert result.doc_type == DocumentType.GST_CERTIFICATE
        assert result.confidence >= 0.80
        assert result.method == "keyword"

    def test_gst_returns_classification(self):
        """Test GST returns classification."""
        result = self.classifier.classify(TEST_TEXTS[DocumentType.GST_RETURNS])
        assert result.doc_type == DocumentType.GST_RETURNS
        assert result.confidence >= 0.85
        assert result.method == "keyword"

    def test_bank_statement_classification(self):
        """Test bank statement classification."""
        result = self.classifier.classify(TEST_TEXTS[DocumentType.BANK_STATEMENT])
        assert result.doc_type == DocumentType.BANK_STATEMENT
        assert result.confidence >= 0.85
        assert result.method == "keyword"

    def test_itr_classification(self):
        """Test ITR classification."""
        result = self.classifier.classify(TEST_TEXTS[DocumentType.ITR])
        assert result.doc_type == DocumentType.ITR
        assert result.confidence >= 0.80
        assert result.method == "keyword"

    def test_financial_statements_classification(self):
        """Test financial statements classification."""
        result = self.classifier.classify(TEST_TEXTS[DocumentType.FINANCIAL_STATEMENTS])
        assert result.doc_type == DocumentType.FINANCIAL_STATEMENTS
        assert result.confidence >= 0.75
        assert result.method == "keyword"

    def test_cibil_classification(self):
        """Test CIBIL report classification."""
        result = self.classifier.classify(TEST_TEXTS[DocumentType.CIBIL_REPORT])
        assert result.doc_type == DocumentType.CIBIL_REPORT
        assert result.confidence >= 0.85
        assert result.method == "keyword"

    def test_udyam_classification(self):
        """Test Udyam/MSME license classification."""
        result = self.classifier.classify(TEST_TEXTS[DocumentType.UDYAM_SHOP_LICENSE])
        assert result.doc_type == DocumentType.UDYAM_SHOP_LICENSE
        assert result.confidence >= 0.75
        assert result.method == "keyword"

    def test_property_documents_classification(self):
        """Test property documents classification."""
        result = self.classifier.classify(TEST_TEXTS[DocumentType.PROPERTY_DOCUMENTS])
        assert result.doc_type == DocumentType.PROPERTY_DOCUMENTS
        assert result.confidence >= 0.70
        assert result.method == "keyword"

    def test_unknown_document(self):
        """Test unknown/unrecognizable document."""
        unknown_text = "Lorem ipsum dolor sit amet consectetur adipiscing elit"
        result = self.classifier.classify(unknown_text)
        # Should either be unknown or have low confidence
        assert result.doc_type == DocumentType.UNKNOWN or result.confidence < 0.70

    def test_empty_text(self):
        """Test empty text handling."""
        result = self.classifier.classify("")
        assert result.doc_type == DocumentType.UNKNOWN
        assert result.confidence == 0.0

    def test_minimal_text(self):
        """Test minimal text (below threshold)."""
        result = self.classifier.classify("Short")
        assert result.doc_type == DocumentType.UNKNOWN
        assert result.confidence == 0.0


class TestClassificationResult:
    """Test ClassificationResult dataclass."""

    def test_result_creation(self):
        """Test creating a classification result."""
        result = ClassificationResult(
            doc_type=DocumentType.AADHAAR,
            confidence=0.95,
            method="ml",
            scores={"aadhaar": 0.95, "pan_personal": 0.05}
        )
        assert result.doc_type == DocumentType.AADHAAR
        assert result.confidence == 0.95
        assert result.method == "ml"
        assert result.scores is not None


class TestConvenienceFunctions:
    """Test convenience functions."""

    def test_classify_document_function(self):
        """Test the classify_document convenience function."""
        result = classify_document(TEST_TEXTS[DocumentType.AADHAAR])
        assert isinstance(result, ClassificationResult)
        assert result.doc_type == DocumentType.AADHAAR


class TestEdgeCases:
    """Test edge cases and error handling."""

    def setup_method(self):
        """Create a classifier instance for testing."""
        self.classifier = DocumentClassifier(model_path="/tmp/nonexistent_model_path")

    def test_case_insensitive_matching(self):
        """Test that matching is case-insensitive."""
        lowercase_text = TEST_TEXTS[DocumentType.AADHAAR].lower()
        result = self.classifier.classify(lowercase_text)
        assert result.doc_type == DocumentType.AADHAAR

    def test_special_characters(self):
        """Test handling of special characters."""
        text_with_special = TEST_TEXTS[DocumentType.AADHAAR] + "!@#$%^&*()"
        result = self.classifier.classify(text_with_special)
        assert result.doc_type == DocumentType.AADHAAR

    def test_multilingual_text(self):
        """Test handling of multilingual content (Hindi in Aadhaar)."""
        # Aadhaar text includes आधार
        result = self.classifier.classify(TEST_TEXTS[DocumentType.AADHAAR])
        assert result.doc_type == DocumentType.AADHAAR

    def test_very_long_text(self):
        """Test handling of very long text."""
        long_text = TEST_TEXTS[DocumentType.BANK_STATEMENT] * 100
        result = self.classifier.classify(long_text)
        # Should still classify correctly
        assert result.doc_type == DocumentType.BANK_STATEMENT


class TestPANDisambiguation:
    """Test PAN personal vs business disambiguation."""

    def setup_method(self):
        """Create a classifier instance for testing."""
        self.classifier = DocumentClassifier(model_path="/tmp/nonexistent_model_path")

    def test_pan_personal_no_business_terms(self):
        """Test that PAN without business terms is classified as personal."""
        result = self.classifier.classify(TEST_TEXTS[DocumentType.PAN_PERSONAL])
        assert result.doc_type == DocumentType.PAN_PERSONAL

    def test_pan_business_with_pvt_ltd(self):
        """Test that PAN with 'Pvt Ltd' is classified as business."""
        result = self.classifier.classify(TEST_TEXTS[DocumentType.PAN_BUSINESS])
        assert result.doc_type == DocumentType.PAN_BUSINESS

    def test_pan_business_with_partnership(self):
        """Test that PAN with 'Partnership' is classified as business."""
        partnership_pan = """
            INCOME TAX DEPARTMENT
            Permanent Account Number
            Name: SHARMA TRADING PARTNERSHIP
            PAN: AABFS9876D
            Business Type: Partnership Firm
        """
        result = self.classifier.classify(partnership_pan)
        assert result.doc_type == DocumentType.PAN_BUSINESS


# ─── Performance Tests ────────────────────────────────────────────────────────

class TestPerformance:
    """Test classification performance metrics."""

    def setup_method(self):
        """Create a classifier instance for testing."""
        self.classifier = DocumentClassifier(model_path="/tmp/nonexistent_model_path")

    def test_all_documents_classify_correctly(self):
        """Test that all test documents classify to their expected types."""
        correct = 0
        total = 0

        for expected_type, text in TEST_TEXTS.items():
            result = self.classifier.classify(text)
            if result.doc_type == expected_type:
                correct += 1
            else:
                print(f"MISMATCH: Expected {expected_type}, got {result.doc_type} (confidence: {result.confidence})")
            total += 1

        accuracy = correct / total
        print(f"\nKeyword Classifier Accuracy: {accuracy:.2%} ({correct}/{total})")

        # Should achieve at least 90% accuracy on test set
        assert accuracy >= 0.90, f"Accuracy {accuracy:.2%} is below 90% threshold"


# ─── Integration Tests ────────────────────────────────────────────────────────

class TestIntegration:
    """Integration tests for the complete classification pipeline."""

    def test_full_classification_pipeline(self):
        """Test the complete classification flow."""
        # Simulate document upload → OCR → Classification
        ocr_text = TEST_TEXTS[DocumentType.BANK_STATEMENT]

        # Classify
        result = classify_document(ocr_text)

        # Verify result structure
        assert isinstance(result, ClassificationResult)
        assert isinstance(result.doc_type, DocumentType)
        assert 0.0 <= result.confidence <= 1.0
        assert result.method in ["ml", "keyword", "empty_input"]

        # Verify correct classification
        assert result.doc_type == DocumentType.BANK_STATEMENT


if __name__ == "__main__":
    # Run tests with pytest
    pytest.main([__file__, "-v", "--tb=short"])
