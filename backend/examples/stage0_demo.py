"""
Demo script for Stage 0: Case Entry API

This script demonstrates how to:
1. Create a new case
2. Upload files (PDF, images, ZIP archives)
3. List cases
4. Get case details
5. Update case information
6. Handle errors gracefully
"""
import asyncio
import httpx
from pathlib import Path
import io
import zipfile

# API base URL
BASE_URL = "http://localhost:8000/api/v1"


async def create_test_files():
    """Create sample test files for demonstration."""
    # Create a simple PDF
    pdf_content = b"%PDF-1.4\n%Sample Document\n%%EOF"

    # Create a minimal PNG (1x1 red pixel)
    png_content = (
        b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01'
        b'\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\xcf'
        b'\xc0\x00\x00\x00\x03\x00\x01\x00\x18\xdd\x8d\xb4\x00\x00\x00\x00IEND\xaeB`\x82'
    )

    # Create a ZIP file with multiple documents
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("bank_statement.pdf", b"%PDF-1.4\n%Bank Statement\n%%EOF")
        zf.writestr("gst_certificate.pdf", b"%PDF-1.4\n%GST Certificate\n%%EOF")
        zf.writestr("pan_card.jpg", png_content)
    zip_buffer.seek(0)

    return {
        "pan.pdf": pdf_content,
        "aadhaar.jpg": png_content,
        "documents.zip": zip_buffer.getvalue()
    }


async def demo_stage0_api():
    """Demonstrate Stage 0 API functionality."""

    async with httpx.AsyncClient() as client:
        print("=" * 60)
        print("Stage 0: Case Entry - API Demo")
        print("=" * 60)

        # 1. Create a new case
        print("\n1. Creating a new case...")
        try:
            response = await client.post(
                f"{BASE_URL}/cases/",
                json={
                    "borrower_name": "Rajesh Kumar",
                    "entity_type": "proprietorship",
                    "program_type": "banking",
                    "industry_type": "Retail",
                    "pincode": "110001",
                    "loan_amount_requested": 500000.0
                }
            )
            response.raise_for_status()
            case = response.json()
            case_id = case["case_id"]
            print(f"✓ Case created: {case_id}")
            print(f"  Status: {case['status']}")
            print(f"  Borrower: {case['borrower_name']}")

        except httpx.HTTPError as e:
            print(f"✗ Failed to create case: {e}")
            return

        # 2. Upload files to the case
        print(f"\n2. Uploading files to case {case_id}...")
        try:
            test_files = await create_test_files()

            files = [
                ("files", ("pan.pdf", io.BytesIO(test_files["pan.pdf"]), "application/pdf")),
                ("files", ("aadhaar.jpg", io.BytesIO(test_files["aadhaar.jpg"]), "image/jpeg")),
                ("files", ("documents.zip", io.BytesIO(test_files["documents.zip"]), "application/zip"))
            ]

            response = await client.post(
                f"{BASE_URL}/cases/{case_id}/upload",
                files=files
            )
            response.raise_for_status()
            documents = response.json()

            print(f"✓ Uploaded {len(documents)} documents:")
            for doc in documents:
                print(f"  - {doc['original_filename']} ({doc['status']})")

        except httpx.HTTPError as e:
            print(f"✗ Failed to upload files: {e}")

        # 3. List all cases
        print("\n3. Listing all cases...")
        try:
            response = await client.get(f"{BASE_URL}/cases/")
            response.raise_for_status()
            cases = response.json()

            print(f"✓ Found {len(cases)} case(s):")
            for c in cases:
                print(f"  - {c['case_id']}: {c['borrower_name'] or 'Unnamed'} ({c['status']})")

        except httpx.HTTPError as e:
            print(f"✗ Failed to list cases: {e}")

        # 4. Get case details
        print(f"\n4. Getting details for case {case_id}...")
        try:
            response = await client.get(f"{BASE_URL}/cases/{case_id}")
            response.raise_for_status()
            case_details = response.json()

            print(f"✓ Case details:")
            print(f"  ID: {case_details['case_id']}")
            print(f"  Status: {case_details['status']}")
            print(f"  Borrower: {case_details['borrower_name']}")
            print(f"  Program: {case_details['program_type']}")
            print(f"  Completeness: {case_details['completeness_score']}%")
            print(f"  Created: {case_details['created_at']}")

        except httpx.HTTPError as e:
            print(f"✗ Failed to get case details: {e}")

        # 5. Update case with manual overrides
        print(f"\n5. Updating case {case_id} with manual data...")
        try:
            response = await client.patch(
                f"{BASE_URL}/cases/{case_id}",
                json={
                    "cibil_score_manual": 750,
                    "monthly_turnover_manual": 500000.0,
                    "business_vintage_years": 5.0
                }
            )
            response.raise_for_status()
            updated_case = response.json()

            print(f"✓ Case updated successfully")
            print(f"  Updated at: {updated_case['updated_at']}")

        except httpx.HTTPError as e:
            print(f"✗ Failed to update case: {e}")

        # 6. Demonstrate error handling - try to get non-existent case
        print("\n6. Testing error handling (non-existent case)...")
        try:
            response = await client.get(f"{BASE_URL}/cases/CASE-20240210-9999")
            response.raise_for_status()
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                print(f"✓ Correctly returned 404 for non-existent case")
            else:
                print(f"✗ Unexpected error: {e}")

        # 7. Demonstrate duplicate file detection
        print("\n7. Testing duplicate file detection...")
        try:
            # Upload the same file twice
            duplicate_file = io.BytesIO(test_files["pan.pdf"])
            files = [
                ("files", ("pan_duplicate.pdf", duplicate_file, "application/pdf"))
            ]

            response = await client.post(
                f"{BASE_URL}/cases/{case_id}/upload",
                files=files
            )
            response.raise_for_status()
            documents = response.json()

            if len(documents) == 0:
                print(f"✓ Duplicate file correctly detected and skipped")
            else:
                print(f"✗ Duplicate was not detected")

        except httpx.HTTPError as e:
            print(f"✗ Failed to test duplicate detection: {e}")

        print("\n" + "=" * 60)
        print("Demo completed!")
        print("=" * 60)


async def demo_file_size_validation():
    """Demonstrate file size validation."""
    print("\n" + "=" * 60)
    print("File Size Validation Demo")
    print("=" * 60)

    async with httpx.AsyncClient() as client:
        # Create a case first
        response = await client.post(
            f"{BASE_URL}/cases/",
            json={"borrower_name": "Size Test User"}
        )
        case = response.json()
        case_id = case["case_id"]

        print(f"\n1. Testing oversized file (will be skipped)...")
        # Create a 26MB file (exceeds 25MB limit)
        large_content = b"x" * (26 * 1024 * 1024)
        large_file = io.BytesIO(large_content)

        files = [
            ("files", ("large_file.pdf", large_file, "application/pdf"))
        ]

        response = await client.post(
            f"{BASE_URL}/cases/{case_id}/upload",
            files=files
        )

        documents = response.json()
        if len(documents) == 0:
            print(f"✓ Oversized file correctly rejected")
        else:
            print(f"✗ Oversized file was not rejected")


if __name__ == "__main__":
    print("\nMake sure the FastAPI server is running on http://localhost:8000")
    print("Start it with: uvicorn app.main:app --reload\n")

    # Run the main demo
    asyncio.run(demo_stage0_api())

    # Uncomment to run file size validation demo
    # asyncio.run(demo_file_size_validation())
