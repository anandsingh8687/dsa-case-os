# Stage 2 Extraction Engine - Architecture Diagram

## System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    DSA CASE OS - STAGE 2                        │
│                 FIELD EXTRACTION ENGINE                          │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│                         INPUT LAYER                              │
└─────────────────────────────────────────────────────────────────┘

    ┌──────────────┐
    │   Document   │ ◄── From Stage 1 (OCR + Classifier)
    │              │
    │ • doc_type   │
    │ • ocr_text   │
    │ • confidence │
    └──────┬───────┘
           │
           ▼

┌─────────────────────────────────────────────────────────────────┐
│                      EXTRACTION LAYER                            │
│                 (stage2_extraction.py)                           │
└─────────────────────────────────────────────────────────────────┘

    ┌─────────────────────────────────────────────────────────┐
    │              FieldExtractor Class                       │
    ├─────────────────────────────────────────────────────────┤
    │                                                         │
    │  extract_fields(ocr_text, doc_type)                    │
    │        │                                                │
    │        ├──► Route by doc_type                          │
    │        │                                                │
    │        ├──► _extract_pan_card()                        │
    │        │      • Regex: [A-Z]{5}[0-9]{4}[A-Z]          │
    │        │      • Anchors: "Name", "DOB"                 │
    │        │                                                │
    │        ├──► _extract_aadhaar()                         │
    │        │      • Regex: \d{4}\s?\d{4}\s?\d{4}          │
    │        │      • 12-digit validation                    │
    │        │                                                │
    │        ├──► _extract_gst_certificate()                 │
    │        │      • Regex: [0-9]{2}[A-Z]{5}...            │
    │        │      • State code mapping                     │
    │        │                                                │
    │        ├──► _extract_gst_returns()                     │
    │        ├──► _extract_cibil_report()                    │
    │        ├──► _extract_itr()                             │
    │        └──► _extract_financial_statements()            │
    │                                                         │
    │  validate_field(field)                                 │
    │        ├──► _validate_pan()                            │
    │        ├──► _validate_gstin()                          │
    │        └──► Business rules validation                  │
    │                                                         │
    └─────────────────────┬───────────────────────────────────┘
                          │
                          ▼
                 ┌────────────────┐
                 │ ExtractedField │
                 │                │
                 │ • field_name   │
                 │ • field_value  │
                 │ • confidence   │ ◄── Adjusted by validation
                 │ • source       │
                 └────────┬───────┘
                          │
                          ▼

┌─────────────────────────────────────────────────────────────────┐
│                      ASSEMBLY LAYER                              │
│                  (stage2_features.py)                            │
└─────────────────────────────────────────────────────────────────┘

    ┌─────────────────────────────────────────────────────────┐
    │            FeatureAssembler Class                       │
    ├─────────────────────────────────────────────────────────┤
    │                                                         │
    │  assemble_features(case_id, extracted_fields)          │
    │        │                                                │
    │        ├──► Fetch manual overrides from Case table     │
    │        │                                                │
    │        ├──► For each field:                            │
    │        │      resolve_field_value()                    │
    │        │      │                                        │
    │        │      ├─► Extracted (conf ≥ 0.5)? ──► Use     │
    │        │      ├─► Manual exists? ──────────► Use     │
    │        │      └─► Extracted (any conf)? ───► Use     │
    │        │                                                │
    │        ├──► Type conversion:                           │
    │        │      convert_field_type()                     │
    │        │      │                                        │
    │        │      ├─► String → str                        │
    │        │      ├─► Date → date                         │
    │        │      ├─► Float → float                       │
    │        │      ├─► Integer → int                       │
    │        │      └─► Enum → EntityType                   │
    │        │                                                │
    │        └──► Calculate completeness:                    │
    │             (filled_fields / 21) × 100                 │
    │                                                         │
    │  save_feature_vector(case_id, feature_vector)         │
    │        └──► Upsert to BorrowerFeature table           │
    │                                                         │
    └─────────────────────┬───────────────────────────────────┘
                          │
                          ▼

┌─────────────────────────────────────────────────────────────────┐
│                      DATABASE LAYER                              │
└─────────────────────────────────────────────────────────────────┘

    ┌─────────────────────┐         ┌─────────────────────┐
    │  extracted_fields   │         │  borrower_features  │
    ├─────────────────────┤         ├─────────────────────┤
    │ • id (PK)           │         │ • id (PK)           │
    │ • case_id (FK)      │         │ • case_id (FK,UQ)   │
    │ • document_id (FK)  │         │ • full_name         │
    │ • field_name        │         │ • pan_number        │
    │ • field_value       │         │ • cibil_score       │
    │ • confidence        │         │ • annual_turnover   │
    │ • source            │         │ • ... (21 fields)   │
    │ • created_at        │         │ • completeness      │
    └─────────────────────┘         │ • created_at        │
           │                        │ • updated_at        │
           │                        └─────────────────────┘
           │                                   │
           └───────────────┬───────────────────┘
                           │
                           ▼

┌─────────────────────────────────────────────────────────────────┐
│                        API LAYER                                 │
│                  (extraction.py endpoints)                       │
└─────────────────────────────────────────────────────────────────┘

    POST /extraction/case/{case_id}/extract
         │
         ├──► Fetch all documents with OCR
         ├──► For each document:
         │      extract_fields()
         │      save_extracted_fields()
         │
         ├──► assemble_features()
         ├──► save_feature_vector()
         │
         └──► Update case status → FEATURES_EXTRACTED

    GET /extraction/case/{case_id}/fields
         └──► Return List[ExtractedFieldItem]

    GET /extraction/case/{case_id}/features
         └──► Return BorrowerFeatureVector

           │
           ▼

┌─────────────────────────────────────────────────────────────────┐
│                       OUTPUT LAYER                               │
└─────────────────────────────────────────────────────────────────┘

    ┌──────────────────────────────┐
    │  BorrowerFeatureVector       │ ──► To Stage 4 (Eligibility)
    │                              │
    │  Identity:                   │
    │  • full_name                 │
    │  • pan_number                │
    │  • aadhaar_number           │
    │  • dob                       │
    │                              │
    │  Business:                   │
    │  • entity_type               │
    │  • gstin                     │
    │  • industry_type             │
    │  • business_vintage_years    │
    │                              │
    │  Financial:                  │
    │  • annual_turnover          │
    │  • itr_total_income         │
    │  • avg_monthly_balance      │
    │  • emi_outflow_monthly      │
    │                              │
    │  Credit:                     │
    │  • cibil_score              │
    │  • active_loan_count        │
    │  • overdue_count            │
    │  • enquiry_count_6m         │
    │                              │
    │  Meta:                       │
    │  • feature_completeness     │
    └──────────────────────────────┘
```

---

## Data Flow Diagram

```
┌─────────────┐
│   Upload    │
│  Documents  │
└──────┬──────┘
       │
       ▼
┌─────────────┐
│  Stage 1:   │
│  OCR + ML   │
│  Classify   │
└──────┬──────┘
       │
       │ ocr_text + doc_type
       │
       ▼
┌──────────────────────────────────────────────┐
│          Stage 2: EXTRACTION                 │
│                                              │
│  ┌────────────────────────────────────┐     │
│  │  For each document:                │     │
│  │                                    │     │
│  │  1. Route by doc_type              │     │
│  │  2. Apply regex patterns           │     │
│  │  3. Extract field values           │     │
│  │  4. Validate formats               │     │
│  │  5. Calculate confidence           │     │
│  │  6. Save to extracted_fields       │     │
│  └────────────────────────────────────┘     │
│                                              │
│  ┌────────────────────────────────────┐     │
│  │  Feature Assembly:                 │     │
│  │                                    │     │
│  │  1. Collect all extracted fields   │     │
│  │  2. Fetch manual overrides         │     │
│  │  3. Apply priority logic           │     │
│  │  4. Convert field types            │     │
│  │  5. Calculate completeness         │     │
│  │  6. Save to borrower_features      │     │
│  └────────────────────────────────────┘     │
│                                              │
│  ┌────────────────────────────────────┐     │
│  │  Update Case:                      │     │
│  │                                    │     │
│  │  • status = FEATURES_EXTRACTED     │     │
│  │  • completeness_score = X%         │     │
│  └────────────────────────────────────┘     │
└──────────────────┬───────────────────────────┘
                   │
                   │ BorrowerFeatureVector
                   │
                   ▼
       ┌─────────────────────┐
       │   Stage 4:          │
       │   Eligibility       │
       │   Scoring           │
       └─────────────────────┘
```

---

## Priority Resolution Flow

```
For each field to assemble:

    ┌─────────────────────────────────┐
    │  Check extracted field          │
    └────────────┬────────────────────┘
                 │
                 ▼
    ┌────────────────────────────────────┐
    │  Is confidence ≥ 0.5?              │
    └────────┬──────────────────┬────────┘
             │ YES              │ NO
             ▼                  ▼
    ┌────────────────┐   ┌────────────────────┐
    │  Use extracted │   │ Manual exists?      │
    │     value      │   └────┬──────────┬────┘
    └────────────────┘        │ YES      │ NO
                              ▼          ▼
                     ┌────────────┐  ┌─────────────────┐
                     │ Use manual │  │ Extracted exists?│
                     │   value    │  └────┬──────┬─────┘
                     └────────────┘       │ YES  │ NO
                                          ▼      ▼
                                  ┌────────────┐ ┌──────┐
                                  │Use extracted│ │ NULL │
                                  │  (low conf) │ └──────┘
                                  └────────────┘

    All paths lead to:
    ┌─────────────────────────────────┐
    │  Convert to appropriate type    │
    └────────────┬────────────────────┘
                 │
                 ▼
    ┌─────────────────────────────────┐
    │  Add to BorrowerFeatureVector   │
    └─────────────────────────────────┘
```

---

## Validation Flow

```
    ┌─────────────────────────────────┐
    │  Field extracted from OCR        │
    └────────────┬────────────────────┘
                 │
                 ▼
    ┌────────────────────────────────────┐
    │  Check field_name                   │
    └─┬────────────┬──────────┬──────────┘
      │            │          │
      ▼            ▼          ▼
┌──────────┐ ┌─────────┐ ┌──────────┐
│   PAN    │ │  GSTIN  │ │  CIBIL   │  ... etc
└────┬─────┘ └────┬────┘ └────┬─────┘
     │            │           │
     ▼            ▼           ▼
┌─────────────────────────────────────┐
│  Validate format & business rules    │
├─────────────────────────────────────┤
│                                     │
│  PAN:                               │
│  • Length = 10                      │
│  • Format: [A-Z]{5}[0-9]{4}[A-Z]   │
│  • 4th char in valid entity types  │
│                                     │
│  GSTIN:                             │
│  • Length = 15                      │
│  • State code in 01-38              │
│  • Embedded PAN valid               │
│                                     │
│  CIBIL Score:                       │
│  • Integer                          │
│  • Range: 300-900                   │
│                                     │
└────────┬────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────┐
│  Valid?                              │
└───┬─────────────────────┬───────────┘
    │ YES                 │ NO
    ▼                     ▼
┌────────────┐    ┌──────────────────┐
│ Keep       │    │ Lower confidence │
│ confidence │    │ by 0.5×          │
└────────────┘    └──────────────────┘
         │                │
         └────────┬───────┘
                  │
                  ▼
         ┌────────────────┐
         │  Save field    │
         └────────────────┘
```

---

## Type Conversion Flow

```
    ┌─────────────────────────────────┐
    │  Field value (always string)     │
    └────────────┬────────────────────┘
                 │
                 ▼
    ┌────────────────────────────────────┐
    │  Determine target type by field_name │
    └─┬───────┬────────┬────────┬────────┘
      │       │        │        │
      ▼       ▼        ▼        ▼
   ┌────┐ ┌──────┐ ┌──────┐ ┌──────┐
   │String│ │ Date │ │Float │ │ Int  │
   └──┬─┘ └──┬───┘ └──┬───┘ └──┬───┘
      │      │        │        │
      │      │        │        │
      ▼      ▼        ▼        ▼
   ┌─────────────────────────────────┐
   │  Type-specific conversion        │
   ├─────────────────────────────────┤
   │                                 │
   │  String: value.strip()          │
   │                                 │
   │  Date:                          │
   │    "15/03/1985"                 │
   │      → datetime.strptime(...)   │
   │      → date(1985, 3, 15)        │
   │                                 │
   │  Float:                         │
   │    "1,25,00,000"                │
   │      → remove commas            │
   │      → float(value)             │
   │      → 12500000.0               │
   │                                 │
   │  Integer:                       │
   │    "750" → int(750)             │
   │    "4.0" → int(float("4.0"))    │
   │      → 4                        │
   │                                 │
   └────────┬────────────────────────┘
            │
            ▼
   ┌────────────────────┐
   │  Typed value ready │
   │  for feature vector│
   └────────────────────┘
```

---

## Document Type Routing

```
    ┌─────────────────┐
    │  Document       │
    │  doc_type       │
    └────────┬────────┘
             │
             ▼
    ┌────────────────────────────┐
    │  Route to extractor        │
    └─┬──┬──┬──┬──┬──┬──┬────────┘
      │  │  │  │  │  │  │
      ▼  ▼  ▼  ▼  ▼  ▼  ▼
     PAN AA GST GST CI IT FS
         DH CRT RET BI TR

┌─────────────────────────────────────┐
│  _extract_pan_card()                │
│  • PAN: [A-Z]{5}[0-9]{4}[A-Z]      │
│  • Name: near "Name"                │
│  • DOB: near "Date of Birth"        │
└─────────────────────────────────────┘

┌─────────────────────────────────────┐
│  _extract_aadhaar()                 │
│  • Aadhaar: \d{4}\s?\d{4}\s?\d{4}  │
│  • Name: near "Name"                │
│  • Address: after "Address"         │
└─────────────────────────────────────┘

┌─────────────────────────────────────┐
│  _extract_gst_certificate()         │
│  • GSTIN: complex pattern           │
│  • Business: near "Legal Name"      │
│  • State: from state code           │
└─────────────────────────────────────┘

┌─────────────────────────────────────┐
│  _extract_gst_returns()             │
│  • Taxable: near "Taxable Value"    │
│  • CGST/SGST: near tax headers      │
└─────────────────────────────────────┘

┌─────────────────────────────────────┐
│  _extract_cibil_report()            │
│  • Score: [3-9]\d{2}                │
│  • Loans: near "Active"             │
└─────────────────────────────────────┘

┌─────────────────────────────────────┐
│  _extract_itr()                     │
│  • Income: near "Total Income"      │
│  • AY: 20\d{2}-\d{2}                │
└─────────────────────────────────────┘

┌─────────────────────────────────────┐
│  _extract_financial_statements()    │
│  • Revenue: near "Revenue"          │
│  • Profit: near "Net Profit"        │
└─────────────────────────────────────┘
```

---

## Class Hierarchy

```
┌─────────────────────────────────────┐
│        FieldExtractor               │
├─────────────────────────────────────┤
│ Attributes:                         │
│ • confidence_threshold: float       │
│                                     │
│ Methods:                            │
│ • extract_fields()                  │
│ • _extract_pan_card()               │
│ • _extract_aadhaar()                │
│ • _extract_gst_certificate()        │
│ • _extract_gst_returns()            │
│ • _extract_cibil_report()           │
│ • _extract_itr()                    │
│ • _extract_financial_statements()   │
│ • _validate_pan()                   │
│ • _validate_gstin()                 │
│ • _validate_field()                 │
└─────────────────────────────────────┘

┌─────────────────────────────────────┐
│      FeatureAssembler               │
├─────────────────────────────────────┤
│ Attributes:                         │
│ • confidence_threshold: float       │
│                                     │
│ Methods:                            │
│ • assemble_features()               │
│ • _resolve_field_value()            │
│ • _convert_field_type()             │
│ • save_feature_vector()             │
│ • save_extracted_fields()           │
│ • get_extracted_fields()            │
│ • get_feature_vector()              │
└─────────────────────────────────────┘

   Singleton Factory Functions:
   • get_extractor() → FieldExtractor
   • get_assembler() → FeatureAssembler
```

---

## Key Design Decisions

### 1. **Regex over ML**
- **Reason**: Faster, no training data needed, deterministic
- **Trade-off**: Less flexible, requires pattern updates

### 2. **Confidence-based Priority**
- **Reason**: Balance automation with data quality
- **Threshold**: 0.5 (configurable)

### 3. **Validation Adjusts Confidence**
- **Reason**: Keep data even if invalid (for review)
- **Approach**: Lower confidence by 50% if invalid

### 4. **Singleton Extractors**
- **Reason**: Avoid reinitialization overhead
- **Benefit**: Faster request processing

### 5. **Async Database Operations**
- **Reason**: Non-blocking I/O for scalability
- **Benefit**: Handle concurrent requests

### 6. **Upsert for Feature Vector**
- **Reason**: Allow re-extraction without duplicates
- **Benefit**: Idempotent operations

---

This architecture provides a robust, maintainable, and scalable solution for extracting structured data from unstructured OCR text.
