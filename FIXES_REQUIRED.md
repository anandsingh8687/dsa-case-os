# Critical Fixes Required for DSA Case OS

## Issues Identified

### 1. Document Classification Not Working ❌
**Problem**: When users upload documents, the system shows incorrect document status (green checkmarks for non-uploaded files, "unknown" for uploaded PDFs)

**Root Causes**:
- Document classifier exists but is NOT being called automatically after upload
- Frontend is showing random/cached document status
- Classification endpoint exists (`POST /documents/{doc_id}/classify`) but must be called manually
- OCR extraction must complete before classification can work

### 2. Lender Copilot Returning Empty Results ❌
**Problem**: All queries return "No lenders found" even for basic questions

**Root Causes**:
1. **API Configuration Issues**:
   - `LLM_API_KEY` is not set (currently `None`)
   - Kimi 2.5 API requires proper configuration

2. **Database Query Issues**:
   - Using `db.fetch()` which is incorrect for SQLAlchemy AsyncSession
   - Should use `db.execute()` with proper SQL statements

3. **Lender Data May Not Be Loaded**:
   - Database might be empty (no lender products/pincodes loaded)
   - CSV ingestion might not have been run

---

## Fix #1: Document Classification Pipeline

### Changes Needed

#### A. Backend: Auto-trigger Classification After OCR
**File**: `backend/app/api/v1/endpoints/cases.py` (or wherever document upload happens)

**Current Flow**:
```
Upload → Save to DB → Return response
```

**Fixed Flow**:
```
Upload → Save to DB → OCR Extraction → Classification → Return response
```

**Implementation**:
```python
# After document upload and OCR extraction:
from app.services.stages.stage1_classifier import classify_document

async def upload_document(file, case_id, doc_type_hint=None):
    # 1. Save file
    document = await save_document_to_db(file, case_id)

    # 2. Extract OCR text (if PDF/image)
    if file.content_type in ['application/pdf', 'image/jpeg', 'image/png']:
        ocr_text = await extract_ocr_text(document.file_path)
        document.ocr_text = ocr_text
        document.status = "ocr_complete"
        await db.commit()

        # 3. AUTO-CLASSIFY (NEW STEP)
        if ocr_text and len(ocr_text.strip()) > 10:
            result = classify_document(ocr_text)
            document.doc_type = result.doc_type.value
            document.classification_confidence = result.confidence
            document.status = "classified"
            await db.commit()

    return document
```

#### B. Frontend: Show Correct Document Status
**File**: Frontend component showing document checklist

**Issue**: Frontend is showing hardcoded/cached document types instead of actual uploaded documents

**Fix**:
1. Fetch actual documents for the case via API: `GET /cases/{case_id}/documents`
2. Match uploaded documents against required document types
3. Show checkmark ONLY if document exists AND is classified with good confidence
4. Show "unknown" status while OCR/classification is in progress

**Example API Response Structure**:
```json
{
  "required_documents": [
    {"type": "gst_certificate", "status": "uploaded", "confidence": 0.95},
    {"type": "bank_statement", "status": "uploaded", "confidence": 0.88},
    {"type": "itr", "status": "missing", "confidence": null},
    {"type": "aadhaar", "status": "missing", "confidence": null}
  ]
}
```

#### C. Create Document Status Endpoint
**New Endpoint**: `GET /cases/{case_id}/document-checklist`

```python
@router.get("/{case_id}/document-checklist")
async def get_document_checklist(case_id: str, db: AsyncSession = Depends(get_db)):
    """Get document checklist status for a case."""

    # Define required document types
    required_types = [
        "gst_certificate", "gst_returns", "cibil_report",
        "itr", "bank_statement", "aadhaar",
        "pan_personal", "pan_business"
    ]

    # Get all uploaded documents for this case
    documents = await db.execute(
        select(Document).where(Document.case_id == case_id)
    )
    docs = documents.scalars().all()

    # Build checklist
    checklist = {}
    for doc_type in required_types:
        matching_docs = [d for d in docs if d.doc_type == doc_type]

        if matching_docs:
            best_doc = max(matching_docs, key=lambda d: d.classification_confidence or 0)
            checklist[doc_type] = {
                "status": "uploaded",
                "confidence": best_doc.classification_confidence,
                "filename": best_doc.original_filename
            }
        else:
            checklist[doc_type] = {
                "status": "missing",
                "confidence": None,
                "filename": None
            }

    return checklist
```

---

## Fix #2: Lender Copilot Database Queries

### Changes Needed

#### A. Fix Database Query Method
**File**: `backend/app/services/stages/stage7_retriever.py`

**Problem**: Using `db.fetch()` which doesn't exist on AsyncSession

**Current (WRONG)**:
```python
rows = await db.fetch(query, cibil_score)
return [dict(row) for row in rows]
```

**Fixed**:
```python
from sqlalchemy import text

result = await db.execute(text(query), {"param1": cibil_score})
rows = result.fetchall()
return [dict(row._mapping) for row in rows]
```

**Apply this fix to ALL retrieval functions**:
- `_retrieve_by_cibil()`
- `_retrieve_by_pincode()`
- `_retrieve_lender_details()`
- `_retrieve_for_comparison()`
- `_retrieve_by_vintage()`
- `_retrieve_by_turnover()`
- `_retrieve_by_entity_type()`
- `_retrieve_by_ticket_size()`
- `_retrieve_by_requirement()`
- `_retrieve_general()`

#### B. Fix Parameterized Queries
All queries currently use PostgreSQL-style parameters (`$1`, `$2`). For SQLAlchemy `text()`, use named parameters:

**Before**:
```python
query = "SELECT * FROM lenders WHERE id = $1"
rows = await db.fetch(query, lender_id)
```

**After**:
```python
query = "SELECT * FROM lenders WHERE id = :lender_id"
result = await db.execute(text(query), {"lender_id": lender_id})
rows = result.fetchall()
```

#### C. Verify Lender Data is Loaded
Run this check:

```bash
# Connect to database
psql -d dsa_case_os

# Check if lender data exists
SELECT COUNT(*) FROM lenders;
SELECT COUNT(*) FROM lender_products;
SELECT COUNT(*) FROM lender_pincodes;

# If all return 0, run the ingestion script:
cd backend
python scripts/ingest_lender_data.py \
  --policy-csv "path/to/Lender Policy.csv" \
  --pincode-csv "path/to/Pincode list.csv"
```

---

## Fix #3: Kimi 2.5 API Configuration

### A. Set Environment Variable
**File**: `.env` (create if doesn't exist)

```bash
# Kimi 2.5 API Configuration
LLM_API_KEY=your-moonshot-api-key-here
LLM_MODEL=moonshot-v1-8k
LLM_BASE_URL=https://api.moonshot.cn/v1
```

### B. Fallback to General Knowledge
The copilot already has fallback logic that works without API key:
- When `LLM_API_KEY` is not set, it uses `_generate_fallback_answer()`
- This provides template-based responses
- However, it still requires database data to be useful

### C. Alternative: Use Claude API Instead
If you have Anthropic API key, you can switch to Claude:

**File**: `backend/app/core/config.py`
```python
# Option 1: Keep Kimi 2.5
LLM_API_KEY: Optional[str] = os.getenv("MOONSHOT_API_KEY")
LLM_MODEL: str = "moonshot-v1-8k"
LLM_BASE_URL: str = "https://api.moonshot.cn/v1"

# Option 2: Switch to Claude (Anthropic)
LLM_API_KEY: Optional[str] = os.getenv("ANTHROPIC_API_KEY")
LLM_MODEL: str = "claude-sonnet-4-20250514"
LLM_BASE_URL: str = "https://api.anthropic.com/v1"  # Requires different client
```

---

## Fix #4: Hybrid Copilot (Database + General Knowledge)

### Current System
The copilot is **already designed as hybrid**! From `stage7_copilot.py`:

```python
def _get_system_prompt() -> str:
    return """You are "Lender Copilot"...

    IMPORTANT RULES:
    1. When DATABASE RESULTS are provided, prioritize them
    2. When NO database results are available, use your general knowledge
    3. Always be specific: name lenders, quote approximate numbers
    ..."""
```

### How It Works
1. **Query with DB Results**: Provides exact, up-to-date lender data from your database
2. **Query without DB Results**: Uses LLM's general knowledge of Indian lending landscape
3. **Fallback Mode**: Template-based responses when API is unavailable

### To Enable Hybrid Mode
1. Fix database queries (Fix #2)
2. Set API key (Fix #3)
3. Load lender data if missing

The system will automatically:
- Return accurate answers when DB has data
- Provide helpful general guidance when DB is empty
- Mention that answers are based on general knowledge (not specific to your data)

---

## Implementation Priority

### CRITICAL (Do First) ⚠️

1. **Fix Database Queries**
   - Change `db.fetch()` to `db.execute(text(...))` in all retriever functions
   - Update parameter binding from `$1` to `:param_name`
   - Test each query individually

2. **Verify/Load Lender Data**
   - Check if lenders table has data
   - Run CSV ingestion if empty
   - Verify data with simple query: `SELECT COUNT(*) FROM lender_products`

3. **Fix Document Classification Pipeline**
   - Add auto-classification after OCR
   - Create document checklist endpoint
   - Update frontend to fetch real document status

### IMPORTANT (Do Next) 📋

4. **Configure LLM API**
   - Get Kimi 2.5 API key OR use Claude API
   - Set environment variable
   - Test copilot with and without API key

5. **Test End-to-End**
   - Upload bank statement PDF → verify it gets classified
   - Query copilot → verify it returns lender data
   - Test all query types (CIBIL, pincode, comparison, etc.)

### NICE TO HAVE (Optional) ✨

6. **Add Better Error Messages**
   - Show specific error when OCR fails
   - Show progress indicator during classification
   - Add retry logic for failed classifications

7. **Add Analytics Dashboard**
   - Track most common copilot queries
   - Monitor classification accuracy
   - Show lender data coverage

---

## Testing Checklist

### Document Classification
- [ ] Upload bank statement PDF
- [ ] Wait for OCR to complete
- [ ] Check if doc_type is set to "bank_statement"
- [ ] Verify classification_confidence > 0.7
- [ ] Check document checklist shows correct status

### Lender Copilot
- [ ] Query: "Which lenders fund below 650 CIBIL?"
- [ ] Verify it returns lender list (not "No lenders found")
- [ ] Query: "who serves pincode 400001"
- [ ] Verify it returns lenders for that pincode
- [ ] Query: "compare Bajaj and IIFL"
- [ ] Verify it returns comparison data
- [ ] Query without DB match (e.g., "hello")
- [ ] Verify it gives helpful general response

---

## Quick Start Commands

```bash
# 1. Fix database queries (manual code changes needed)
cd backend/app/services/stages
# Edit stage7_retriever.py - replace db.fetch() with db.execute(text(...))

# 2. Check if lender data exists
psql -d dsa_case_os -c "SELECT COUNT(*) FROM lenders;"

# 3. If empty, load lender data
cd backend
python scripts/ingest_lender_data.py \
  --policy-csv "path/to/lender_policy.csv" \
  --pincode-csv "path/to/pincodes.csv"

# 4. Set API key
echo "LLM_API_KEY=your-api-key-here" >> .env

# 5. Restart backend
uvicorn app.main:app --reload

# 6. Test copilot
curl -X POST http://localhost:8000/api/v1/copilot/query \
  -H "Content-Type: application/json" \
  -d '{"query": "lenders for 650 CIBIL"}'
```

---

## Summary

### What's Broken
1. ❌ Document classification not triggered automatically
2. ❌ Database queries using wrong method (`db.fetch()` vs `db.execute()`)
3. ❌ Lender data may not be loaded
4. ❌ LLM API key not configured (optional, has fallback)

### What Needs To Be Fixed
1. ✅ Change all `db.fetch()` to `db.execute(text(query))` in retriever
2. ✅ Update parameter binding from `$1` to `:param_name`
3. ✅ Add auto-classification to document upload pipeline
4. ✅ Create document checklist endpoint
5. ✅ Update frontend to show real document status
6. ✅ Verify lender data is loaded (or run ingestion)
7. ✅ Set LLM API key (Kimi 2.5 or Claude)

### Expected Outcome
- ✅ Documents get classified automatically after upload
- ✅ Frontend shows correct document status
- ✅ Copilot returns accurate lender recommendations
- ✅ Hybrid mode works (DB data + general knowledge)
- ✅ System is production-ready

---

**Need help with specific implementation? Let me know which fix to tackle first!**
