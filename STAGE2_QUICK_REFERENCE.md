# Stage 2 Extraction Engine - Quick Reference

## 🚀 Quick Start

### 1. Extract Fields from a Single Document

```python
from app.services.stages.stage2_extraction import get_extractor
from app.core.enums import DocumentType

# Get extractor instance
extractor = get_extractor()

# Sample PAN OCR text
pan_ocr = """
Name: RAJESH KUMAR SHARMA
PAN: ABCDE1234F
Date of Birth: 15/03/1985
"""

# Extract fields
fields = await extractor.extract_fields(pan_ocr, DocumentType.PAN_PERSONAL)

# Print results
for field in fields:
    print(f"{field.field_name}: {field.field_value} (confidence: {field.confidence})")
```

**Output**:
```
pan_number: ABCDE1234F (confidence: 0.9)
full_name: RAJESH KUMAR SHARMA (confidence: 0.75)
dob: 15/03/1985 (confidence: 0.8)
```

---

### 2. Assemble Feature Vector for a Case

```python
from app.services.stages.stage2_features import get_assembler
from app.schemas.shared import ExtractedFieldItem

# Get assembler instance
assembler = get_assembler()

# Extracted fields from multiple documents
extracted_fields = [
    ExtractedFieldItem(
        field_name="pan_number",
        field_value="ABCDE1234F",
        confidence=0.9,
        source="extraction"
    ),
    ExtractedFieldItem(
        field_name="cibil_score",
        field_value="750",
        confidence=0.85,
        source="extraction"
    ),
    ExtractedFieldItem(
        field_name="annual_turnover",
        field_value="12500000",
        confidence=0.8,
        source="extraction"
    )
]

# Assemble feature vector
feature_vector = await assembler.assemble_features(
    db=db_session,
    case_id="CASE-001",
    extracted_fields=extracted_fields
)

print(f"PAN: {feature_vector.pan_number}")
print(f"CIBIL: {feature_vector.cibil_score}")
print(f"Turnover: {feature_vector.annual_turnover}")
print(f"Completeness: {feature_vector.feature_completeness}%")
```

---

### 3. Full Extraction Pipeline via API

```bash
# Trigger extraction for a case
curl -X POST http://localhost:8000/api/v1/extraction/case/CASE-001/extract

# Get extracted fields
curl http://localhost:8000/api/v1/extraction/case/CASE-001/fields

# Get feature vector
curl http://localhost:8000/api/v1/extraction/case/CASE-001/features
```

---

## 📋 Document Type Cheat Sheet

| Document Type | Key Fields | Confidence Tips |
|--------------|------------|-----------------|
| **PAN Card** | pan_number, full_name, dob | ✅ High if PAN validates |
| **Aadhaar** | aadhaar_number, name, dob, address | ✅ High if 12 digits |
| **GST Certificate** | gstin, business_name, reg_date, state | ✅ High if GSTIN validates |
| **GST Returns** | taxable_value, cgst, sgst, period | ⚠️ Medium (format varies) |
| **CIBIL Report** | cibil_score, active_loans, overdues | ✅ High if score in 300-900 |
| **ITR** | total_income, ay, tax_paid, biz_income | ⚠️ Medium (format varies) |
| **Financial Statements** | revenue, net_profit, net_worth | ⚠️ Medium (format varies) |

---

## 🎯 Field Name Reference

### Identity Fields
```python
"full_name"        # Borrower's full name
"pan_number"       # PAN (ABCDE1234F)
"aadhaar_number"   # Aadhaar (12 digits)
"dob"              # Date of birth (dd/mm/yyyy)
```

### Business Fields
```python
"entity_type"      # proprietorship, partnership, pvt_ltd, etc.
"gstin"            # GSTIN (15 chars)
"business_name"    # Legal name of business
"industry_type"    # Industry/sector
"pincode"          # 6-digit pincode
"business_vintage_years"  # Years in business
```

### Financial Fields
```python
"annual_turnover"        # Annual revenue (in rupees)
"itr_total_income"       # From ITR
"avg_monthly_balance"    # Bank statement
"monthly_credit_avg"     # Bank statement
"emi_outflow_monthly"    # Monthly EMI payments
"bounce_count_12m"       # Cheque bounces
"cash_deposit_ratio"     # Cash/total ratio
```

### Credit Fields
```python
"cibil_score"       # 300-900
"active_loan_count" # Number of active loans
"overdue_count"     # Overdue accounts
"enquiry_count_6m"  # Credit enquiries
```

---

## ⚙️ Configuration Options

### Confidence Threshold

```python
# Default: 0.5 (50%)
extractor = FieldExtractor(confidence_threshold=0.5)
assembler = FeatureAssembler(confidence_threshold=0.5)

# Conservative: 0.7 (prefer manual entries)
assembler = FeatureAssembler(confidence_threshold=0.7)

# Aggressive: 0.3 (prefer extractions)
assembler = FeatureAssembler(confidence_threshold=0.3)
```

---

## 🔍 Validation Examples

### PAN Validation
```python
extractor._validate_pan("ABCDE1234F")  # ✅ True
extractor._validate_pan("ABCXE1234F")  # ❌ False (invalid entity type)
extractor._validate_pan("ABCDE1234")   # ❌ False (wrong length)
```

Valid entity types (4th character):
- **P**: Person (individual)
- **C**: Company
- **F**: Firm (partnership)
- **H**: HUF (Hindu Undivided Family)
- **A**: AOP (Association of Persons)
- **T**: Trust
- **B**: Body of Individuals
- **L**: Local Authority
- **J**: Artificial Juridical Person
- **G**: Government

### GSTIN Validation
```python
extractor._validate_gstin("29ABCDE1234F1Z5")  # ✅ True
extractor._validate_gstin("99ABCDE1234F1Z5")  # ❌ False (invalid state)
extractor._validate_gstin("29ABCXE1234F1Z5")  # ❌ False (invalid PAN)
```

GSTIN structure:
- **Chars 1-2**: State code (01-38)
- **Chars 3-12**: PAN number
- **Char 13**: Entity number (1-9, A-Z)
- **Char 14**: Z (default)
- **Char 15**: Checksum

---

## 🧪 Testing Snippets

### Test Single Extraction

```python
import pytest
from app.services.stages.stage2_extraction import FieldExtractor
from app.core.enums import DocumentType

@pytest.mark.asyncio
async def test_my_extraction():
    extractor = FieldExtractor()

    ocr_text = "Your OCR text here..."
    fields = await extractor.extract_fields(ocr_text, DocumentType.PAN_PERSONAL)

    # Assert fields
    assert len(fields) > 0
    assert any(f.field_name == "pan_number" for f in fields)
```

### Test Feature Assembly

```python
@pytest.mark.asyncio
async def test_feature_assembly(db_session):
    from app.models.case import Case
    from app.services.stages.stage2_features import FeatureAssembler

    # Create test case
    case = Case(case_id="TEST-001", user_id=test_user_id)
    db_session.add(case)
    await db_session.commit()

    # Assemble features
    assembler = FeatureAssembler()
    feature_vector = await assembler.assemble_features(
        db=db_session,
        case_id="TEST-001",
        extracted_fields=[...]
    )

    assert feature_vector.feature_completeness > 0
```

---

## 🐛 Common Issues & Fixes

### Issue: No fields extracted
```python
# Check 1: Is OCR text empty?
if not ocr_text or not ocr_text.strip():
    # OCR failed or document is blank

# Check 2: Is document type supported?
if doc_type not in [DocumentType.PAN_PERSONAL, DocumentType.AADHAAR, ...]:
    # Add extraction method for this type

# Check 3: Are patterns matching?
import re
if not re.search(r'pattern', ocr_text):
    # Adjust regex pattern or anchor keywords
```

### Issue: Low confidence scores
```python
# Solution 1: Check validation
field = ExtractedFieldItem(field_name="pan_number", field_value="ABC...")
if not extractor._validate_field(field):
    # Field is invalid, confidence was lowered

# Solution 2: Improve OCR quality
# - Use better OCR engine
# - Preprocess images (denoise, deskew)
# - Use higher resolution scans
```

### Issue: Wrong values extracted
```python
# Solution: Add more specific anchors
# Before:
pattern = r'Name\s*:\s*([A-Z][a-z]+)'

# After (more specific):
pattern = r'(?:Full Name|Name of Applicant)\s*[:\-]\s*([A-Z][A-Za-z\s]+)'
```

---

## 📊 Priority Logic Examples

| Scenario | Extracted | Manual | Result | Reason |
|----------|-----------|--------|--------|--------|
| High confidence | 750 (0.9) | 720 | **750** | Extraction confidence ≥ 0.5 |
| Low confidence | 650 (0.3) | 720 | **720** | Manual preferred over low confidence |
| No manual | 650 (0.3) | None | **650** | Better than nothing |
| No extraction | None | 720 | **720** | Only source available |

---

## 🔢 Type Conversion Examples

### Dates
```python
"15/03/1985" → date(1985, 3, 15)
"15-03-1985" → date(1985, 3, 15)
```

### Numbers (Indian Format)
```python
"1,25,00,000" → 12500000.0   # Float
"Rs. 18,50,000" → 1850000.0  # Removes currency
"750" → 750                   # Integer (for cibil_score)
"4.0" → 4                     # Float to int conversion
```

### Enums
```python
"proprietorship" → EntityType.PROPRIETORSHIP
"pvt_ltd" → EntityType.PVT_LTD
```

---

## 📈 Feature Completeness Calculation

```python
total_fields = 21  # All fields in BorrowerFeatureVector

filled_fields = sum(1 for field in feature_vector if field is not None)

feature_completeness = (filled_fields / total_fields) * 100

# Examples:
# 5 fields filled → 23.8% completeness
# 10 fields filled → 47.6% completeness
# 15 fields filled → 71.4% completeness
# 21 fields filled → 100% completeness
```

---

## 🎨 Regex Pattern Examples

### PAN Number
```regex
\b([A-Z]{5}[0-9]{4}[A-Z])\b
```
Matches: `ABCDE1234F`

### GSTIN
```regex
\b(\d{2}[A-Z]{5}\d{4}[A-Z]\d[A-Z][0-9A-Z])\b
```
Matches: `29ABCDE1234F1Z5`

### Aadhaar
```regex
\b(\d{4}\s?\d{4}\s?\d{4})\b
```
Matches: `1234 5678 9012` or `123456789012`

### Date (dd/mm/yyyy)
```regex
\d{2}[/-]\d{2}[/-]\d{4}
```
Matches: `15/03/1985` or `15-03-1985`

### Currency Amount (Indian Format)
```regex
(?:Rs\.?|INR)?\s*([0-9,]+\.?\d*)
```
Matches: `Rs. 1,25,000` → `1,25,000`

### CIBIL Score
```regex
(?:Score|CIBIL Score|Credit Score)\s*[:\-]?\s*(\d{3})
```
Matches: `Credit Score: 756` → `756`

---

## 🔗 Integration Checklist

Before running extraction:
- ✅ Documents uploaded and stored
- ✅ OCR completed (`ocr_text` field populated)
- ✅ Documents classified (`doc_type` set)
- ✅ Case exists in database

After extraction:
- ✅ Check `feature_completeness` score
- ✅ Review low-confidence fields
- ✅ Fill missing manual overrides if needed
- ✅ Proceed to Stage 4 (Eligibility)

---

## 📚 Additional Resources

- **Full Documentation**: `STAGE2_EXTRACTION_README.md`
- **Delivery Summary**: `STAGE2_DELIVERY_SUMMARY.md`
- **Tests**: `tests/test_extraction.py`
- **Verification**: `verify_extraction_pipeline.py`

---

## 💡 Tips & Best Practices

1. **Always validate extracted values** before using in production
2. **Log low-confidence extractions** for manual review
3. **Use manual overrides** for critical fields (CIBIL, turnover)
4. **Test with real OCR data** to fine-tune patterns
5. **Monitor extraction success rates** per document type
6. **Keep regex patterns updated** as formats change
7. **Document new patterns** when adding document types

---

**Need help?** Check the full documentation or run the verification script!
