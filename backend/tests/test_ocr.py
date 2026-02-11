"""Tests for OCR text extraction service."""
import pytest
import asyncio
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
import fitz  # PyMuPDF
import tempfile
import os

from app.services.stages.stage1_ocr import OCRService, ocr_service
from app.schemas.shared import OCRResult


@pytest.fixture
def temp_dir():
    """Create a temporary directory for test files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


@pytest.fixture
def sample_text_pdf(temp_dir):
    """Create a sample text-based PDF for testing."""
    pdf_path = os.path.join(temp_dir, "sample_text.pdf")

    # Create a simple text PDF using PyMuPDF
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)  # A4 size

    # Add text
    text = """Sample Invoice

Invoice Number: INV-2024-001
Date: 10-02-2024
Customer: ABC Enterprises
Amount: Rs. 50,000

This is a sample text-based PDF document for testing OCR extraction.
The document should be recognized as native PDF and extracted using PyMuPDF.
"""
    page.insert_text((50, 50), text, fontsize=12)
    doc.save(pdf_path)
    doc.close()

    yield pdf_path


@pytest.fixture
def sample_multipage_pdf(temp_dir):
    """Create a multi-page text PDF for testing."""
    pdf_path = os.path.join(temp_dir, "sample_multipage.pdf")

    doc = fitz.open()

    # Page 1
    page1 = doc.new_page(width=595, height=842)
    page1.insert_text((50, 50), "This is page 1 content.\nFirst page of the document.", fontsize=12)

    # Page 2
    page2 = doc.new_page(width=595, height=842)
    page2.insert_text((50, 50), "This is page 2 content.\nSecond page with different text.", fontsize=12)

    # Page 3
    page3 = doc.new_page(width=595, height=842)
    page3.insert_text((50, 50), "This is page 3 content.\nFinal page of the test document.", fontsize=12)

    doc.save(pdf_path)
    doc.close()

    yield pdf_path


@pytest.fixture
def sample_image_with_text(temp_dir):
    """Create a sample image with text for OCR testing."""
    img_path = os.path.join(temp_dir, "sample_image.png")

    # Create a simple image with text
    img = Image.new('RGB', (800, 400), color='white')
    draw = ImageDraw.Draw(img)

    # Add text (using default font)
    text = """PAN CARD
INCOME TAX DEPARTMENT
Permanent Account Number
ABCDE1234F
Name: John Doe"""

    draw.text((50, 50), text, fill='black')
    img.save(img_path)

    yield img_path


@pytest.fixture
def sample_scanned_pdf(temp_dir):
    """Create a scanned PDF (image-based) for testing."""
    pdf_path = os.path.join(temp_dir, "sample_scanned.pdf")

    # Create an image first
    img = Image.new('RGB', (800, 600), color='white')
    draw = ImageDraw.Draw(img)
    draw.text((100, 100), "This is a scanned document\nwith image-based text", fill='black')

    # Save image temporarily
    img_temp_path = os.path.join(temp_dir, "temp_scan.png")
    img.save(img_temp_path)

    # Convert image to PDF (no text layer)
    doc = fitz.open()
    page = doc.new_page(width=800, height=600)
    page.insert_image(page.rect, filename=img_temp_path)
    doc.save(pdf_path)
    doc.close()

    yield pdf_path


class TestOCRService:
    """Test suite for OCR extraction service."""

    @pytest.mark.asyncio
    async def test_extract_from_text_pdf(self, sample_text_pdf):
        """Test extraction from native text PDF using PyMuPDF."""
        service = OCRService()
        result = await service.extract_text(sample_text_pdf, "application/pdf")

        assert isinstance(result, OCRResult)
        assert result.method == "pymupdf"
        assert result.page_count == 1
        assert result.confidence > 0.9  # High confidence for native text
        assert "Sample Invoice" in result.text
        assert "INV-2024-001" in result.text
        assert len(result.text) > 50

    @pytest.mark.asyncio
    async def test_extract_multipage_pdf(self, sample_multipage_pdf):
        """Test extraction from multi-page PDF with page markers."""
        service = OCRService()
        result = await service.extract_text(sample_multipage_pdf, "application/pdf")

        assert result.method == "pymupdf"
        assert result.page_count == 3
        assert "--- PAGE 1 ---" in result.text
        assert "--- PAGE 2 ---" in result.text
        assert "--- PAGE 3 ---" in result.text
        assert "page 1 content" in result.text
        assert "page 2 content" in result.text
        assert "page 3 content" in result.text

    @pytest.mark.asyncio
    async def test_extract_from_image(self, sample_image_with_text):
        """Test extraction from image file using Tesseract."""
        service = OCRService()
        result = await service.extract_text(sample_image_with_text, "image/png")

        assert isinstance(result, OCRResult)
        assert result.method == "tesseract"
        assert result.page_count == 1
        assert 0 <= result.confidence <= 1
        # OCR may not be 100% accurate, but should capture key text
        assert len(result.text) > 10

    @pytest.mark.asyncio
    async def test_extract_from_scanned_pdf(self, sample_scanned_pdf):
        """Test extraction from scanned (image-based) PDF falls back to Tesseract."""
        service = OCRService()
        result = await service.extract_text(sample_scanned_pdf, "application/pdf")

        assert isinstance(result, OCRResult)
        # Should fall back to Tesseract since it's image-based
        assert result.method == "tesseract"
        assert result.page_count == 1
        assert 0 <= result.confidence <= 1

    @pytest.mark.asyncio
    async def test_empty_pdf(self, temp_dir):
        """Test extraction from empty PDF."""
        pdf_path = os.path.join(temp_dir, "empty.pdf")

        # Create empty PDF
        doc = fitz.open()
        doc.save(pdf_path)
        doc.close()

        service = OCRService()
        result = await service.extract_text(pdf_path, "application/pdf")

        assert result.page_count == 0
        assert result.text == ""

    @pytest.mark.asyncio
    async def test_unsupported_file_type(self):
        """Test that unsupported file types raise an error."""
        service = OCRService()

        with pytest.raises(ValueError, match="Unsupported file type"):
            await service.extract_text("/fake/path.xyz", "application/unknown")

    @pytest.mark.asyncio
    async def test_nonexistent_file(self):
        """Test that nonexistent files raise an error."""
        service = OCRService()

        with pytest.raises(Exception):
            await service.extract_text("/nonexistent/file.pdf", "application/pdf")

    def test_is_image_file(self):
        """Test image file detection."""
        service = OCRService()

        assert service._is_image_file("test.jpg") is True
        assert service._is_image_file("test.jpeg") is True
        assert service._is_image_file("test.png") is True
        assert service._is_image_file("test.tiff") is True
        assert service._is_image_file("test.pdf") is False
        assert service._is_image_file("test.docx") is False
        assert service._is_image_file("TEST.JPG") is True  # Case insensitive

    @pytest.mark.asyncio
    async def test_confidence_scores(self, sample_text_pdf, sample_image_with_text):
        """Test that confidence scores are within valid range."""
        service = OCRService()

        # Text PDF should have high confidence
        pdf_result = await service.extract_text(sample_text_pdf, "application/pdf")
        assert 0 <= pdf_result.confidence <= 1
        assert pdf_result.confidence > 0.9  # PyMuPDF should give high confidence

        # Image OCR may have variable confidence
        img_result = await service.extract_text(sample_image_with_text, "image/png")
        assert 0 <= img_result.confidence <= 1


class TestOCRServiceIntegration:
    """Integration tests for OCR service."""

    @pytest.mark.asyncio
    async def test_singleton_instance(self):
        """Test that ocr_service singleton works correctly."""
        from app.services.stages.stage1_ocr import ocr_service

        assert ocr_service is not None
        assert isinstance(ocr_service, OCRService)

    @pytest.mark.asyncio
    async def test_different_image_formats(self, temp_dir):
        """Test OCR works with different image formats."""
        service = OCRService()

        # Create test images in different formats
        formats = ['png', 'jpg', 'jpeg']

        for fmt in formats:
            img_path = os.path.join(temp_dir, f"test.{fmt}")
            img = Image.new('RGB', (400, 200), color='white')
            draw = ImageDraw.Draw(img)
            draw.text((50, 50), f"Test {fmt.upper()} format", fill='black')
            img.save(img_path)

            result = await service.extract_text(img_path, f"image/{fmt}")
            assert isinstance(result, OCRResult)
            assert result.method == "tesseract"
            assert result.page_count == 1


# Performance benchmark test (optional, can be skipped in CI)
@pytest.mark.slow
@pytest.mark.asyncio
async def test_performance_benchmark(sample_text_pdf, sample_image_with_text):
    """Benchmark OCR performance."""
    import time

    service = OCRService()

    # PDF extraction should be fast (<1 second)
    start = time.time()
    await service.extract_text(sample_text_pdf, "application/pdf")
    pdf_time = time.time() - start
    assert pdf_time < 2.0, f"PDF OCR too slow: {pdf_time:.2f}s"

    # Image OCR may be slower but should complete in reasonable time
    start = time.time()
    await service.extract_text(sample_image_with_text, "image/png")
    img_time = time.time() - start
    assert img_time < 5.0, f"Image OCR too slow: {img_time:.2f}s"
