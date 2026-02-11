#!/usr/bin/env python3
"""
Demo script showing how to use the document classifier.

This demonstrates the classification pipeline:
1. Get OCR text (simulated or from database)
2. Classify the document
3. Display results

Usage:
    python scripts/classify_document_demo.py
"""
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.services.stages.stage1_classifier import DocumentClassifier, classify_document
from app.core.enums import DocumentType


# Sample OCR texts for demonstration
SAMPLE_DOCUMENTS = {
    "aadhaar.pdf": """
        GOVERNMENT OF INDIA
        UNIQUE IDENTIFICATION AUTHORITY OF INDIA
        Aadhaar Card
        Name: RAJESH KUMAR
        Father's Name: SURESH KUMAR
        Date of Birth: 15/08/1985
        Address: House No 123, Sector 45, Gurgaon, Haryana PIN: 122003
        Aadhaar Number: 1234 5678 9012
        आधार
    """,
    "pan_card.pdf": """
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
    "bank_statement.pdf": """
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
        Closing Balance: 5,50,000.00
    """,
    "gst_certificate.pdf": """
        GOVERNMENT OF INDIA
        GOODS AND SERVICES TAX
        Certificate of Registration
        Registration Number (GSTIN): 29AAACT1234C1Z5
        Legal Name: TECH SOLUTIONS PRIVATE LIMITED
        Date of Registration: 01/07/2017
        State: Karnataka
    """,
}


def demo_classification():
    """Run classification demo on sample documents."""
    print("=" * 80)
    print("Document Classifier Demo")
    print("=" * 80)
    print()

    # Initialize classifier
    classifier = DocumentClassifier()

    print(f"Classifier initialized:")
    print(f"  ML Model available: {classifier.ml_available}")
    print(f"  Model path: {classifier.model_path}")
    print()

    print("=" * 80)
    print("Classifying sample documents...")
    print("=" * 80)
    print()

    # Classify each sample document
    for filename, ocr_text in SAMPLE_DOCUMENTS.items():
        print(f"📄 {filename}")
        print("-" * 80)

        # Classify
        result = classifier.classify(ocr_text)

        # Display results
        print(f"  Document Type:  {result.doc_type.value.upper()}")
        print(f"  Confidence:     {result.confidence:.2%}")
        print(f"  Method:         {result.method.upper()}")

        # Show top 3 scores if available
        if result.scores:
            sorted_scores = sorted(result.scores.items(), key=lambda x: x[1], reverse=True)[:3]
            print(f"  Top scores:")
            for doc_type, score in sorted_scores:
                print(f"    - {doc_type:25s}: {score:.2%}")

        print()

    print("=" * 80)


def demo_with_custom_text():
    """Demo with user-provided text."""
    print("\n" + "=" * 80)
    print("Custom Text Classification")
    print("=" * 80)
    print()
    print("Enter OCR text to classify (or press Ctrl+C to exit):")
    print("(Enter an empty line to finish input)")
    print()

    try:
        lines = []
        while True:
            line = input()
            if not line:
                break
            lines.append(line)

        if lines:
            ocr_text = "\n".join(lines)
            result = classify_document(ocr_text)

            print("\n" + "-" * 80)
            print("Classification Result:")
            print("-" * 80)
            print(f"  Document Type:  {result.doc_type.value.upper()}")
            print(f"  Confidence:     {result.confidence:.2%}")
            print(f"  Method:         {result.method.upper()}")

            if result.scores:
                sorted_scores = sorted(result.scores.items(), key=lambda x: x[1], reverse=True)[:5]
                print(f"\n  All scores:")
                for doc_type, score in sorted_scores:
                    print(f"    - {doc_type:25s}: {score:.2%}")

    except KeyboardInterrupt:
        print("\n\nExiting...")


def main():
    """Main function."""
    # Run demo with sample documents
    demo_classification()

    # Ask if user wants to try custom text
    try:
        response = input("Would you like to classify custom text? (y/n): ")
        if response.lower() in ['y', 'yes']:
            demo_with_custom_text()
    except KeyboardInterrupt:
        print("\n\nExiting...")

    print("\n" + "=" * 80)
    print("Demo completed!")
    print("=" * 80)


if __name__ == "__main__":
    main()
