# DSA Case OS — Parallel Cowork Task Breakdown

## How to Use This Document

Each task below is **fully independent** and can be given to a separate Cowork session.
The foundation project (folder structure, DB schema, shared models, route stubs, Docker)
is already built and lives in the `dsa-case-os/` folder.

**Before starting any task:** Copy the `dsa-case-os/` folder into that Cowork session's
workspace so the agent has access to the shared schema, enums, and models.

**Dependency rule:** Tasks marked ★ can start immediately. Tasks marked ◆ need the
output of another task — start them after the dependency is done or have the agent
code against the shared interfaces (which are already defined in `schemas/shared.py`).

---

## Task Map (10 Parallel Tracks)

```
FOUNDATION (done) ──┬── T1: File Upload + Case Creation     ★
                    ├── T2: OCR Pipeline                    ★
                    ├── T3: Document Classifier              ★ (needs training data)
                    ├── T4: Checklist Engine                 ★
                    ├── T5: Regex Field Extraction           ★
                    ├── T6: Bank Statement Analyzer          ★
                    ├── T7: Knowledge Base + Lender Ingestion ★
                    ├── T8: Eligibility Engine               ◆ (uses T5/T6/T7 interfaces)
                    ├── T9: Case Report Generator (PDF)      ◆ (uses T8 interface)
                    ├── T10: DSA Copilot Chatbot             ◆ (uses T7 data)
                    ├── T11: React Frontend                  ★
                    └── T12: Auth + User Management          ★
```

---

## TASK 1: File Upload + Case Creation (Stage 0)

**Complexity:** Medium | **Est. Time:** 3-4 hours | **Dependency:** ★ None

### Prompt for Cowork

```
You are building the FILE UPLOAD AND CASE CREATION module for the DSA Case OS
— a credit intelligence platform for business loan DSAs in India.

## YOUR TASK
Implement Stage 0: Case Entry (Chaos Ingestion). This module accepts messy,
real-world document uploads and creates structured Case objects.

## PROJECT CONTEXT
- Backend: Python FastAPI (project is in the workspace folder dsa-case-os/)
- Database: PostgreSQL (schema in backend/app/db/schema.sql)
- Shared models: backend/app/schemas/shared.py
- Enums: backend/app/core/enums.py
- Config: backend/app/core/config.py
- Route stubs already exist in: backend/app/api/v1/endpoints/cases.py

## WHAT TO BUILD

### 1. File Storage Service (backend/app/services/file_storage.py)
- Abstract interface with local filesystem implementation (S3 later)
- Store files at: {STORAGE_PATH}/{case_id}/{filename}
- Return storage_key for DB reference
- Support: PDF, JPG, JPEG, PNG, TIFF, ZIP

### 2. Case Creation Service (backend/app/services/stages/stage0_case_entry.py)
- Generate Case ID: format CASE-YYYYMMDD-XXXX (4-digit sequential daily counter)
- Create case record in DB
- Handle file upload: single files + ZIP extraction
- ZIP handling: auto-flatten nested folders, ignore .DS_Store / __MACOSX
- Duplicate detection: SHA-256 hash check before storing
- File size validation: max 25MB per file, 100MB per case upload
- After upload, set case status to PROCESSING
- Store each file as a document record in the documents table

### 3. Wire Up the Endpoints (update cases.py router)
- POST /api/v1/cases/ → create new case
- POST /api/v1/cases/{case_id}/upload → upload files (multipart form)
- GET /api/v1/cases/ → list user's cases
- GET /api/v1/cases/{case_id} → get case details
- PATCH /api/v1/cases/{case_id} → update manual overrides
- DELETE /api/v1/cases/{case_id} → soft delete

### TECHNICAL REQUIREMENTS
- Use async SQLAlchemy (from app.db.database import get_db)
- Use Pydantic schemas from app.schemas.shared
- Use enums from app.core.enums
- Handle errors gracefully with proper HTTP status codes
- Add logging throughout
- Write unit tests in backend/tests/test_stage0.py

### DO NOT
- Build OCR or classification — that's a separate module
- Build authentication — just accept user_id as a parameter for now
- Use external cloud APIs — keep it local filesystem for MVP
```

---

## TASK 2: OCR Pipeline (Stage 1 — Step 1)

**Complexity:** Medium | **Est. Time:** 3-4 hours | **Dependency:** ★ None

### Prompt for Cowork

```
You are building the OCR TEXT EXTRACTION pipeline for the DSA Case OS
— a credit intelligence platform for business loan DSAs in India.

## YOUR TASK
Implement the OCR pipeline that extracts text from any uploaded document
(PDF or image). This is the first step of Stage 1: Document Intelligence.

## PROJECT CONTEXT
- Backend: Python FastAPI (project is in the workspace folder dsa-case-os/)
- Database schema: backend/app/db/schema.sql (see documents table — ocr_text, ocr_confidence fields)
- Shared models: backend/app/schemas/shared.py
- Config: backend/app/core/config.py

## WHAT TO BUILD

### 1. OCR Service (backend/app/services/stages/stage1_ocr.py)

Create a service with this logic:

**For native PDFs (text-based):**
- Use PyMuPDF (fitz) for direct text extraction
- Detect if PDF is text-based: check if extracted text length > 50 chars per page
- If text-based, use PyMuPDF directly (fast, accurate)

**For scanned PDFs (image-based):**
- If PyMuPDF yields little/no text, fall back to image-based OCR
- Convert PDF pages to images using PyMuPDF
- Run Tesseract OCR on each page image
- Concatenate results

**For image files (JPG, PNG, TIFF):**
- Run Tesseract OCR directly on the image
- Use Pillow for preprocessing: convert to grayscale, increase contrast if needed

**For multi-page PDFs:**
- Iterate through pages
- Extract text per page
- Return concatenated text with page markers: --- PAGE 1 ---, --- PAGE 2 ---

### 2. Service Interface
```python
class OCRService:
    async def extract_text(self, file_path: str, mime_type: str) -> OCRResult:
        """Returns OCRResult with text, confidence, page_count"""

class OCRResult:
    text: str
    confidence: float  # 0-1 average confidence
    page_count: int
    method: str  # "pymupdf" or "tesseract"
```

### 3. Update Document Records
- After OCR, update the documents table: ocr_text, ocr_confidence, page_count
- Set document status to "ocr_complete"

### 4. Wire Up Endpoint
- Update documents.py: GET /documents/{doc_id}/ocr-text

### TECHNICAL REQUIREMENTS
- Install: PyMuPDF (fitz), pytesseract, Pillow, pdfplumber
- Handle corrupt/unreadable files gracefully — don't crash, mark as failed
- Log processing time per document
- Write tests in backend/tests/test_ocr.py with sample PDF/image fixtures

### ACCURACY NOTE
Moderate accuracy is fine. OCR output is used for classification and keyword
matching, not verbatim data capture. Speed > perfection.

### DO NOT
- Build document classification — that's a separate module
- Build field extraction — that's a separate module
- Call any external APIs — all processing must be local
```

---

## TASK 3: Document Classifier (Stage 1 — Step 2)

**Complexity:** Medium-High | **Est. Time:** 4-5 hours | **Dependency:** ★ None (needs training data separately)

### Prompt for Cowork

```
You are building the DOCUMENT CLASSIFIER for the DSA Case OS
— a credit intelligence platform for business loan DSAs in India.

## YOUR TASK
Build a classifier that takes OCR text from a document and determines what
type of document it is (Aadhaar, PAN, Bank Statement, etc.).

## PROJECT CONTEXT
- Backend: Python FastAPI (project is in the workspace folder dsa-case-os/)
- Enums: backend/app/core/enums.py (DocumentType enum is the source of truth)
- Database: documents table has doc_type, classification_confidence fields

## WHAT TO BUILD

### 1. Classifier Service (backend/app/services/stages/stage1_classifier.py)

**Two-layer approach:**

**Layer 1: Keyword/Rule-Based Fallback (always available)**
Define keyword dictionaries for each document type:
- AADHAAR: ["UIDAI", "Unique Identification", "Aadhaar", "enrolment", "आधार"]
- PAN_PERSONAL: ["Permanent Account Number", "Income Tax Department", "NSDL"]
- PAN_BUSINESS: ["Permanent Account Number" + company/firm name patterns]
- GST_CERTIFICATE: ["GSTIN", "Goods and Services Tax", "Certificate of Registration"]
- GST_RETURNS: ["GSTR", "taxable value", "CGST", "SGST", "Return Period"]
- BANK_STATEMENT: ["Opening Balance", "Closing Balance", "Statement of Account", "debit", "credit"]
- ITR: ["Assessment Year", "Total Income", "ITR-", "Income Tax Return", "Verification"]
- FINANCIAL_STATEMENTS: ["Balance Sheet", "Profit and Loss", "Schedule", "Audit Report"]
- CIBIL_REPORT: ["TransUnion", "Credit Score", "Credit Information", "CIBIL"]
- UDYAM_SHOP_LICENSE: ["Udyam Registration", "MSME", "Shop and Establishment"]
- PROPERTY_DOCUMENTS: ["Sale Deed", "Registry", "Property Tax", "Conveyance"]

Score = (matched keywords / total keywords for that category)
Return category with highest score if > threshold.

**Layer 2: TF-IDF + Logistic Regression (when training data available)**
- TF-IDF vectorizer on OCR text
- Logistic Regression or Naive Bayes classifier
- Training pipeline: load labeled data, fit model, save with joblib
- Prediction: vectorize new text, predict with confidence

**Logic:** Use ML model if available and confidence > 0.7, otherwise fall back to keyword rules.

### 2. Training Pipeline (backend/app/services/stages/classifier_trainer.py)
- Load labeled training data from a CSV: filename, doc_type, text
- TF-IDF vectorize
- Train LogisticRegression
- Cross-validate and report accuracy
- Save model + vectorizer with joblib to models/ directory
- Support retraining with new data

### 3. Service Interface
```python
class DocumentClassifier:
    def classify(self, ocr_text: str) -> ClassificationResult:
        """Returns doc_type and confidence"""

class ClassificationResult:
    doc_type: DocumentType
    confidence: float  # 0-1
    method: str  # "ml" or "keyword"
```

### 4. Wire Up
- After classification, update documents table: doc_type, classification_confidence, status="classified"
- POST /documents/{doc_id}/reclassify endpoint for manual correction

### CONFIDENCE THRESHOLDS
- Aadhaar: 0.80, PAN: 0.80, GST Cert: 0.80, Bank Statement: 0.85
- ITR: 0.80, Financial: 0.75, CIBIL: 0.85, Udyam: 0.75
- Property: 0.70, Unknown: below threshold

### TESTS
- Write backend/tests/test_classifier.py
- Create synthetic test texts for each category
- Test both keyword and ML paths

### DO NOT
- Build OCR — assume ocr_text is already available as input
- Build field extraction — that's a separate module
```

---

## TASK 4: Document Checklist Engine (Stage 1 — Steps 3-5)

**Complexity:** Medium | **Est. Time:** 3 hours | **Dependency:** ★ None

### Prompt for Cowork

```
You are building the DOCUMENT CHECKLIST ENGINE for the DSA Case OS
— a credit intelligence platform for business loan DSAs in India.

## YOUR TASK
Given a case's classified documents and selected loan program, generate a
completeness checklist showing what's present, missing, and the overall
completeness score. Also handle progressive data capture (manual field entry).

## PROJECT CONTEXT
- Backend: Python FastAPI (project is in the workspace folder dsa-case-os/)
- Enums: backend/app/core/enums.py (ProgramType, DocumentType, EntityType)
- Schemas: backend/app/schemas/shared.py (DocumentChecklist model)
- Database: cases table (completeness_score), documents table (doc_type)

## WHAT TO BUILD

### 1. Checklist Rules (backend/app/services/stages/stage1_checklist.py)

Define required documents per program:

BANKING program required:
- bank_statement (12 months) — CRITICAL
- pan_personal or pan_business
- aadhaar
- gst_certificate
- cibil_report

INCOME program required:
- itr (2-3 years)
- financial_statements
- pan_personal or pan_business
- aadhaar
- cibil_report

HYBRID program required:
- bank_statement + itr + gst_certificate + cibil_report + pan + aadhaar

Optional for all programs:
- udyam_shop_license
- property_documents
- gst_returns

### 2. Completeness Score Calculator
- Score = (available required docs / total required docs) × 100
- If completeness < 60%, flag as WARNING
- If completeness < 30%, flag as CRITICAL
- Score updates dynamically whenever new docs are uploaded or manual data entered

### 3. Progressive Data Capture
- If CIBIL report not uploaded → prompt for manual CIBIL score
- If GST certificate not uploaded → prompt for business vintage year + entity type
- If GST returns not uploaded → prompt for approximate monthly turnover
- Track which fields are manual vs extracted

### 4. Service Interface
```python
class ChecklistEngine:
    def generate_checklist(self, case_id, program_type, classified_docs) -> DocumentChecklist
    def get_missing_manual_prompts(self, case_id) -> List[ManualFieldPrompt]
    def update_completeness(self, case_id) -> float
```

### 5. Wire Up Endpoints
- GET /cases/{case_id}/checklist → DocumentChecklist
- PATCH /cases/{case_id} → update manual overrides, recalculate completeness

### TESTS
- backend/tests/test_checklist.py
- Test each program type with various document combinations
- Test completeness calculation edge cases

### DO NOT
- Build OCR or classification — assume documents are already classified
- Build the extraction logic — just check what doc types are present
```

---

## TASK 5: Regex Field Extraction (Stage 2)

**Complexity:** High | **Est. Time:** 5-6 hours | **Dependency:** ★ None

### Prompt for Cowork

```
You are building the REGEX FIELD EXTRACTION engine for the DSA Case OS
— a credit intelligence platform for business loan DSAs in India.

## YOUR TASK
Extract structured fields (PAN number, GSTIN, CIBIL score, names, dates, etc.)
from OCR text using regex patterns and anchor keywords. Then assemble these into
a Borrower Feature Vector.

## PROJECT CONTEXT
- Backend: Python FastAPI (project is in the workspace folder dsa-case-os/)
- Schemas: backend/app/schemas/shared.py (BorrowerFeatureVector, ExtractedFieldItem)
- Database: extracted_fields table, borrower_features table
- Enums: backend/app/core/enums.py

## WHAT TO BUILD

### 1. Extraction Rules (backend/app/services/stages/stage2_extraction.py)

Per-document extraction logic:

**PAN Card:**
- PAN number: regex [A-Z]{5}[0-9]{4}[A-Z]
- Name: text near "Name" keyword
- DOB: pattern dd/mm/yyyy near "Date of Birth"

**Aadhaar Card:**
- Aadhaar number: XXXX XXXX XXXX (12 digits, may have spaces)
- Name: text near "Name" / first prominent name
- DOB: dd/mm/yyyy pattern
- Address: multi-line text after "Address"

**GST Certificate:**
- GSTIN: [0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][0-9][A-Z][0-9A-Z]
- Business name: text near "Legal Name" or "Trade Name"
- Registration date: date pattern near "Date of Registration"
- State: from first 2 digits of GSTIN (state code mapping)

**GST Returns:**
- Total taxable value: numeric near "Total Taxable Value"
- CGST/SGST amounts: numeric near CGST/SGST headers
- Filing period: month/year patterns

**CIBIL Report:**
- Credit score: 3-digit number (300-900) near "Score" keyword
- Active loans: count from loan table
- Overdue accounts: count where "Overdue" or DPD > 0
- Enquiry count: number near "Enquiry" section

**ITR:**
- Total income: numeric near "Total Income" / "Gross Total Income"
- Assessment year: pattern "AY 20XX-XX"
- Tax paid: numeric near "Tax Paid" / "Total Tax"
- Business income: numeric near "Business" income head

**Financial Statements:**
- Revenue: numeric near "Revenue" / "Total Income" / "Sales"
- Net profit: numeric near "Net Profit" / "Profit After Tax"
- Net worth: numeric near "Net Worth" / "Shareholders Fund"

### 2. Feature Vector Assembly (backend/app/services/stages/stage2_features.py)
- Take all extracted fields for a case
- Merge into a single BorrowerFeatureVector
- Priority: extraction > manual override (except when extraction confidence < 0.5)
- Calculate feature_completeness: (filled fields / total fields) × 100

### 3. GST Turnover Strategy
Priority order:
1. Parse GST returns directly → annual taxable turnover
2. Estimate from bank statement monthly credits × 12 (if bank analysis available)
3. Manual entry fallback

### 4. Wire Up Endpoints
- POST /extraction/case/{case_id}/extract → run extraction pipeline
- GET /extraction/case/{case_id}/fields → list all extracted fields
- GET /extraction/case/{case_id}/features → get assembled feature vector

### 5. Each Extracted Field Stored With:
- field_name, field_value, confidence (0-1), source ("extraction"/"manual"/"computed")

### IMPORTANT REGEX NOTES
- Indian document formats have OCR noise — be liberal with whitespace matching
- PAN 4th character indicates entity type (P=Personal, C=Company, F=Firm, etc.)
- GSTIN first 2 digits = state code, useful for validation
- Currency amounts may have commas (1,00,000 Indian format) or decimals

### TESTS
- backend/tests/test_extraction.py
- Create sample OCR text for each document type with known field values
- Test edge cases: noisy OCR, missing fields, multiple matches

### DO NOT
- Build OCR — assume ocr_text is available
- Build bank statement analysis — that's a separate module (T6)
- Build eligibility scoring — that's separate (T8)
```

---

## TASK 6: Bank Statement Analyzer Integration (Stage 2)

**Complexity:** Medium | **Est. Time:** 3-4 hours | **Dependency:** ★ None

### Prompt for Cowork

```
You are building the BANK STATEMENT ANALYZER for the DSA Case OS
— a credit intelligence platform for business loan DSAs in India.

## YOUR TASK
Build a bank statement analysis module that extracts key financial metrics
from bank statement text/PDFs. This is a critical component of the Borrower
Feature Vector.

## PROJECT CONTEXT
- Backend: Python FastAPI (project is in the workspace folder dsa-case-os/)
- Schemas: see BorrowerFeatureVector in backend/app/schemas/shared.py
- This module's outputs feed into: avg_monthly_balance, monthly_credit_avg,
  emi_outflow_monthly, bounce_count_12m, cash_deposit_ratio

## WHAT TO BUILD

### 1. Bank Statement Parser (backend/app/services/stages/stage2_bank_analyzer.py)

**Input:** OCR text from bank statement (multiple pages, 12 months typically)

**Extraction targets:**

**Transaction Parsing:**
- Parse date, description, debit, credit, balance columns
- Handle multiple bank formats: SBI, HDFC, ICICI, Axis, Kotak, BOB etc.
- Indian date formats: dd/mm/yyyy, dd-mm-yyyy, dd-MMM-yyyy
- Indian number formats: 1,00,000.00 (lakhs) or 100000.00

**Computed Metrics:**
1. avg_monthly_balance: Average of month-end closing balances
2. monthly_credit_avg: Average of total monthly credits
3. emi_outflow_monthly: Detect EMI patterns (recurring same-amount debits, keywords: EMI, LOAN, NACH)
4. bounce_count_12m: Count of bounced cheques (keywords: BOUNCE, RETURN, DISHON, INSUFFICIENT)
5. cash_deposit_ratio: Cash deposits / total credits (keywords: CASH DEP, BY CASH, CASH DEPOSIT)
6. total_debits_monthly: Average monthly total debits
7. peak_balance: Highest balance in the period
8. min_balance: Lowest balance in the period

### 2. Multi-Bank Format Handling
Create format detectors for major banks:
- SBI: specific header patterns
- HDFC: specific column layout
- ICICI: specific format
- Generic fallback: attempt column detection heuristically

### 3. Service Interface
```python
class BankStatementAnalyzer:
    async def analyze(self, ocr_text: str, bank_name: Optional[str] = None) -> BankAnalysisResult

class BankAnalysisResult:
    avg_monthly_balance: float
    monthly_credit_avg: float
    emi_outflow_monthly: float
    bounce_count_12m: int
    cash_deposit_ratio: float
    total_debits_monthly: float
    peak_balance: float
    min_balance: float
    statement_period_months: int
    confidence: float
    bank_detected: Optional[str]
    monthly_summary: List[MonthlySummary]  # per-month breakdown
```

### 4. Feed Into Feature Vector
- Save results as extracted_fields in the DB
- Update borrower_features table with bank analysis outputs

### TESTS
- backend/tests/test_bank_analyzer.py
- Create sample bank statement text for SBI, HDFC, ICICI formats
- Test edge cases: partial statements, missing columns, unusual formats

### DO NOT
- Build OCR — assume text is already extracted
- Build the full feature vector assembly — just provide your outputs
```

---

## TASK 7: Knowledge Base + Lender Ingestion (Stage 3)

**Complexity:** Medium-High | **Est. Time:** 4-5 hours | **Dependency:** ★ None

### Prompt for Cowork

```
You are building the KNOWLEDGE BASE AND LENDER INGESTION system for DSA Case OS
— a credit intelligence platform for business loan DSAs in India.

## YOUR TASK
Build the system that stores, manages, and queries lender eligibility rules,
branch/RM contacts, and product information. Also build the ingestion pipeline
to parse lender one-pager PDFs into structured rules.

## PROJECT CONTEXT
- Backend: Python FastAPI (project is in the workspace folder dsa-case-os/)
- Database: lenders, lender_products, lender_branches, lender_rms tables
  (see backend/app/db/schema.sql)
- Config: ANTHROPIC_API_KEY in backend/app/core/config.py (for LLM ingestion)
- Route stubs: backend/app/api/v1/endpoints/lenders.py

## WHAT TO BUILD

### 1. Lender CRUD Service (backend/app/services/lender_service.py)
- Create/update/list lenders
- Create/update/list lender products (with all rule fields)
- Create/update lender branches and RM contacts
- Query: find all products matching a program type
- Query: find all lenders active in a given pincode

### 2. Lender One-Pager Ingestion (backend/app/services/stages/stage3_ingestion.py)

Pipeline to convert unstructured lender PDFs into structured rules:

Step 1: Extract text from lender one-pager PDF (use PyMuPDF)
Step 2: Send to Claude API with this structured prompt:

```
Extract the following fields from this lender product document.
Return as JSON:
{
  "lender_name": "",
  "product_name": "",
  "program_type": "banking|income|hybrid",
  "min_turnover_annual": null,  // in Lakhs
  "min_vintage_years": null,
  "min_cibil_score": null,
  "max_foir": null,
  "eligible_entity_types": [],
  "eligible_industries": [],
  "excluded_industries": [],
  "serviceable_pincodes": [],
  "min_ticket_size": null,
  "max_ticket_size": null,
  "required_documents": [],
  "interest_rate_range": "",
  "expected_tat_days": null,
  "processing_fee_pct": null,
  "usps": ""
}
Document text:
{ocr_text}
```

Step 3: Parse Claude's JSON response
Step 4: Save to lender_products table with version tracking
Step 5: Flag for human review (add a needs_review boolean)

### 3. Manual Rule Entry
- API to directly create/update lender product rules via JSON
- Bulk import from CSV/JSON file

### 4. Geo Lending Graph
- Store pincode → city → lender → branch → RM mappings
- Query: given a pincode, return all active lenders + their local RMs
- Support partial pincode matching (first 3 digits = region)

### 5. Wire Up Endpoints (update lenders.py)
- GET /lenders/ → list all lenders
- POST /lenders/ → create lender
- GET /lenders/{lender_id}/products → list products
- POST /lenders/ingest → upload one-pager PDF, auto-extract rules
- POST /lenders/bulk-import → import from CSV/JSON
- GET /lenders/by-pincode/{pincode} → lenders active in area
- CRUD for branches and RMs

### TESTS
- backend/tests/test_knowledge_base.py
- Test CRUD operations
- Test pincode querying
- Mock Claude API for ingestion tests

### DO NOT
- Build the eligibility scoring engine — that uses this data but is separate (T8)
- Build the chatbot — that queries this data but is separate (T10)
```

---

## TASK 8: Eligibility Engine (Stage 4)

**Complexity:** High | **Est. Time:** 5-6 hours | **Dependency:** ◆ Uses interfaces from T5, T6, T7

### Prompt for Cowork

```
You are building the ELIGIBILITY ENGINE for the DSA Case OS
— a credit intelligence platform for business loan DSAs in India.

## YOUR TASK
Match the Borrower Feature Vector against Lender Rules to produce a ranked
list of eligible lenders with probability scores. This is the core intelligence
of the entire system.

## PROJECT CONTEXT
- Backend: Python FastAPI (project is in the workspace folder dsa-case-os/)
- Input: BorrowerFeatureVector (schema in backend/app/schemas/shared.py)
- Input: Lender product rules (lender_products table in backend/app/db/schema.sql)
- Output: EligibilityResponse with ranked results (schema in backend/app/schemas/shared.py)
- Route stubs: backend/app/api/v1/endpoints/eligibility.py

## WHAT TO BUILD

### 1. Eligibility Service (backend/app/services/stages/stage4_eligibility.py)

**Three-layer scoring architecture:**

#### Layer 1: Hard Filters (Pass/Fail)
If ANY hard filter fails, the lender is eliminated:
- Pincode not in lender's serviceable_pincodes → FAIL
- Entity type not in eligible_entity_types → FAIL
- CIBIL score < min_cibil_score → FAIL
- Industry in excluded_industries → FAIL
- Turnover < min_turnover (with 10% tolerance margin) → FAIL
- Vintage < min_vintage_years → FAIL

Record WHICH filter(s) failed in hard_filter_details.

#### Layer 2: Weighted Scoring (for lenders that pass hard filters)

Calculate composite eligibility_score (0-100):

| Component        | Weight | Scoring Logic                                              |
|-----------------|--------|-----------------------------------------------------------|
| CIBIL Band      | 25%    | 750+ = 100, 700-749 = 80, 650-699 = 60, <650 = 30       |
| Turnover Band   | 25%    | ratio of borrower turnover to lender minimum               |
| Business Vintage| 15%    | 5+ yrs = 100, 3-5 = 80, 2-3 = 60, <2 = 30              |
| Banking Strength| 20%    | composite of avg_balance, credit regularity, bounce ratio  |
| FOIR            | 10%    | <40% = 100, 40-55% = 70, 55-65% = 40, >65% = 0          |
| Industry Risk   | 5%     | preferred industry = 100, neutral = 60, borderline = 30   |

FOIR calculation: (emi_outflow_monthly / monthly_credit_avg) if both available.

#### Layer 3: Confidence Score
- Calculate based on data completeness
- confidence = (number of scoring components with real data / total components)
- Flag which missing data would improve the score

### 2. Ranking Logic
- Sort lenders by eligibility_score descending
- Assign approval_probability: score >= 75 = HIGH, 50-74 = MEDIUM, <50 = LOW
- Estimate ticket range: based on lender's min/max ticket and borrower's turnover
- Assign rank 1, 2, 3...

### 3. Missing Data Advisor
- For each lender that barely fails or could score higher, identify what
  additional data would help
- Example: "Providing CIBIL report would enable scoring for 5 more lenders"

### 4. Wire Up Endpoints (update eligibility.py)
- POST /eligibility/case/{case_id}/score → run scoring, save results
- GET /eligibility/case/{case_id}/results → get saved results

### 5. Save Results
- Store per-lender results in eligibility_results table
- Update case status to "eligibility_scored"

### TESTS
- backend/tests/test_eligibility.py
- Create test cases: strong borrower (should match many), weak borrower (few matches)
- Test hard filter edge cases
- Test scoring math accuracy
- Test with missing data (partial feature vectors)

### DO NOT
- Build the feature vector extraction — it's already done by T5/T6
- Build the knowledge base — it's already built by T7
- Build the report — that's T9
```

---

## TASK 9: Case Intelligence Report Generator (Stage 5)

**Complexity:** Medium-High | **Est. Time:** 4-5 hours | **Dependency:** ◆ Uses T8 output format

### Prompt for Cowork

```
You are building the CASE INTELLIGENCE REPORT GENERATOR for DSA Case OS
— a credit intelligence platform for business loan DSAs in India.

## YOUR TASK
Generate a professional, shareable PDF case report that summarizes the
borrower profile, shows matched lenders, highlights strengths and risks,
and provides a submission strategy. This is the PRIMARY PAID DELIVERABLE.

## PROJECT CONTEXT
- Backend: Python FastAPI (project is in the workspace folder dsa-case-os/)
- Input: CaseReportData (schema in backend/app/schemas/shared.py)
- Database: case_reports table (backend/app/db/schema.sql)
- Route stubs: backend/app/api/v1/endpoints/reports.py

## WHAT TO BUILD

### 1. Report Data Assembly (backend/app/services/stages/stage5_report.py)

Gather all data for the report:
- BorrowerFeatureVector from borrower_features table
- DocumentChecklist from checklist engine
- EligibilityResults from eligibility_results table
- Derive strengths and risks from the data

**Strengths detection logic:**
- CIBIL >= 750 → "Excellent credit score ({score})"
- Turnover > 2x lender minimum → "Strong turnover"
- Vintage > 5 years → "Well-established business"
- Bounce count = 0 → "Clean banking with zero bounces"
- Low FOIR < 40% → "Low existing obligations"

**Risk flags detection logic:**
- CIBIL < 650 → "Low credit score may limit options"
- Vintage < 2 years → "Low business vintage"
- Bounces > 3 → "Banking irregularities (bounced cheques)"
- High cash deposits > 40% → "High cash deposit ratio"
- FOIR > 55% → "High existing debt obligations"
- Missing critical documents → "Incomplete documentation"

**Submission strategy:**
- Recommend approaching top-ranked lender first
- Suggest sequence based on scores
- Note which lenders to avoid and why

### 2. PDF Generation (backend/app/services/stages/stage5_pdf_generator.py)

Use ReportLab to generate a professional PDF:

**Page 1: Cover**
- "Case Intelligence Report"
- Case ID, Date, Borrower Name
- Prepared by DSA Case OS

**Page 2: Borrower Profile Summary**
- Key details in a clean table: Name, Entity Type, Vintage, Industry, Location
- Key financial metrics: Turnover, CIBIL, Average Balance

**Page 3: Case Completeness**
- Visual checklist: ✓ Available / ✗ Missing documents
- Completeness percentage (use a progress bar visual)

**Page 4: Strengths & Risks**
- Green bullet points for strengths
- Red bullet points for risk flags

**Page 5+: Lender Match Table**
- Table with columns: Rank, Lender, Product, Score, Probability, Ticket Range
- Top 10 lenders, sorted by rank
- Color-coded: green (HIGH), yellow (MEDIUM), red (LOW)

**Final Page: Recommendations**
- Submission strategy text
- Missing data advisory
- Expected loan range

### 3. WhatsApp Summary
- Generate a 5-line text summary for WhatsApp sharing:
  "📋 Case: {case_id} | {borrower_name}
   📊 CIBIL: {score} | Turnover: ₹{amount}L
   ✅ Top Match: {lender} ({probability})
   📈 Matched {n} lenders | Score: {top_score}/100
   🔗 Full report: {link}"

### 4. Wire Up Endpoints (update reports.py)
- POST /reports/case/{case_id}/generate → generate report
- GET /reports/case/{case_id}/report → get report data (JSON)
- GET /reports/case/{case_id}/report/pdf → download PDF

### TESTS
- backend/tests/test_report.py
- Test report data assembly with mock data
- Test PDF generation produces valid PDF
- Test edge cases: minimal data, no lender matches

### DO NOT
- Build eligibility scoring — that's already done (T8)
- Build the frontend view — that's T11
```

---

## TASK 10: DSA Copilot Chatbot (Stage 7)

**Complexity:** Medium | **Est. Time:** 3-4 hours | **Dependency:** ◆ Queries T7 knowledge base

### Prompt for Cowork

```
You are building the DSA COPILOT CHATBOT for the DSA Case OS
— a credit intelligence platform for business loan DSAs in India.

## YOUR TASK
Build a natural language chatbot that DSAs can use for quick lender queries
like "Which lenders fund below 650 CIBIL?" or "Who gives business loans in
pincode 400001?". This uses Claude API over the lender knowledge base.

## PROJECT CONTEXT
- Backend: Python FastAPI (project is in the workspace folder dsa-case-os/)
- Knowledge base: lenders, lender_products, lender_branches tables
- Config: ANTHROPIC_API_KEY, CLAUDE_MODEL in backend/app/core/config.py
- Schemas: CopilotQuery, CopilotResponse in backend/app/schemas/shared.py
- Database: copilot_queries table for logging
- Route stubs: backend/app/api/v1/endpoints/copilot.py

## WHAT TO BUILD

### 1. Knowledge Base Retriever (backend/app/services/stages/stage7_retriever.py)
- Query lender_products table to build context for LLM
- Implement smart query routing:
  - CIBIL queries → filter lender_products by min_cibil_score
  - Pincode queries → join with lender_branches
  - Product queries → filter by program_type, product features
  - Document queries → return required_documents for matched lenders
  - Comparison queries → return multiple lenders side-by-side

### 2. Copilot Service (backend/app/services/stages/stage7_copilot.py)

Flow:
1. Receive natural language query
2. Retrieve relevant lender data from DB (context building)
3. Build prompt for Claude API:

```
You are a knowledgeable assistant for Business Loan DSAs in India.
Answer the DSA's question using ONLY the lender data provided below.
Be specific: include lender names, numbers, and details.
If the data doesn't cover the question, say so clearly.

LENDER DATA:
{retrieved_lender_json}

DSA QUESTION: {user_query}
```

4. Call Claude API (anthropic Python SDK)
5. Return response with sources

### 3. Query Classification
Classify incoming queries to optimize retrieval:
- "cibil" / "credit score" → CIBIL-related query
- pincode / city name → Geographic query
- "documents" / "docs needed" → Document requirement query
- lender name mentioned → Specific lender query
- "compare" / "vs" / "which is better" → Comparison query
- "fastest" / "TAT" → Speed/process query

### 4. Logging
- Log every query and response in copilot_queries table
- Track response time
- Track sources used

### 5. Wire Up Endpoint (update copilot.py)
- POST /copilot/query → CopilotResponse

### EXAMPLE QUERIES TO SUPPORT
| Query | Expected Behavior |
|-------|------------------|
| "Which lenders fund below 650 CIBIL?" | Filter products where min_cibil < 650, return list |
| "Who gives business loans in 400001?" | Join with branches, return lenders in that pincode |
| "What docs does HDFC need?" | Return required_documents for HDFC products |
| "Which lender has fastest TAT?" | Sort by expected_tat_days |
| "Compare Bajaj and Tata Capital for banking program" | Side-by-side comparison |

### TESTS
- backend/tests/test_copilot.py
- Mock Claude API responses
- Test query classification
- Test retriever with sample lender data

### DO NOT
- Build the knowledge base CRUD — that's T7
- Build WhatsApp integration — that's Phase 2
```

---

## TASK 11: React Frontend

**Complexity:** High | **Est. Time:** 8-10 hours | **Dependency:** ★ Can start immediately (uses API interfaces)

### Prompt for Cowork

```
You are building the REACT FRONTEND for the DSA Case OS
— a credit intelligence platform for business loan DSAs in India.

## YOUR TASK
Build a complete React web application with all the pages needed for DSAs
to upload documents, view case status, see eligibility results, and use
the copilot chatbot.

## PROJECT CONTEXT
- Frontend lives in: dsa-case-os/frontend/
- Backend API base: http://localhost:8000/api/v1
- Auth: JWT token (stored in localStorage, sent as Bearer token)
- All API response schemas are in: backend/app/schemas/shared.py

## TECH STACK
- React 18 with Vite
- React Router for navigation
- Tailwind CSS for styling
- Axios for API calls
- React Query (TanStack Query) for data fetching
- React Hook Form for forms
- Lucide React for icons

## PAGES TO BUILD

### 1. Auth Pages
- /login — email + password form → POST /auth/login
- /register — name, email, phone, password → POST /auth/register
- Protected route wrapper (redirect to login if no token)

### 2. Dashboard (/dashboard)
- Case list: cards showing case_id, borrower_name, status, completeness, date
- Status badges: color-coded (green=report_generated, yellow=processing, red=failed)
- "New Case" button → /cases/new
- Search/filter by status
- Stats bar: total cases, avg completeness, cases this month

### 3. New Case (/cases/new)
- Step 1: Basic info form (borrower_name, entity_type, program_type, pincode)
- Step 2: File upload zone (drag & drop, multi-file, shows upload progress)
- Step 3: Review uploaded files, see auto-classifications
- After upload, redirect to case detail page

### 4. Case Detail (/cases/:caseId)
This is the MAIN page. Tabbed layout:

**Tab: Documents**
- List of all uploaded documents with: filename, doc_type badge, confidence %
- Upload more files button
- Reclassify button per document

**Tab: Checklist**
- Visual checklist: ✓ green for available, ✗ red for missing
- Completeness progress bar
- Manual data entry forms for missing fields (CIBIL score, vintage, etc.)
- Program type selector (Banking/Income/Hybrid)

**Tab: Borrower Profile**
- Display the BorrowerFeatureVector as a clean profile card
- Show which fields are extracted vs manual
- Edit/override any field

**Tab: Eligibility**
- "Run Eligibility Scoring" button
- Results table: Rank, Lender, Product, Score, Probability, Ticket Range
- Color-coded rows: green/yellow/red
- Expandable rows showing hard filter details
- "What's missing" section per lender

**Tab: Report**
- "Generate Report" button
- Report preview (rendered HTML version)
- "Download PDF" button
- WhatsApp share button (copy summary text)

### 5. Copilot (/copilot)
- Chat interface: message bubbles
- Input field at bottom
- Send query → POST /copilot/query
- Show response with typing animation
- Quick suggestion chips: "Low CIBIL lenders", "Lenders in Mumbai", etc.

### 6. Layout
- Sidebar navigation: Dashboard, New Case, Copilot, Settings
- Top bar: app name, user name, logout button
- Mobile responsive (sidebar collapses to hamburger menu)

## DESIGN GUIDELINES
- Clean, professional look — this is for business users
- Primary color: #2563EB (blue-600)
- Use consistent card-based layout
- Loading skeletons while data fetches
- Toast notifications for success/error
- Empty states with helpful messages

## API INTEGRATION
- Create an api.js utility with Axios instance (base URL, auth interceptor)
- React Query hooks per entity: useCases(), useCase(id), useEligibility(caseId)
- Optimistic updates where appropriate

## SETUP
Initialize with: npm create vite@latest . -- --template react
Install: tailwindcss, react-router-dom, axios, @tanstack/react-query,
         react-hook-form, lucide-react, react-dropzone, react-hot-toast

## TESTS
- At minimum: test that all pages render without crashing
- Test API integration hooks with mocked responses

## DO NOT
- Build backend logic — only consume the API
- Implement actual auth logic — just token storage and API headers
- Over-engineer state management — React Query handles server state
```

---

## TASK 12: JWT Authentication + User Management

**Complexity:** Low-Medium | **Est. Time:** 2-3 hours | **Dependency:** ★ None

### Prompt for Cowork

```
You are building the JWT AUTHENTICATION system for the DSA Case OS
— a credit intelligence platform for business loan DSAs in India.

## YOUR TASK
Implement user registration, login, and JWT-based auth middleware for the
FastAPI backend.

## PROJECT CONTEXT
- Backend: Python FastAPI (project is in the workspace folder dsa-case-os/)
- Config: SECRET_KEY, JWT_ALGORITHM, ACCESS_TOKEN_EXPIRE_MINUTES in backend/app/core/config.py
- Database: users table in backend/app/db/schema.sql
- Schemas: UserCreate, UserResponse, TokenResponse in backend/app/schemas/shared.py
- Route stubs: backend/app/api/v1/endpoints/auth.py

## WHAT TO BUILD

### 1. Password Hashing (backend/app/core/security.py)
- Use passlib with bcrypt
- hash_password(plain) → hashed
- verify_password(plain, hashed) → bool

### 2. JWT Token Management (backend/app/core/security.py)
- create_access_token(user_id, email) → JWT string
- decode_token(token) → payload dict
- Token payload: {sub: user_id, email: email, exp: expiry}

### 3. Auth Dependency (backend/app/core/deps.py)
- get_current_user dependency: extract token from Authorization header,
  decode, fetch user from DB, return user object
- Raise 401 if token invalid/expired/user not found

### 4. Auth Endpoints (update auth.py)
- POST /auth/register → create user, return UserResponse
  - Validate email uniqueness
  - Hash password before storing
- POST /auth/login → validate credentials, return TokenResponse
  - Accept email + password
  - Return JWT access token
- GET /auth/me → return current user info (requires auth)

### 5. Protect Other Routes
- Export the get_current_user dependency
- Other route files can use: current_user = Depends(get_current_user)
- Don't modify other route files — just make the dependency available

### TESTS
- backend/tests/test_auth.py
- Test registration (success + duplicate email)
- Test login (success + wrong password)
- Test protected endpoint access (valid token + no token + expired token)

### DO NOT
- Build OAuth/social login — just email+password for MVP
- Build email verification — skip for MVP
- Build password reset — skip for MVP
- Modify other endpoint files — just provide the dependency
```

---

## Integration Order

After all tasks are complete, integration happens in this order:

```
1. T12 (Auth) → add Depends(get_current_user) to all route files
2. T1 (Upload) → verify case creation + file storage works
3. T2 (OCR) → connect to T1: after upload, trigger OCR
4. T3 (Classifier) → connect to T2: after OCR, classify
5. T4 (Checklist) → connect to T3: after classification, generate checklist
6. T5 + T6 (Extraction) → connect to T2: after OCR, extract fields
7. T7 (Knowledge Base) → independently load lender data
8. T8 (Eligibility) → connect T5/T6 output + T7 rules
9. T9 (Report) → connect all above outputs
10. T10 (Copilot) → connect to T7 knowledge base
11. T11 (Frontend) → point at running backend
```

Pipeline orchestrator (to build during integration):
`backend/app/services/pipeline.py` — triggers Stage 0 → 1 → 2 → 4 → 5 sequentially per case.

---

## Quick Reference: File Locations

| Module | Service File | Endpoint File | Test File |
|--------|-------------|---------------|-----------|
| Case Entry | services/stages/stage0_case_entry.py | api/v1/endpoints/cases.py | tests/test_stage0.py |
| OCR | services/stages/stage1_ocr.py | api/v1/endpoints/documents.py | tests/test_ocr.py |
| Classifier | services/stages/stage1_classifier.py | api/v1/endpoints/documents.py | tests/test_classifier.py |
| Checklist | services/stages/stage1_checklist.py | api/v1/endpoints/cases.py | tests/test_checklist.py |
| Extraction | services/stages/stage2_extraction.py | api/v1/endpoints/extraction.py | tests/test_extraction.py |
| Bank Analyzer | services/stages/stage2_bank_analyzer.py | api/v1/endpoints/extraction.py | tests/test_bank_analyzer.py |
| Features | services/stages/stage2_features.py | api/v1/endpoints/extraction.py | tests/test_features.py |
| Knowledge Base | services/lender_service.py | api/v1/endpoints/lenders.py | tests/test_knowledge_base.py |
| Ingestion | services/stages/stage3_ingestion.py | api/v1/endpoints/lenders.py | tests/test_ingestion.py |
| Eligibility | services/stages/stage4_eligibility.py | api/v1/endpoints/eligibility.py | tests/test_eligibility.py |
| Report | services/stages/stage5_report.py | api/v1/endpoints/reports.py | tests/test_report.py |
| PDF Gen | services/stages/stage5_pdf_generator.py | api/v1/endpoints/reports.py | tests/test_pdf.py |
| Copilot | services/stages/stage7_copilot.py | api/v1/endpoints/copilot.py | tests/test_copilot.py |
| Auth | core/security.py + core/deps.py | api/v1/endpoints/auth.py | tests/test_auth.py |
