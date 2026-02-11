# Stage 1: OCR Text Extraction

## Overview

The OCR service (`stage1_ocr.py`) extracts text from uploaded documents (PDFs and images). This is the first step in the Document Intelligence pipeline for the DSA Case OS.

## Features

- **Native PDF Text Extraction**: Fast extraction using PyMuPDF for text-based PDFs
- **Scanned Document OCR**: Automatic fallback to Tesseract OCR for image-based PDFs
- **Image OCR**: Direct Tesseract processing for JPG, PNG, TIFF images
- **Multi-page Support**: Handles multi-page PDFs with page markers
- **Confidence Scoring**: Returns OCR confidence scores (0-1 scale)
- **Error Handling**: Graceful handling of corrupt/unreadable files

## Usage

### Basic Usage

```python
from app.services.stages.stage1_ocr import ocr_service

# Extract text from a PDF
result = await ocr_service.extract_text(
    file_path="/path/to/document.pdf",
    mime_type="application/pdf"
)

# Access results
print(f"Extracted text: {result.text}")
print(f"Confidence: {result.confidence}")
print(f"Pages: {result.page_count}")
print(f"Method: {result.method}")  # "pymupdf" or "tesseract"
```

### With Database Integration

```python
from app.services.document_processor import document_processor
from app.db.database import get_db

# Process a document and update DB
async with get_db() as db:
    result = await document_processor.process_document_ocr(
        db=db,
        document_id=document_uuid,
        file_path="/path/to/file.pdf"
    )
```

### API Endpoint

```
GET /api/v1/documents/{doc_id}/ocr-text
```

Returns:
```json
{
  "status": "completed",
  "text": "Extracted text content...",
  "confidence": 0.95,
  "page_count": 3,
  "document_status": "ocr_complete"
}
```

## Technical Details

### PDF Processing Logic

1. **Text-based PDFs**:
   - PyMuPDF extracts text directly (fast, accurate)
   - Detected when text content > 50 chars/page
   - Confidence: 0.95

2. **Scanned PDFs**:
   - Falls back to Tesseract if PyMuPDF yields little text
   - Converts pages to images at 150 DPI
   - Runs OCR on each page
   - Confidence: based on Tesseract output

### Image Processing

1. Convert to grayscale
2. Enhance contrast (1.5x)
3. Run Tesseract OCR
4. Calculate confidence from character-level scores

### Multi-page PDFs

Text from multiple pages is concatenated with markers:
```
--- PAGE 1 ---
Content from page 1...

--- PAGE 2 ---
Content from page 2...
```

## Configuration

Set Tesseract path in `backend/app/core/config.py`:

```python
TESSERACT_CMD: str = "tesseract"  # or "/usr/bin/tesseract"
```

## Dependencies

- `PyMuPDF==1.23.18` - Native PDF text extraction
- `pytesseract==0.3.10` - OCR engine wrapper
- `Pillow==10.2.0` - Image preprocessing

**System requirement**: Tesseract OCR must be installed on the system.

### Install Tesseract

**Ubuntu/Debian:**
```bash
sudo apt-get install tesseract-ocr
```

**macOS:**
```bash
brew install tesseract
```

**Windows:**
Download installer from: https://github.com/UB-Mannheim/tesseract/wiki

## Performance

- **Native PDFs**: < 1 second per page
- **Scanned PDFs**: 2-5 seconds per page
- **Images**: 1-3 seconds per image

## Database Schema

The OCR service updates the following fields in the `documents` table:

- `ocr_text` (TEXT): Extracted text content
- `ocr_confidence` (FLOAT): Confidence score (0-1)
- `page_count` (INTEGER): Number of pages processed
- `status` (VARCHAR): Updated to "ocr_complete" or "failed"

## Error Handling

The service handles:
- Corrupt/unreadable files → raises exception, marks document as "failed"
- Empty PDFs → returns empty result with page_count=0
- Unsupported file types → raises ValueError
- Missing files → raises exception

## Testing

Run tests:
```bash
pytest backend/tests/test_ocr.py -v
```

Test coverage includes:
- Native PDF extraction
- Multi-page PDFs
- Image OCR
- Scanned PDF fallback
- Error handling
- Confidence scoring

## Accuracy Note

OCR output is used for document classification and keyword matching, not verbatim data capture. The service prioritizes **speed over perfection**.

Expected accuracy:
- Native PDFs: 99%+
- Good quality scans: 90-95%
- Poor quality scans: 70-85%

## Future Enhancements

- [ ] Support for additional languages (currently English only)
- [ ] Table extraction and structure preservation
- [ ] Advanced image preprocessing (deskewing, noise removal)
- [ ] Parallel processing for multi-page documents
- [ ] Caching of OCR results
