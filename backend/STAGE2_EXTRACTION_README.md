# Stage 2: Field Extraction Engine - Documentation

## Overview

The Stage 2 Extraction Engine extracts structured fields from OCR text using regex patterns and assembles them into a unified Borrower Feature Vector for credit analysis.

## Architecture

### Components

1. **stage2_extraction.py** - Field extraction from OCR text using regex patterns
2. **stage2_features.py** - Feature vector assembly and database management
3. **API endpoints** - REST endpoints for triggering extraction and retrieving results
4. **Database models** - ExtractedField and BorrowerFeature tables

### Data Flow

```
OCR Text → Field Extraction → Extracted Fields → Feature Assembly → Borrower Feature Vector
                ↓                                        ↓
           ExtractedField Table               BorrowerFeature Table
```

## Supported Documents

### 1. PAN Card
**Extracted Fields:**
- PAN number (format: ABCDE1234F)
- Full name
- Date of birth (dd/mm/yyyy)

**Validation:**
- PAN format validation
- 4th character entity type check (P/C/F/H/A/T/B/L/J/G)

### 2. Aadhaar Card
**Extracted Fields:**
- Aadhaar number (12 digits)
- Full name
- Date of birth
- Address

**Validation:**
- 12-digit numeric validation

### 3. GST Certificate
**Extracted Fields:**
- GSTIN (15 characters)
- Business name
- Registration date
- State (derived from GSTIN state code)

**Validation:**
- GSTIN format validation
- State code validation (01-38)
- Embedded PAN validation

### 4. GST Returns
**Extracted Fields:**
- Total taxable value
- CGST amount
- SGST amount
- Filing period

### 5. CIBIL Report
**Extracted Fields:**
- Credit score (300-900)
- Active loan count
- Overdue account count
- Enquiry count (last 6 months)

**Validation:**
- Score range validation (300-900)

### 6. ITR (Income Tax Return)
**Extracted Fields:**
- Total income
- Assessment year
- Tax paid
- Business income

### 7. Financial Statements
**Extracted Fields:**
- Annual turnover/revenue
- Net profit
- Net worth

## Feature Vector Assembly

### Priority Logic

The feature assembler uses the following priority order:

1. **High-confidence extraction** (confidence ≥ 0.5) → Use extracted value
2. **Manual override** (from Case table) → Use manual value
3. **Low-confidence extraction** (confidence < 0.5) → Use extracted value (better than nothing)
4. **No data** → Field remains null

### Type Conversion

Fields are automatically converted to appropriate types:
- **String fields**: pan_number, gstin, full_name, etc.
- **Date fields**: dob → Python date object
- **Float fields**: annual_turnover, itr_total_income, etc.
- **Integer fields**: cibil_score, active_loan_count, etc.
- **Enum fields**: entity_type → EntityType enum

### Completeness Calculation

```
feature_completeness = (filled_fields / total_fields) × 100
```

Total fields = 21 (all non-meta fields in BorrowerFeatureVector)

## API Usage

### 1. Trigger Extraction

```bash
POST /api/v1/extraction/case/{case_id}/extract
```

**Response:**
```json
{
  "status": "success",
  "case_id": "CASE-001",
  "total_fields_extracted": 12,
  "feature_completeness": 57.14,
  "documents_processed": 5,
  "extraction_summary": [
    {
      "document_id": "uuid",
      "doc_type": "pan_personal",
      "fields_extracted": 3
    }
  ]
}
```

### 2. Get Extracted Fields

```bash
GET /api/v1/extraction/case/{case_id}/fields
```

**Response:**
```json
[
  {
    "field_name": "pan_number",
    "field_value": "ABCDE1234F",
    "confidence": 0.9,
    "source": "extraction"
  }
]
```

### 3. Get Feature Vector

```bash
GET /api/v1/extraction/case/{case_id}/features
```

**Response:**
```json
{
  "full_name": "Rajesh Kumar Sharma",
  "pan_number": "ABCDE1234F",
  "cibil_score": 750,
  "annual_turnover": 12500000.0,
  "feature_completeness": 57.14,
  ...
}
```

## Configuration

### Confidence Threshold

Default: **0.5** (50%)

Extracted values with confidence ≥ 0.5 will override manual entries.

### Regex Patterns

All regex patterns are designed to be liberal with whitespace to handle OCR noise:
- Use `\s*` and `\s+` for flexible whitespace matching
- Support both `/` and `-` in dates
- Handle Indian number formatting (1,00,000)

## Database Schema

### ExtractedField Table

```sql
CREATE TABLE extracted_fields (
    id UUID PRIMARY KEY,
    case_id UUID REFERENCES cases(id),
    document_id UUID REFERENCES documents(id),
    field_name VARCHAR(100),
    field_value TEXT,
    confidence FLOAT,
    source VARCHAR(20),  -- 'extraction' | 'manual' | 'computed'
    created_at TIMESTAMP
);
```

### BorrowerFeature Table

```sql
CREATE TABLE borrower_features (
    id UUID PRIMARY KEY,
    case_id UUID REFERENCES cases(id) UNIQUE,
    -- Identity fields
    full_name VARCHAR(255),
    pan_number VARCHAR(10),
    aadhaar_number VARCHAR(12),
    dob TIMESTAMP,
    -- Business fields
    entity_type VARCHAR(20),
    business_vintage_years FLOAT,
    gstin VARCHAR(15),
    -- Financial fields
    annual_turnover FLOAT,
    cibil_score INTEGER,
    -- ... more fields
    feature_completeness FLOAT,
    created_at TIMESTAMP,
    updated_at TIMESTAMP
);
```

## Testing

### Run Tests

```bash
cd backend
pytest tests/test_extraction.py -v
```

### Test Coverage

- ✅ Field extraction for all document types
- ✅ PAN validation
- ✅ GSTIN validation with state code
- ✅ CIBIL score range validation
- ✅ Date parsing (dd/mm/yyyy)
- ✅ Numeric field handling (Indian format with commas)
- ✅ Priority logic (extraction vs manual)
- ✅ Type conversion
- ✅ Feature completeness calculation
- ✅ Noisy OCR handling
- ✅ Database CRUD operations

## Edge Cases Handled

1. **Noisy OCR**: Liberal whitespace matching, multiple delimiter support
2. **Multiple matches**: Takes first match (configurable)
3. **Missing fields**: Gracefully handles null values
4. **Invalid formats**: Lowers confidence but still stores data
5. **Indian number formats**: Removes commas (1,00,000 → 100000)
6. **Mixed delimiters**: Supports both `-` and `/` in dates

## GST Turnover Strategy

Priority order for determining annual turnover:

1. **GST Returns** - Direct parsing of taxable value → multiply by 12 months
2. **Bank Statement Analysis** - Monthly credits × 12 (if available)
3. **Financial Statements** - Revenue from P&L
4. **Manual Entry** - Fallback

## Integration with Other Stages

### Input Dependencies
- **Stage 1 (OCR)**: Requires `ocr_text` field populated in documents
- **Stage 1 (Classifier)**: Requires `doc_type` classification

### Output Consumers
- **Stage 4 (Eligibility)**: Uses BorrowerFeatureVector for scoring
- **Stage 5 (Reporting)**: Uses feature data for report generation

## Common Issues & Solutions

### Issue: Low extraction rate
**Solution**: Check OCR quality, adjust regex patterns for specific document formats

### Issue: Wrong values extracted
**Solution**: Validate field values, adjust anchor keywords in regex patterns

### Issue: Confidence too low
**Solution**: Improve validation logic, add more context-aware extraction

### Issue: Type conversion errors
**Solution**: Check field format, add error handling for malformed data

## Future Enhancements

1. **ML-based extraction**: Replace regex with NER models for better accuracy
2. **Confidence scoring**: Implement more sophisticated confidence calculation
3. **Field relationships**: Validate cross-field consistency (e.g., GSTIN contains PAN)
4. **Auto-correction**: Suggest corrections for invalid values
5. **Template matching**: Learn document layouts for better anchor detection

## Performance Considerations

- **Extraction time**: ~100-500ms per document (regex-based)
- **Database writes**: Batched for efficiency
- **Caching**: Singleton extractors to avoid reinitialization
- **Async operations**: All DB operations are async for scalability

## Maintenance

### Adding New Document Types

1. Add document type to `DocumentType` enum
2. Create extraction method in `FieldExtractor`
3. Add regex patterns and validation logic
4. Update tests with sample OCR data
5. Document fields in this README

### Modifying Extraction Rules

1. Update regex pattern in corresponding `_extract_*` method
2. Test with sample OCR data
3. Verify confidence scores
4. Update validation if needed

## Contributing

When contributing extraction rules:
- Include sample OCR text in tests
- Test with both clean and noisy data
- Document field format and validation rules
- Maintain confidence threshold consistency
