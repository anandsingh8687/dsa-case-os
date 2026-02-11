# DSA Case OS — UPDATED Task Prompts (T6 to T12)

## Status of Completed Tasks

| Task | Status | Notes |
|------|--------|-------|
| T1: File Upload + Case Creation | ✅ DONE | stage0_case_entry.py fully implemented |
| T2: OCR Pipeline | ✅ DONE | stage1_ocr.py — PyMuPDF + Tesseract |
| T3: Document Classifier | ✅ DONE | stage1_classifier.py — ML + keyword fallback |
| T4: Checklist Engine | ✅ DONE | stage1_checklist.py — 3 program types |
| T5: Regex Field Extraction | ✅ DONE | stage2_extraction.py + stage2_features.py |
| T6: Bank Statement Analyzer | 🔄 NEEDS UPDATE | Credilo parser exists, needs metrics layer |
| T7: Knowledge Base + Lender Ingestion | 🔄 NEEDS UPDATE | Real CSV data available |
| T8: Eligibility Engine | ⬜ NOT STARTED | Stub only |
| T9: Case Report Generator | ⬜ NOT STARTED | Stub only |
| T10: DSA Copilot Chatbot | ⬜ NOT STARTED | Stub only |
| T11: React Frontend | ⬜ NOT STARTED | Empty directory |
| T12: JWT Auth | ⬜ NOT STARTED | Stub only |

---

## TASK 6 (UPDATED): Bank Statement Metrics Layer on Credilo Parser

**What changed:** We already have a production-grade bank statement parser called
"Credilo" that extracts transactions from PDFs into structured data. We do NOT need
to build a parser from scratch. Instead, we need to build a METRICS COMPUTATION LAYER
that takes Credilo's transaction output and computes the financial metrics needed
for the Borrower Feature Vector.

### Prompt for Cowork

```
You are building a BANK STATEMENT METRICS COMPUTATION layer for the DSA Case OS
— a credit intelligence platform for business loan DSAs in India.

## CRITICAL CONTEXT: EXISTING PARSER
We already have a production bank statement parser called "Credilo" located at:
  /path/to/credilo/app/parser_engine.py

The Credilo parser:
- Takes bank statement PDFs as input
- Detects the bank (14+ Indian banks: HDFC, SBI, ICICI, Axis, Kotak, BOB, PNB, etc.)
- Extracts transactions with fields: transactionDate, valueDate, narration,
  chequeRefNo, withdrawalAmt, depositAmt, closingBalance
- Returns a list of ParsedStatement objects, each with bank name, account number,
  and a list of transaction dicts
- Has ~80% F1 accuracy on transaction extraction

YOU DO NOT NEED TO BUILD A PARSER. The parser is already built and working.

## YOUR TASK
Build a metrics computation service that:
1. Calls the Credilo parser to get raw transactions
2. Computes financial metrics from those transactions
3. Saves results into the DSA Case OS database

## PROJECT CONTEXT
- Backend: Python FastAPI (project is in the workspace folder dsa-case-os/)
- Credilo source: credilo/ folder in the workspace (copy parser_engine.py to use it)
- Schemas: backend/app/schemas/shared.py (see BankAnalysisResult model)
- Database: borrower_features table, extracted_fields table
- Existing extraction: backend/app/services/stages/stage2_extraction.py (already handles
  other document types — your bank analysis results feed into the same feature vector)

## WHAT TO BUILD

### 1. Copy & Integrate Credilo Parser
- Copy credilo/app/parser_engine.py into backend/app/services/credilo_parser.py
- It uses pdfplumber (already in requirements.txt)
- The key class is StatementParser with method:
  parse_statement(pdf_path: str) -> ParsedStatement
  parse_statements(pdf_paths: List[str]) -> List[ParsedStatement]

### 2. Metrics Computation Service (backend/app/services/stages/stage2_bank_analyzer.py)

Take the raw transactions from Credilo and compute these metrics:

**avg_monthly_balance:**
- Group transactions by month (using transactionDate)
- For each month, take the last closingBalance as month-end balance
- Average all month-end balances

**monthly_credit_avg:**
- Sum all depositAmt per month
- Average across all months

**monthly_debit_avg:**
- Sum all withdrawalAmt per month
- Average across all months

**emi_outflow_monthly:**
- Detect EMI patterns: look for recurring debits with similar amounts (±5% tolerance)
  appearing monthly with keywords: EMI, LOAN, NACH, ECS, SI-, MANDATE, BAJAJ, HDFC LOAN,
  TATA CAPITAL, ICICI LOAN
- Sum all detected monthly EMI debits

**bounce_count_12m:**
- Count transactions with narration containing: BOUNCE, RETURN, DISHON, INSUFFICIENT,
  UNPAID, REJECT, INWARD RETURN, CHQ RETURN, ECS RETURN, NACH RETURN
- Only count debits that were returned (not regular debits)

**cash_deposit_ratio:**
- Identify cash deposits: narration contains CASH DEP, BY CASH, CASH DEPOSIT,
  CASH CR, CASH CREDIT (but NOT "CASH CREDIT A/C" which is an account type)
- Ratio = total cash deposits / total credits

**peak_balance:** Maximum closingBalance in the period
**min_balance:** Minimum closingBalance in the period

**monthly_summary:** Per-month breakdown:
  [{month: "2024-01", credits: X, debits: Y, closing_balance: Z, bounce_count: N}]

### 3. Service Interface
```python
class BankStatementAnalyzer:
    def __init__(self):
        self.parser = StatementParser()  # from credilo

    async def analyze(self, pdf_paths: List[str]) -> BankAnalysisResult:
        """Parse PDFs with Credilo, then compute metrics."""
        # Step 1: Parse with Credilo
        statements = self.parser.parse_statements(pdf_paths)
        # Step 2: Aggregate all transactions
        # Step 3: Compute metrics
        # Step 4: Return BankAnalysisResult

    async def analyze_from_transactions(self, transactions: List[Dict]) -> BankAnalysisResult:
        """Compute metrics from pre-parsed transactions (for testing)."""
```

### 4. Integration with Existing Pipeline
The existing extraction.py endpoint POST /extraction/case/{case_id}/extract already
triggers extraction. Your bank analyzer should:
- Be called by that endpoint when bank_statement documents exist
- Save computed metrics as extracted_fields in the DB
- Feed into the BorrowerFeatureVector via stage2_features.py

### 5. Tests (backend/tests/test_bank_analyzer.py)
- Create sample transaction data (no need for actual PDFs)
- Test each metric computation
- Test edge cases: single month, no bounces, all cash deposits
- Test EMI detection with various narration patterns

### DO NOT
- Build a PDF parser — Credilo already does this
- Modify the Credilo parser code — treat it as a black box
- Build the full feature vector assembly — stage2_features.py already does this
```

---

## TASK 7 (UPDATED): Knowledge Base from Real Lender CSV Data

**What changed:** We now have actual lender data in 3 CSV files. No need to build
an LLM-based ingestion pipeline for PDFs. Instead, build a CSV ingestion pipeline
for the real data.

### Prompt for Cowork

```
You are building the KNOWLEDGE BASE AND LENDER DATA INGESTION system for DSA Case OS
— a credit intelligence platform for business loan DSAs in India.

## CRITICAL CONTEXT: REAL DATA AVAILABLE
We have 3 CSV files with actual lender data:

### File 1: Lender Policy CSV
Path: "Lender policy/Lender Policy.xlsx - BL Lender Policy.csv"
Format: 29 columns, 87 rows (some lenders have multiple products)
Columns: Sr No, Lender, Product Program, Min. Vintage, Min. Score, Min. Turnover,
Max Ticket size, Disb Till date, ABB, Entity, Age, Minimum Turnover, No 30+, 60+,
90+, Enquiries, No Overdues, EMI bounce, Bureau Check, Banking Statement, Bank Source,
Ownership Proof, GST, Tele PD, Video KYC, FI, KYC Doc, Tenor Min, Tenor Max

Key lenders: Indifi, Credit Saison, Protium, Bajaj (STBL/HTBL), Arthmate,
Tata Capital (Digital/Direct), Ambit, Flexiloans, Lendingkart, NeoGrowth (Insta/Express/Retails),
IIFL (Digital/HTBL), ABFL (Udyog+/LAP), Clix Capital (STBL/HTBL/MTBL), UGro, Godrej

Some lenders marked "Policy not available": FT Cash, ICICI, Cholamandalam

### File 2: Pincode Serviceability CSV
Path: "Lender policy/Pincode list Lender Wise.csv"
Format: 28 lender columns, 21,098 pincode rows
Structure: Each column = a lender name (GODREJ, LENDINGKART, FLEXILOANS, INDIFI, PROTIUM,
BAJAJ, ARTHMATE, POONAWALA, KREDIT BEE, AMBIT, TATA PL, TATA BL, INCRED, FIBE, IIFL,
CLIX CAPITAL, PAYSENSE, CREDIT SAISON, LOAN TAP, ABFL, L&T FINANCE, OLYV, USFB PL,
MAS, USFB BL, TruCap, TECHFINO, BAJAJ RURAL)
Each cell = a pincode that lender services (no header-to-pincode relationship — just
column-aligned lists of pincodes per lender)

NOTE: Lender names in this file may differ slightly from the policy file. You need
to build a name-mapping table (e.g., "TATA BL" → "Tata Capital" product "Direct",
"BAJAJ" → "Bajaj" etc.)

### File 3: Lender SPOC (IGNORE for now)
The user said to ignore the SPOC file for now.

## PROJECT CONTEXT
- Backend: Python FastAPI (project is in the workspace folder dsa-case-os/)
- Database schema: backend/app/db/schema.sql (updated lender_products and lender_pincodes tables)
- Schemas: backend/app/schemas/shared.py (LenderProductRule model updated with all fields)
- Route stubs: backend/app/api/v1/endpoints/lenders.py

## WHAT TO BUILD

### 1. CSV Ingestion Service (backend/app/services/stages/stage3_ingestion.py)

**Lender Policy Ingestion:**
```python
async def ingest_lender_policy_csv(csv_path: str) -> int:
    """Parse the BL Lender Policy CSV and insert into DB.
    Returns number of lender-products created."""
```

Parsing rules for each column:
- "Min. Vintage": parse as float (years). Some values like "GST active - 2 years otherwise 3 years" → parse the numeric part
- "Min. Score": parse as integer (CIBIL score)
- "Min. Turnover": parse as float in Lakhs (remove "L" suffix)
- "Max Ticket size": parse as float in Lakhs (e.g., "30L" → 30, "3L" → 3)
- "ABB": parse as float (e.g., ">=25k" → 25000, "10k" → 10000, "15K" → 15000)
- "Entity": split by comma into list, normalize (e.g., "Pvt Ltd" → "pvt_ltd")
- "Age": parse range (e.g., "22-65" → age_min=22, age_max=65)
- "No 30+": parse months (e.g., "6 month" → 6, "12 months" → 12)
- "60+", "90+": same as above
- "Banking Statement": parse months (e.g., "6 months" → 6, "12 months" → 12)
- "Bank Source": keep as-is (AA, PDF, Scorme, etc.)
- "GST", "Tele PD", "Video KYC", "FI": parse as boolean (Yes/Mandatory → True, NA/No → False)
- "Bureau Check": keep full text (complex rules)
- "Tenor Min", "Tenor Max": parse as integer months
- If "Policy not available" appears anywhere → set policy_available = False

For each row:
1. Find or create the lender in `lenders` table
2. Create a `lender_products` record with all parsed fields
3. Handle duplicates gracefully (upsert by lender_name + product_name)

**Pincode Ingestion:**
```python
async def ingest_pincode_csv(csv_path: str) -> int:
    """Parse the pincode CSV and insert into lender_pincodes table.
    Returns number of pincode mappings created."""
```

The CSV structure is unusual — each column is a lender, and cells contain pincodes.
Read column by column:
1. For each column header (= lender name), read all non-empty cells
2. Each non-empty cell is a pincode that lender services
3. Map column header to lender in DB (build name mapping: "TATA BL" → Tata Capital BL, etc.)
4. Insert into lender_pincodes table
5. Some cells might contain city names instead of pincodes (e.g., "Faridabad", "Ghaziabad") — skip non-numeric values or note them separately

**Lender Name Mapping:**
Build a mapping dict to normalize names between the policy CSV and pincode CSV:
```python
LENDER_NAME_MAP = {
    "GODREJ": "Godrej",
    "LENDINGKART": "Lendingkart",
    "FLEXILOANS": "Flexiloans",
    "INDIFI": "Indifi",
    "PROTIUM": "Protium",
    "BAJAJ": "Bajaj",
    "ARTHMATE": "Arthmate",
    "POONAWALA": "Poonawalla",
    "KREDIT BEE": "KreditBee",
    "AMBIT": "Ambit",
    "TATA PL": "Tata Capital",
    "TATA BL": "Tata Capital",
    "INCRED": "InCred",
    "FIBE": "Fibe",
    "IIFL": "IIFL",
    "CLIX CAPITAL": "Clix Capital",
    "PAYSENSE": "PaySense",
    "CREDIT SAISON": "Credit Saison",
    "LOAN TAP": "LoanTap",
    "ABFL": "ABFL",
    "L&T FINANCE": "L&T Finance",
    "OLYV": "Olyv",
    "USFB PL": "Unity Small Finance Bank",
    "MAS": "MAS Financial",
    "USFB BL": "Unity Small Finance Bank",
    "TruCap": "TruCap",
    "TECHFINO": "Techfino",
    "BAJAJ RURAL": "Bajaj",
}
```

### 2. Lender CRUD Service (backend/app/services/lender_service.py)
- list_lenders() → all lenders with product count
- get_lender(lender_id) → lender with all products
- get_lender_products(lender_id) → product rules for a lender
- find_lenders_by_pincode(pincode) → all lenders servicing this pincode
- get_all_products_for_scoring() → all active products (used by eligibility engine)

### 3. Wire Up Endpoints (update lenders.py)
- GET /lenders/ → list all lenders with product counts
- GET /lenders/{lender_id}/products → list products with rules
- GET /lenders/by-pincode/{pincode} → lenders active in that pincode
- POST /lenders/ingest-policy → upload lender policy CSV, ingest
- POST /lenders/ingest-pincodes → upload pincode CSV, ingest
- GET /lenders/stats → total lenders, products, pincodes coverage

### 4. Management Command
Create a script: backend/scripts/ingest_lender_data.py
- Accepts paths to the two CSV files
- Calls the ingestion functions
- Prints summary: X lenders created, Y products, Z pincodes

### TESTS
- backend/tests/test_knowledge_base.py
- Test CSV parsing with sample data
- Test name normalization
- Test pincode querying
- Test edge cases: "Policy not available", missing values

### DO NOT
- Build an LLM-based PDF ingestion — we have structured CSV data
- Ingest the SPOC file — user said to ignore it for now
- Build the eligibility engine — that's T8
- Build the chatbot — that's T10
```

---

## TASK 8 (UPDATED): Eligibility Engine with Real Lender Rules

**What changed:** The eligibility rules now match the actual lender policy CSV columns
with DPD rules, ABB requirements, bureau check criteria, etc.

### Prompt for Cowork

```
You are building the ELIGIBILITY ENGINE for the DSA Case OS
— a credit intelligence platform for business loan DSAs in India.

## YOUR TASK
Match the Borrower Feature Vector against real Lender Product Rules to produce a
ranked list of eligible lenders with probability scores.

## PROJECT CONTEXT
- Backend: Python FastAPI (project is in the workspace folder dsa-case-os/)
- Input: BorrowerFeatureVector (schema in backend/app/schemas/shared.py)
- Input: LenderProductRule (schema in backend/app/schemas/shared.py — UPDATED with real fields)
- Output: EligibilityResponse with ranked results
- Database: eligibility_results table, lender_products table, lender_pincodes table
- Route stubs: backend/app/api/v1/endpoints/eligibility.py

## REAL LENDER RULES CONTEXT
We have 25+ real lenders with these fields (from actual CSV data):
- min_cibil_score (650-730 range typically)
- min_vintage_years (1-3 years)
- min_turnover_annual (in Lakhs, 10-100 range)
- max_ticket_size (3L to 90L)
- min_abb (8k to 25k average bank balance)
- eligible_entity_types (Proprietorship, Partnership, LLP, Pvt Ltd etc.)
- age_min / age_max (21-75 range)
- no_30plus_dpd_months, no_60plus_dpd_months, no_90plus_dpd_months (DPD lookback)
- max_enquiries_rule (bureau enquiry limits)
- max_overdue_amount (overdue threshold)
- emi_bounce_rule (bounce limits)
- banking_months_required (6 or 12 months statements needed)
- gst_required, ownership_proof_required
- tele_pd_required, video_kyc_required, fi_required
- tenor_min_months, tenor_max_months
- policy_available (some lenders have no policy data)
- Pincode serviceability from lender_pincodes table

## WHAT TO BUILD

### 1. Eligibility Service (backend/app/services/stages/stage4_eligibility.py)

#### Layer 1: Hard Filters (Pass/Fail)
If ANY hard filter fails, the lender is eliminated:

1. **policy_available = False** → SKIP (don't evaluate)
2. **Pincode serviceability** → Query lender_pincodes table. If borrower's pincode
   not in lender's list → FAIL "Pincode not serviceable"
3. **CIBIL score** → If borrower cibil_score < lender min_cibil_score → FAIL
4. **Entity type** → If borrower entity_type not in eligible_entity_types → FAIL
5. **Business vintage** → If borrower vintage < min_vintage_years → FAIL
6. **Turnover** → If borrower annual_turnover < min_turnover_annual → FAIL
7. **Age** → If borrower age outside age_min-age_max range → FAIL
   (Calculate age from DOB if available)
8. **ABB** → If borrower avg_monthly_balance < min_abb → FAIL

Record WHICH filter(s) failed in hard_filter_details dict.

#### Layer 2: Weighted Scoring (for lenders that pass hard filters)

Calculate composite eligibility_score (0-100):

| Component        | Weight | Scoring Logic                                              |
|-----------------|--------|-----------------------------------------------------------|
| CIBIL Band      | 25%    | 750+ = 100, 725-749 = 90, 700-724 = 75, 675-699 = 60, 650-674 = 40, <650 = 20 |
| Turnover Band   | 20%    | turnover / min_turnover ratio. >3x = 100, 2-3x = 80, 1.5-2x = 60, 1-1.5x = 40 |
| Business Vintage| 15%    | 5+ yrs = 100, 3-5 = 80, 2-3 = 60, 1-2 = 40              |
| Banking Strength| 20%    | composite of: avg_balance vs ABB requirement, bounce_count (0=100, 1-2=70, 3+=30), cash_deposit_ratio (<20%=100, 20-40%=60, >40%=30) |
| FOIR            | 10%    | emi_outflow / monthly_credit. <30% = 100, 30-45% = 75, 45-55% = 50, 55-65% = 30, >65% = 0 |
| Documentation   | 10%    | % of lender's required docs available in case (gst_required met? ownership? kyc?) |

#### Layer 3: Ranking
- Sort by eligibility_score descending
- approval_probability: score >= 75 = HIGH, 50-74 = MEDIUM, <50 = LOW
- expected_ticket_range: min(max_ticket_size, turnover * factor) based on score band
- Assign rank 1, 2, 3...
- missing_for_improvement: list what would improve the score

### 2. Wire Up Endpoints (update eligibility.py)
- POST /eligibility/case/{case_id}/score → run scoring against ALL active lenders
- GET /eligibility/case/{case_id}/results → get saved results

### 3. Save Results
- Store per-lender results in eligibility_results table
- Update case status to "eligibility_scored"

### TESTS
- backend/tests/test_eligibility.py
- Use real lender rules: e.g., Bajaj STBL (CIBIL 685, vintage 1yr, max 3L)
- Test strong borrower: CIBIL 750, turnover 50L, vintage 5yrs → should match many
- Test weak borrower: CIBIL 620, turnover 5L, vintage 6 months → should match few
- Test pincode filter

### DO NOT
- Build the feature vector — it's done (T5)
- Build the knowledge base — it's done (T7)
- Build the report — that's T9
```

---

## TASK 9 (UPDATED): Case Intelligence Report Generator

### Prompt for Cowork

```
You are building the CASE INTELLIGENCE REPORT GENERATOR for DSA Case OS
— a credit intelligence platform for business loan DSAs in India.

## YOUR TASK
Generate a professional PDF case report showing borrower profile, matched lenders,
strengths, risks, and submission strategy. This is the PRIMARY PAID DELIVERABLE.

## PROJECT CONTEXT
- Backend: Python FastAPI (project is in the workspace folder dsa-case-os/)
- Input: CaseReportData (schema in backend/app/schemas/shared.py)
- Database: case_reports table
- All upstream data is already available:
  - BorrowerFeatureVector from borrower_features table
  - DocumentChecklist from stage1_checklist.py
  - EligibilityResults from eligibility_results table
- Route stubs: backend/app/api/v1/endpoints/reports.py

## WHAT TO BUILD

### 1. Report Data Assembly (backend/app/services/stages/stage5_report.py)

Gather all data:
- Fetch BorrowerFeatureVector for the case
- Fetch DocumentChecklist
- Fetch EligibilityResults (sorted by rank)
- Compute strengths and risk flags:

**Strengths detection:**
- CIBIL >= 750 → "Excellent credit score ({score})"
- CIBIL 700-749 → "Good credit score ({score})"
- Turnover > 50L → "Strong annual turnover (₹{amount}L)"
- Vintage > 5 years → "Well-established business ({years} years)"
- Bounce count = 0 → "Clean banking — zero bounces in 12 months"
- Cash deposit ratio < 20% → "Healthy banking — low cash deposit ratio"
- FOIR < 40% → "Low existing obligations"
- Multiple lenders matched HIGH → "Strong profile — {count} lenders matched with high probability"

**Risk flags detection:**
- CIBIL < 650 → "Low credit score ({score}) — limits lender options"
- Vintage < 2 years → "Low business vintage ({years} years)"
- Bounces > 3 → "Banking concern — {count} bounced cheques in 12 months"
- Cash deposit ratio > 40% → "High cash deposit ratio ({pct}%) — some lenders may flag this"
- FOIR > 55% → "High existing debt obligations (FOIR: {pct}%)"
- Missing critical documents → "Incomplete documentation — {count} required docs missing"
- No lenders matched → "No eligible lenders found — consider improving {suggestions}"

**Submission strategy:**
- Top lender recommendation with reasoning
- Suggested order of approach (top 3-5 lenders)
- Special notes per lender (e.g., "requires Video KYC", "needs ownership proof")

### 2. PDF Generation (backend/app/services/stages/stage5_pdf_generator.py)

Use ReportLab to generate a professional PDF:

**Page 1: Cover**
- Title: "Case Intelligence Report"
- Case ID, Date Generated
- Borrower Name, Entity Type
- "Prepared by DSA Case OS"

**Page 2: Borrower Profile**
- Clean table: Name, Entity Type, Vintage, Industry, Pincode
- Financial snapshot: Turnover, CIBIL Score, Avg Bank Balance, Monthly Credits

**Page 3: Document Status**
- Checklist with green checkmarks and red X marks
- Completeness bar (e.g., "78% complete")
- Missing items listed

**Page 4: Strengths & Risks**
- Green section: strengths bullet points
- Red section: risk flags
- Yellow section: advisory notes

**Page 5-6: Lender Match Table**
- Table: Rank | Lender | Product | Score | Probability | Max Ticket | Notes
- Color-coded: GREEN rows (HIGH), YELLOW (MEDIUM), RED (LOW / FAIL)
- Show top 15 lenders (or all that passed)

**Page 7: Recommendations**
- Submission strategy text
- Missing data advisory
- Expected loan range

### 3. WhatsApp Summary Generator
Short text for copy-paste sharing:
```
📋 Case: CASE-20250210-0001
👤 Borrower: [Name] | [Entity] | [Vintage]yr
📊 CIBIL: [score] | Turnover: ₹[X]L | ABB: ₹[Y]
✅ Top Match: [Lender] - [Product] ([probability])
📈 [N] lenders matched | Best score: [X]/100
⚠️ Missing: [list of missing docs]
```

### 4. Wire Up Endpoints (update reports.py)
- POST /reports/case/{case_id}/generate → generate report, save PDF
- GET /reports/case/{case_id}/report → get report data as JSON
- GET /reports/case/{case_id}/report/pdf → download PDF file
- GET /reports/case/{case_id}/report/whatsapp → get WhatsApp summary text

### TESTS
- backend/tests/test_report.py
- Test data assembly with mock data
- Test PDF generation produces valid file
- Test with partial data (missing eligibility, missing features)

### DO NOT
- Build eligibility scoring — that's T8
- Build the frontend — that's T11
```

---

## TASK 10 (UPDATED): DSA Copilot Chatbot

### Prompt for Cowork

```
You are building the DSA COPILOT CHATBOT for the DSA Case OS
— a credit intelligence platform for business loan DSAs in India.

## YOUR TASK
Build a natural language chatbot that queries the REAL lender knowledge base.
DSAs use this daily for quick lender queries.

## PROJECT CONTEXT
- Backend: Python FastAPI (project is in the workspace folder dsa-case-os/)
- Knowledge base: lenders, lender_products, lender_pincodes tables (POPULATED with real data)
- 25+ real lenders with actual policy rules
- 21,000+ pincode mappings for 28 lenders
- Config: ANTHROPIC_API_KEY, CLAUDE_MODEL in backend/app/core/config.py
- Schemas: CopilotQuery, CopilotResponse in backend/app/schemas/shared.py
- Route stubs: backend/app/api/v1/endpoints/copilot.py

## REAL LENDER DATA AVAILABLE
The DB contains real policies for lenders like Bajaj, Tata Capital, IIFL, Indifi,
Protium, Lendingkart, Flexiloans, ABFL, Clix Capital, NeoGrowth, UGro, Godrej, etc.

Each lender has: min_cibil, min_vintage, min_turnover, max_ticket, entity types,
DPD rules, ABB requirements, document requirements, verification requirements.

## WHAT TO BUILD

### 1. Knowledge Retriever (backend/app/services/stages/stage7_retriever.py)

Query classification + smart DB retrieval:

**Query types to support:**
| Query Pattern | DB Query |
|--------------|----------|
| "below 650 CIBIL" | WHERE min_cibil_score <= 650 |
| "pincode 400001" | JOIN lender_pincodes WHERE pincode = '400001' |
| "max ticket 50 lakh" | WHERE max_ticket_size >= 50 |
| "proprietorship only" | WHERE eligible_entity_types @> '["proprietorship"]' |
| "1 year vintage" | WHERE min_vintage_years <= 1 |
| "compare Bajaj and IIFL" | Fetch both, return side-by-side |
| "Tata Capital policy" | Fetch all products for Tata Capital |
| "no video KYC" | WHERE video_kyc_required = FALSE |

### 2. Copilot Service (backend/app/services/stages/stage7_copilot.py)

Flow:
1. Receive natural language query
2. Classify query type (CIBIL, pincode, lender-specific, comparison, etc.)
3. Retrieve relevant lender data from DB
4. Build Claude API prompt with retrieved data as context
5. Call Claude API (anthropic Python SDK)
6. Return answer with sources

Claude prompt template:
```
You are a helpful assistant for Business Loan DSAs in India.
Answer the DSA's question using ONLY the lender data provided below.
Be specific: name lenders, quote exact numbers.
Format as a clear, actionable answer.

LENDER DATA:
{retrieved_data_json}

QUESTION: {user_query}
```

### 3. Wire Up Endpoint
- POST /copilot/query → CopilotResponse

### 4. Logging
- Log queries and responses in copilot_queries table
- Track response time

### TESTS
- backend/tests/test_copilot.py
- Mock Claude API
- Test query classification
- Test retriever with real lender rules

### DO NOT
- Build the knowledge base — it's done (T7)
```

---

## TASK 11 (UPDATED): React Frontend

### Prompt for Cowork

```
You are building the REACT FRONTEND for the DSA Case OS
— a credit intelligence platform for business loan DSAs in India.

## YOUR TASK
Build a complete React web application. The backend API is fully built with
these WORKING endpoints:

### WORKING ENDPOINTS (implemented):
- POST /api/v1/cases/ → create case
- GET /api/v1/cases/ → list cases
- GET /api/v1/cases/{case_id} → get case
- PATCH /api/v1/cases/{case_id} → update case
- POST /api/v1/cases/{case_id}/upload → upload documents
- GET /api/v1/cases/{case_id}/checklist → document checklist
- GET /api/v1/cases/{case_id}/manual-prompts → progressive data capture
- GET /api/v1/documents/{doc_id}/ocr-text → OCR text
- POST /api/v1/documents/{doc_id}/reclassify → reclassify document
- POST /api/v1/extraction/case/{case_id}/extract → run extraction
- GET /api/v1/extraction/case/{case_id}/fields → extracted fields
- GET /api/v1/extraction/case/{case_id}/features → feature vector
- POST /api/v1/eligibility/case/{case_id}/score → run scoring
- GET /api/v1/eligibility/case/{case_id}/results → get results
- POST /api/v1/reports/case/{case_id}/generate → generate report
- GET /api/v1/reports/case/{case_id}/report/pdf → download PDF
- GET /api/v1/lenders/ → list lenders
- GET /api/v1/lenders/by-pincode/{pincode} → lenders by pincode
- POST /api/v1/copilot/query → chatbot query

## PROJECT CONTEXT
- Frontend lives in: dsa-case-os/frontend/
- Backend API base: http://localhost:8000/api/v1

## TECH STACK
- React 18 with Vite
- React Router v6
- Tailwind CSS
- Axios + React Query (TanStack Query)
- React Hook Form for forms
- Lucide React for icons
- React Dropzone for file uploads
- React Hot Toast for notifications

## PAGES TO BUILD

### 1. Login/Register (/login, /register)
- Simple email + password forms
- JWT token stored in localStorage
- Redirect to dashboard after login

### 2. Dashboard (/dashboard)
- Case cards: case_id, borrower_name, status badge, completeness %, date
- Status color coding: green = report_generated, blue = processing, yellow = features_extracted, red = failed
- "New Case +" button
- Search by borrower name
- Quick stats: total cases, avg completeness

### 3. New Case (/cases/new)
- Step wizard:
  1. Basic Info: borrower name, entity type dropdown (Proprietorship/Partnership/LLP/Pvt Ltd/etc.), program type (Banking/Income/Hybrid), industry, pincode
  2. Upload: drag-drop zone, multi-file + ZIP support, show upload progress
  3. Processing: show auto-classification results, allow reclassify

### 4. Case Detail (/cases/:caseId) — MAIN PAGE
Tabbed layout with 5 tabs:

**Tab: Documents**
- Table: filename, doc_type badge, confidence %, status
- "Upload More" button
- "Reclassify" dropdown per doc

**Tab: Checklist**
- Program type selector (Banking/Income/Hybrid)
- Visual checklist: ✓ green / ✗ red per document
- Completeness progress bar
- Manual entry forms for missing data (CIBIL score input, vintage input, entity type select, turnover input)

**Tab: Profile**
- BorrowerFeatureVector displayed as clean card
- Sections: Identity, Business, Financial, Credit
- Confidence indicators per field
- Edit buttons for manual override

**Tab: Eligibility**
- "Run Scoring" button
- Results table: Rank, Lender, Product, Score/100, Probability badge (HIGH/MEDIUM/LOW), Max Ticket, Notes
- Color-coded rows
- Expandable details per lender (which filters failed, what's missing)
- Summary: "X of Y lenders matched"

**Tab: Report**
- "Generate Report" button
- Report preview (key sections rendered)
- "Download PDF" button
- "Copy WhatsApp Summary" button

### 5. Copilot (/copilot)
- Chat interface with message bubbles
- Input field + send button
- Suggestion chips: "Low CIBIL lenders", "Lenders in Mumbai", "Compare Bajaj vs IIFL", "No Video KYC lenders"
- Typing indicator while waiting

### 6. Lender Directory (/lenders)
- List of all lenders with key details
- Search by name
- Filter by pincode
- Click to see full policy details

### 7. Layout
- Sidebar: Dashboard, New Case, Copilot, Lenders, Settings
- Top bar: "DSA Case OS" logo, user name, logout
- Mobile responsive

## DESIGN
- Primary: #2563EB (blue-600), Accent: #10B981 (green-500)
- Card-based layout, clean and professional
- Loading skeletons, empty states, error boundaries

## SETUP COMMANDS
```bash
npm create vite@latest . -- --template react
npm install tailwindcss @tailwindcss/vite react-router-dom axios @tanstack/react-query
npm install react-hook-form lucide-react react-dropzone react-hot-toast
```

## DO NOT
- Build any backend logic
- Implement actual auth verification — just token storage
```

---

## TASK 12 (UNCHANGED): JWT Authentication

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

### TESTS
- backend/tests/test_auth.py
- Test registration, login, protected endpoints

### DO NOT
- Build OAuth — just email+password for MVP
- Build email verification or password reset — skip for MVP
```

---

## Execution Order

**Batch 1 (start now, all parallel):**
- T6: Bank Statement Metrics (on Credilo)
- T7: Knowledge Base (CSV ingestion)
- T12: JWT Auth
- T11: React Frontend (can start immediately)

**Batch 2 (after T6 + T7 done):**
- T8: Eligibility Engine

**Batch 3 (after T8 done):**
- T9: Case Report Generator
- T10: DSA Copilot (only needs T7)

**Integration (after all done):**
- Wire up pipeline orchestrator
- Connect auth to all routes
- End-to-end testing
