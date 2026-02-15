"""Stage 1: OCR Text Extraction Service
Extracts text from PDFs and images using PyMuPDF (for native PDFs) and Tesseract (for scanned docs/images).
"""
import logging
import time
from pathlib import Path
from typing import Tuple
import os
import re
import fitz  # PyMuPDF
import pytesseract
from PIL import Image, ImageEnhance
import io

from app.schemas.shared import OCRResult
from app.core.config import settings

logger = logging.getLogger(__name__)


class OCRService:
    """Handles text extraction from PDFs and images."""

    def __init__(self):
        # Configure Tesseract path if specified in config
        if settings.TESSERACT_CMD != "tesseract":
            pytesseract.pytesseract.tesseract_cmd = settings.TESSERACT_CMD

    async def extract_text(self, file_path: str, mime_type: str) -> OCRResult:
        """
        Extract text from a document (PDF or image).

        Args:
            file_path: Absolute path to the file
            mime_type: MIME type of the file (e.g., 'application/pdf', 'image/jpeg')

        Returns:
            OCRResult containing extracted text, confidence, page count, and method used

        Raises:
            Exception: If file cannot be read or processed
        """
        start_time = time.time()

        try:
            # Determine file type and route to appropriate handler
            if mime_type == 'application/pdf' or file_path.lower().endswith('.pdf'):
                result = await self._extract_from_pdf(file_path)
            elif mime_type.startswith('image/') or self._is_image_file(file_path):
                result = await self._extract_from_image(file_path)
            else:
                raise ValueError(f"Unsupported file type: {mime_type}")

            processing_time = time.time() - start_time
            logger.info(
                f"OCR completed in {processing_time:.2f}s | "
                f"Method: {result.method} | Pages: {result.page_count} | "
                f"Confidence: {result.confidence:.2f} | Text length: {len(result.text)}"
            )

            return result

        except Exception as e:
            logger.error(f"OCR failed for {file_path}: {str(e)}", exc_info=True)
            raise

    async def _extract_from_pdf(self, file_path: str) -> OCRResult:
        """
        Extract text from PDF using PyMuPDF first, falling back to Tesseract if needed.

        Strategy:
        1. Try PyMuPDF text extraction (fast, works for native PDFs)
        2. If text is sparse (<50 chars/page), treat as scanned PDF
        3. Convert to images and run Tesseract OCR
        """
        doc = None
        try:
            doc = fitz.open(file_path)
            if doc.is_encrypted:
                unlocked = self._unlock_pdf(doc, file_path=file_path)
                if not unlocked:
                    raise ValueError(
                        "PDF is password-protected and could not be unlocked with configured candidates"
                    )
            page_count = len(doc)

            if page_count == 0:
                return OCRResult(
                    text="",
                    confidence=0.0,
                    page_count=0,
                    method="pymupdf"
                )

            # First attempt: PyMuPDF text extraction
            pymupdf_text, is_text_based = self._extract_with_pymupdf(doc)

            # If PDF has sufficient text content, use PyMuPDF result
            if is_text_based:
                return OCRResult(
                    text=pymupdf_text,
                    confidence=0.95,  # High confidence for native text extraction
                    page_count=page_count,
                    method="pymupdf"
                )

            # Fall back to Tesseract for scanned PDFs
            logger.info(f"PDF appears to be scanned ({len(pymupdf_text)} chars). Using Tesseract OCR.")
            ocr_text, avg_confidence = self._extract_pdf_with_tesseract(doc)

            return OCRResult(
                text=ocr_text,
                confidence=avg_confidence,
                page_count=page_count,
                method="tesseract"
            )

        finally:
            if doc:
                doc.close()

    def _unlock_pdf(self, doc: fitz.Document, file_path: str) -> bool:
        """Try common password candidates for encrypted PDFs."""
        candidates = self._build_pdf_password_candidates(file_path)

        for candidate in candidates:
            try:
                if doc.authenticate(candidate):
                    logger.info(
                        "Unlocked encrypted PDF using candidate derived from filename/config"
                    )
                    return True
            except Exception:
                continue

        logger.warning("Failed to unlock encrypted PDF %s using %d candidates", file_path, len(candidates))
        return False

    def _build_pdf_password_candidates(self, file_path: str) -> list[str]:
        stem = Path(file_path).stem
        stem_clean = re.sub(r"[^A-Za-z0-9]", "", stem)
        tokens = [tok for tok in re.split(r"[^A-Za-z0-9]+", stem) if tok]

        candidates = [
            stem,
            stem.upper(),
            stem.lower(),
            stem.title(),
            stem_clean,
            stem_clean.upper(),
            stem_clean.lower(),
        ]

        if tokens:
            joined = "".join(tokens)
            candidates.extend([
                joined,
                joined.upper(),
                joined.lower(),
                "".join(tok.upper() for tok in tokens),
            ])

        # Add explicit environment candidates for known protected formats.
        if settings.PDF_PASSWORD_CANDIDATES:
            extra = [item.strip() for item in settings.PDF_PASSWORD_CANDIDATES.split(",") if item.strip()]
            candidates.extend(extra)

        # Preserve order while deduplicating.
        unique = []
        seen = set()
        for cand in candidates:
            if not cand:
                continue
            if cand in seen:
                continue
            seen.add(cand)
            unique.append(cand)
        return unique

    def _extract_with_pymupdf(self, doc: fitz.Document) -> Tuple[str, bool]:
        """
        Extract text from PDF using PyMuPDF.

        Returns:
            (extracted_text, is_text_based) - is_text_based is True if PDF has native text
        """
        pages_text = []
        total_chars = 0

        for page_num in range(len(doc)):
            page = doc[page_num]
            page_text = page.get_text()

            # Add page marker for multi-page PDFs
            if len(doc) > 1:
                pages_text.append(f"\n--- PAGE {page_num + 1} ---\n")

            pages_text.append(page_text)
            total_chars += len(page_text.strip())

        full_text = "".join(pages_text)

        # Heuristic: If we get >50 chars per page on average, it's likely text-based
        avg_chars_per_page = total_chars / len(doc) if len(doc) > 0 else 0
        is_text_based = avg_chars_per_page > 50

        return full_text, is_text_based

    def _extract_pdf_with_tesseract(self, doc: fitz.Document) -> Tuple[str, float]:
        """
        Convert PDF pages to images and run Tesseract OCR.

        Returns:
            (extracted_text, average_confidence)
        """
        pages_text = []
        confidences = []

        for page_num in range(len(doc)):
            page = doc[page_num]

            # Convert page to image (150 DPI is good balance of quality/speed)
            pix = page.get_pixmap(matrix=fitz.Matrix(150/72, 150/72))
            img_bytes = pix.tobytes("png")
            image = Image.open(io.BytesIO(img_bytes))

            # Run Tesseract OCR with detailed output
            ocr_data = pytesseract.image_to_data(
                image,
                output_type=pytesseract.Output.DICT,
                lang='eng'
            )

            # Extract text
            page_text = pytesseract.image_to_string(image, lang='eng')

            # Add page marker for multi-page PDFs
            if len(doc) > 1:
                pages_text.append(f"\n--- PAGE {page_num + 1} ---\n")

            pages_text.append(page_text)

            # Calculate average confidence for this page
            page_confidences = [
                int(conf) for conf in ocr_data['conf']
                if conf != '-1' and str(conf).isdigit()
            ]
            if page_confidences:
                confidences.extend(page_confidences)

        full_text = "".join(pages_text)

        # Calculate average confidence (0-1 scale)
        avg_confidence = (sum(confidences) / len(confidences) / 100.0) if confidences else 0.5

        return full_text, avg_confidence

    async def _extract_from_image(self, file_path: str) -> OCRResult:
        """
        Extract text from image file using Tesseract OCR.

        Preprocessing steps:
        1. Convert to grayscale
        2. Enhance contrast
        3. Run OCR
        """
        try:
            # Open and preprocess image
            image = Image.open(file_path)

            # Convert to RGB if necessary (handle PNG with transparency, etc.)
            if image.mode not in ('RGB', 'L'):
                image = image.convert('RGB')

            # Convert to grayscale
            image = image.convert('L')

            # Enhance contrast
            enhancer = ImageEnhance.Contrast(image)
            image = enhancer.enhance(1.5)

            # Run Tesseract OCR with detailed output
            ocr_data = pytesseract.image_to_data(
                image,
                output_type=pytesseract.Output.DICT,
                lang='eng'
            )

            # Extract text
            text = pytesseract.image_to_string(image, lang='eng')

            # Calculate average confidence
            confidences = [
                int(conf) for conf in ocr_data['conf']
                if conf != '-1' and str(conf).isdigit()
            ]
            avg_confidence = (sum(confidences) / len(confidences) / 100.0) if confidences else 0.5

            return OCRResult(
                text=text,
                confidence=avg_confidence,
                page_count=1,
                method="tesseract"
            )

        except Exception as e:
            logger.error(f"Image OCR failed: {str(e)}", exc_info=True)
            raise

    def _is_image_file(self, file_path: str) -> bool:
        """Check if file is an image based on extension."""
        image_extensions = {'.jpg', '.jpeg', '.png', '.tiff', '.tif', '.bmp', '.gif'}
        return Path(file_path).suffix.lower() in image_extensions


# Singleton instance
ocr_service = OCRService()
