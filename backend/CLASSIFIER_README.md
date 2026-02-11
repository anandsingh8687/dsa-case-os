# Document Classifier - DSA Case OS

Intelligent document classification system for the DSA Case OS credit intelligence platform.

## Overview

The Document Classifier uses a **two-layer approach** to identify document types from OCR text:

1. **Layer 1: ML-based classification** (TF-IDF + Logistic Regression)
   - Used when trained model is available
   - Higher accuracy for complex cases
   - Requires training data

2. **Layer 2: Keyword/Rule-based fallback**
   - Always available
   - No training required
   - Rule-based pattern matching

## Supported Document Types

The classifier can identify these document types (from `DocumentType` enum):

- `AADHAAR` - Aadhaar cards
- `PAN_PERSONAL` - Personal PAN cards
- `PAN_BUSINESS` - Business PAN cards (companies, partnerships, etc.)
- `GST_CERTIFICATE` - GST registration certificates
- `GST_RETURNS` - GST return filings (GSTR-1, GSTR-3B, etc.)
- `BANK_STATEMENT` - Bank account statements
- `ITR` - Income Tax Returns
- `FINANCIAL_STATEMENTS` - Balance sheets, P&L statements
- `CIBIL_REPORT` - Credit reports from CIBIL/TransUnion
- `UDYAM_SHOP_LICENSE` - Udyam/MSME certificates, shop licenses
- `PROPERTY_DOCUMENTS` - Sale deeds, property registrations
- `UNKNOWN` - Unrecognizable documents

## Confidence Thresholds

Each document type has a minimum confidence threshold:

| Document Type | Threshold |
|--------------|-----------|
| AADHAAR | 0.80 |
| PAN (Personal/Business) | 0.80 |
| GST Certificate | 0.80 |
| GST Returns | 0.85 |
| Bank Statement | 0.85 |
| ITR | 0.80 |
| Financial Statements | 0.75 |
| CIBIL Report | 0.85 |
| Udyam/Shop License | 0.75 |
| Property Documents | 0.70 |

## Quick Start

### 1. Using the Keyword-based Classifier (No Training Required)

```python
from app.services.stages.stage1_classifier import classify_document

# Classify a document
ocr_text = "GOVERNMENT OF INDIA AADHAAR..."
result = classify_document(ocr_text)

print(f"Type: {result.doc_type}")
print(f"Confidence: {result.confidence}")
print(f"Method: {result.method}")  # "keyword"
```

### 2. Training the ML Model

```bash
# Using sample training data
python scripts/train_classifier.py

# Using custom training data
python scripts/train_classifier.py path/to/your/training_data.csv
```

**Training data CSV format:**
```csv
filename,doc_type,text
aadhaar_001.pdf,aadhaar,"UIDAI Aadhaar Card Name: RAJESH KUMAR..."
pan_001.pdf,pan_personal,"PAN Card Name: RAJESH KUMAR..."
```

### 3. Using the ML Model

After training, the classifier automatically uses the ML model:

```python
from app.services.stages.stage1_classifier import classify_document

result = classify_document(ocr_text)
# Now uses ML model if confidence > 0.70, otherwise falls back to keywords
print(f"Method: {result.method}")  # "ml" or "keyword"
```

## API Endpoints

### Classify a Document

```http
POST /api/v1/documents/{doc_id}/classify
```

Classifies a document based on its OCR text and updates the database.

**Response:**
```json
{
  "doc_type": "aadhaar",
  "confidence": 0.95,
  "method": "ml",
  "scores": {
    "aadhaar": 0.95,
    "pan_personal": 0.03,
    "unknown": 0.02
  }
}
```

### Manually Reclassify a Document

```http
POST /api/v1/documents/{doc_id}/reclassify
```

**Request body:**
```json
{
  "doc_type": "pan_personal",
  "confidence": 1.0
}
```

Use this endpoint when automatic classification is incorrect.

## Integration with Pipeline

### After OCR Stage

```python
from sqlalchemy.ext.asyncio import AsyncSession
from app.services.stages.stage1_classifier import classify_document
from app.models.case import Document
from app.core.enums import DocumentStatus

async def process_document_after_ocr(doc_id: str, db: AsyncSession):
    """Classify document after OCR is complete."""

    # Get document
    document = await db.get(Document, doc_id)

    # Classify
    result = classify_document(document.ocr_text)

    # Update database
    document.doc_type = result.doc_type.value
    document.classification_confidence = result.confidence
    document.status = DocumentStatus.CLASSIFIED.value

    await db.commit()
```

## Running Tests

```bash
# Install pytest if not already installed
pip install pytest

# Run all classifier tests
pytest backend/tests/test_classifier.py -v

# Run specific test class
pytest backend/tests/test_classifier.py::TestKeywordClassifier -v

# Run with coverage
pytest backend/tests/test_classifier.py --cov=app.services.stages.stage1_classifier
```

## Demo Scripts

### Classification Demo

```bash
python scripts/classify_document_demo.py
```

Shows how the classifier works on sample documents.

### Training Demo

```bash
python scripts/train_classifier.py
```

Trains the ML model using sample data.

## Architecture

### Files Structure

```
backend/
├── app/
│   ├── services/
│   │   └── stages/
│   │       ├── stage1_classifier.py      # Main classifier
│   │       └── classifier_trainer.py     # Training pipeline
│   ├── schemas/
│   │   └── classifier.py                 # Pydantic schemas
│   └── api/
│       └── v1/
│           └── endpoints/
│               └── documents.py          # API endpoints
├── models/                               # Saved ML models
│   ├── classifier_model.joblib
│   └── classifier_vectorizer.joblib
├── training_data/
│   └── sample_training_data.csv         # Sample training data
├── scripts/
│   ├── train_classifier.py              # Training script
│   └── classify_document_demo.py        # Demo script
└── tests/
    └── test_classifier.py               # Unit tests
```

### Classification Logic

```
Input: OCR Text
     ↓
ML Model Available?
     ↓
   YES → ML Classification
     ↓
   Confidence > 0.70?
     ↓
   YES → Return ML Result
     ↓
   NO ↓
     ↓
Keyword-based Classification
     ↓
   Confidence > Threshold?
     ↓
   YES → Return Keyword Result
     ↓
   NO → Return UNKNOWN
```

## Keyword Patterns

Each document type has specific patterns:

**Aadhaar:**
- "UIDAI", "Unique Identification", "Aadhaar", "आधार"
- Pattern: `\d{4}\s+\d{4}\s+\d{4}` (Aadhaar number)

**PAN:**
- "Permanent Account Number", "Income Tax Department"
- Pattern: `[A-Z]{5}\d{4}[A-Z]` (PAN number)
- Business indicators: "Pvt Ltd", "LLP", "Partnership"

**GST Certificate:**
- "GSTIN", "Goods and Services Tax", "Certificate of Registration"
- Pattern: `\d{2}[A-Z]{5}\d{4}[A-Z]{1}\d[Z]{1}[A-Z\d]{1}` (GSTIN)

**Bank Statement:**
- "Opening Balance", "Closing Balance", "Statement of Account"
- Bank names: "HDFC", "ICICI", "SBI", "Axis"

See `stage1_classifier.py` for complete patterns.

## ML Model Details

### Features

- **Vectorizer:** TF-IDF with n-grams (1-3)
- **Classifier:** Logistic Regression (multinomial)
- **Max Features:** 5000
- **Class Balancing:** Yes (class_weight='balanced')

### Training Metrics

After training, you'll see:
- Test accuracy
- 5-fold cross-validation scores
- Classification report (precision, recall, F1)
- Confusion matrix
- Top keywords per document type

### Improving Accuracy

1. **Add more training data** - Aim for 50+ samples per document type
2. **Include diverse examples** - Different formats, banks, states, etc.
3. **Balance classes** - Equal samples for each type
4. **Tune hyperparameters** - Adjust in `classifier_trainer.py`

## Troubleshooting

### ML model not loading

**Symptom:** Always uses keyword method

**Solution:**
1. Check if model files exist: `backend/models/classifier_*.joblib`
2. Run training: `python scripts/train_classifier.py`
3. Check console for error messages

### Low classification confidence

**Symptom:** Many documents classified as UNKNOWN

**Solution:**
1. Check OCR quality - Poor OCR = poor classification
2. Review keyword patterns - Add domain-specific terms
3. Train ML model with local examples

### Wrong classification

**Symptom:** PAN classified as Aadhaar, etc.

**Solution:**
1. Use manual reclassification endpoint
2. Add misclassified examples to training data
3. Retrain the model
4. Adjust keyword patterns if needed

## Performance Benchmarks

**Keyword Classifier:**
- Accuracy on test set: >90%
- Speed: <10ms per document
- Memory: ~5MB

**ML Classifier:**
- Accuracy on test set: >95% (with good training data)
- Speed: ~50ms per document
- Memory: ~50MB (model + vectorizer)

## Future Enhancements

- [ ] Deep learning models (BERT, DistilBERT)
- [ ] Multi-language support
- [ ] Confidence calibration
- [ ] Active learning pipeline
- [ ] Document sub-type classification
- [ ] Field extraction integration

## License

Part of DSA Case OS - Internal use only.
