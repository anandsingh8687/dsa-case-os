# Step-by-Step Implementation Guide

## Overview
This guide provides the exact code changes needed to fix the two main issues:
1. Document classification not working
2. Lender copilot returning empty results

---

## PART 1: Fix Lender Copilot Database Queries

### Step 1.1: Fix stage7_retriever.py

The main issue is that the code uses `db.fetch()` which doesn't exist on AsyncSession. We need to use SQLAlchemy's `text()` and proper execution.

**Create**: `backend/app/services/stages/stage7_retriever_FIXED.py`

Key changes needed:
1. Import `text` from sqlalchemy
2. Replace all `await db.fetch(query, params)` with `await db.execute(text(query), params_dict)`
3. Convert positional parameters (`$1`, `$2`) to named parameters (`:param_name`)
4. Use `result.fetchall()` and `row._mapping` to convert to dicts

**Example of one fixed function**:

```python
from sqlalchemy import text

async def _retrieve_by_cibil(db, params: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Retrieve lenders by CIBIL score requirement."""
    cibil_score = params.get('cibil_score')
    operator = params.get('operator', '<=')

    # Build query based on operator
    if operator == '<=':
        condition = "lp.min_cibil_score <= :cibil_score"
        order = "lp.min_cibil_score ASC"
    else:
        condition = "lp.min_cibil_score > :cibil_score"
        order = "lp.min_cibil_score ASC"

    query = f"""
        SELECT
            l.lender_name,
            lp.product_name,
            lp.min_cibil_score,
            lp.min_vintage_years,
            lp.min_turnover_annual,
            lp.max_ticket_size,
            lp.eligible_entity_types,
            lp.video_kyc_required,
            lp.fi_required,
            lp.gst_required,
            COUNT(DISTINCT lpc.pincode) as pincode_coverage
        FROM lender_products lp
        INNER JOIN lenders l ON lp.lender_id = l.id
        LEFT JOIN lender_pincodes lpc ON l.id = lpc.lender_id
        WHERE lp.is_active = TRUE
          AND l.is_active = TRUE
          AND {condition}
        GROUP BY l.lender_name, lp.id, lp.product_name, lp.min_cibil_score,
                 lp.min_vintage_years, lp.min_turnover_annual, lp.max_ticket_size,
                 lp.eligible_entity_types, lp.video_kyc_required, lp.fi_required, lp.gst_required
        ORDER BY {order}
        LIMIT 20
    """

    # FIXED: Use text() and named parameters
    result = await db.execute(text(query), {"cibil_score": cibil_score})
    rows = result.fetchall()
    return [dict(row._mapping) for row in rows]
```

### Step 1.2: Apply Same Fix to All Retrieval Functions

You need to update these functions in the same file:
- ✅ `_retrieve_by_pincode()` - Change `$1` to `:pincode`
- ✅ `_retrieve_lender_details()` - Change `$1` to `:lender_pattern`
- ✅ `_retrieve_for_comparison()` - More complex, uses dynamic params
- ✅ `_retrieve_by_vintage()` - Change `$1` to `:vintage_years`
- ✅ `_retrieve_by_turnover()` - Change `$1` to `:turnover`
- ✅ `_retrieve_by_entity_type()` - Change `$1` to `:entity_types`
- ✅ `_retrieve_by_ticket_size()` - Change `$1` to `:ticket_size`
- ✅ `_retrieve_by_requirement()` - Change `$1` to `:value`
- ✅ `_retrieve_general()` - No params, should work as-is

### Step 1.3: Fix the Comparison Query (Most Complex)

The comparison query is tricky because it uses dynamic parameters:

```python
async def _retrieve_for_comparison(db, params: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Retrieve products from multiple lenders for comparison."""
    lenders = params.get('lenders', [])

    if not lenders:
        return []

    # Build LIKE conditions with named parameters
    like_conditions = []
    query_params = {}

    for i, lender in enumerate(lenders):
        param_name = f"lender_{i}"
        like_conditions.append(f"LOWER(l.lender_name) LIKE LOWER(CONCAT('%', :{param_name}, '%'))")
        query_params[param_name] = lender

    query = f"""
        SELECT
            l.lender_name,
            lp.product_name,
            lp.min_cibil_score,
            lp.min_vintage_years,
            lp.min_turnover_annual,
            lp.max_ticket_size,
            lp.min_abb,
            lp.eligible_entity_types,
            lp.video_kyc_required,
            lp.fi_required,
            lp.tele_pd_required,
            lp.tenor_min_months,
            lp.tenor_max_months,
            COUNT(DISTINCT lpc.pincode) as pincode_coverage
        FROM lender_products lp
        INNER JOIN lenders l ON lp.lender_id = l.id
        LEFT JOIN lender_pincodes lpc ON l.id = lpc.lender_id
        WHERE lp.is_active = TRUE
          AND l.is_active = TRUE
          AND ({' OR '.join(like_conditions)})
        GROUP BY l.lender_name, lp.id, lp.product_name, lp.min_cibil_score,
                 lp.min_vintage_years, lp.min_turnover_annual, lp.max_ticket_size,
                 lp.min_abb, lp.eligible_entity_types, lp.video_kyc_required,
                 lp.fi_required, lp.tele_pd_required, lp.tenor_min_months, lp.tenor_max_months
        ORDER BY l.lender_name, lp.product_name
    """

    result = await db.execute(text(query), query_params)
    rows = result.fetchall()
    return [dict(row._mapping) for row in rows]
```

---

## PART 2: Verify and Load Lender Data

### Step 2.1: Check if Data Exists

```bash
# Connect to your PostgreSQL database
psql -d dsa_case_os

# Run these queries:
SELECT COUNT(*) FROM lenders;           -- Should return 25+
SELECT COUNT(*) FROM lender_products;   -- Should return 87+
SELECT COUNT(*) FROM lender_pincodes;   -- Should return 21,000+

# If any return 0, you need to load the data
```

### Step 2.2: Load Lender Data (If Missing)

```bash
cd backend

# Option 1: If you have the CSV files
python scripts/ingest_lender_data.py \
  --policy-csv "path/to/Lender Policy.csv" \
  --pincode-csv "path/to/Pincode list.csv"

# Option 2: Use sample data for testing
python scripts/ingest_lender_data.py \
  --policy-csv "test_data/sample_lender_policy.csv" \
  --pincode-csv "test_data/sample_pincode_serviceability.csv"
```

---

## PART 3: Configure LLM API

### Step 3.1: Create/Update .env File

**File**: `backend/.env`

```bash
# Database
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/dsa_case_os

# LLM Configuration (Choose ONE)

# Option A: Kimi 2.5 (Moonshot AI)
LLM_API_KEY=your-moonshot-api-key-here
LLM_MODEL=moonshot-v1-8k
LLM_BASE_URL=https://api.moonshot.cn/v1

# Option B: Claude (Anthropic) - Requires modifying copilot.py
# LLM_API_KEY=your-anthropic-api-key-here
# LLM_MODEL=claude-sonnet-4-20250514
# LLM_BASE_URL=https://api.anthropic.com/v1

# Option C: No API Key (uses fallback mode with general knowledge)
# Leave LLM_API_KEY empty or unset
```

### Step 3.2: Get API Key

**For Kimi 2.5 (Moonshot AI)**:
1. Visit: https://platform.moonshot.cn/
2. Sign up and get API key
3. Copy key to .env file

**For Claude (Alternative)**:
1. Visit: https://console.anthropic.com/
2. Get API key
3. **Note**: Requires code changes to use Anthropic SDK instead of OpenAI-compatible API

---

## PART 4: Fix Document Classification

### Step 4.1: Update Document Upload to Auto-Classify

**File**: `backend/app/api/v1/endpoints/cases.py`

Find the document upload function and add classification:

```python
from app.services.stages.stage1_classifier import classify_document

@router.post("/{case_id}/documents")
async def upload_document(
    case_id: str,
    file: UploadFile,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Upload a document to a case."""

    # ... existing upload logic ...

    # Save document to database
    document = Document(
        case_id=case_id,
        original_filename=file.filename,
        file_path=saved_path,
        status="uploaded"
    )
    db.add(document)
    await db.commit()
    await db.refresh(document)

    # NEW: Auto-extract OCR and classify
    if file.filename.lower().endswith('.pdf'):
        try:
            # Extract OCR text
            from app.services.document_processor import extract_text_from_pdf
            ocr_text = await extract_text_from_pdf(saved_path)

            # Update OCR fields
            document.ocr_text = ocr_text
            document.status = "ocr_complete"
            await db.commit()

            # Classify if we have good OCR text
            if ocr_text and len(ocr_text.strip()) > 10:
                result = classify_document(ocr_text)
                document.doc_type = result.doc_type.value
                document.classification_confidence = result.confidence
                document.status = "classified"
                await db.commit()
                await db.refresh(document)

        except Exception as e:
            logger.error(f"Error in OCR/classification: {e}")
            document.status = "failed"
            await db.commit()

    return {
        "id": str(document.id),
        "filename": document.original_filename,
        "doc_type": document.doc_type,
        "confidence": document.classification_confidence,
        "status": document.status
    }
```

### Step 4.2: Create Document Checklist Endpoint

**File**: `backend/app/api/v1/endpoints/cases.py`

Add this new endpoint:

```python
@router.get("/{case_id}/document-checklist")
async def get_document_checklist(
    case_id: str,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Get document checklist status for a case."""

    # Define required document types
    REQUIRED_DOCS = [
        "gst_certificate",
        "gst_returns",
        "cibil_report",
        "itr",
        "bank_statement",
        "aadhaar",
        "pan_personal",
        "pan_business"
    ]

    # Get all documents for this case
    stmt = select(Document).where(Document.case_id == UUID(case_id))
    result = await db.execute(stmt)
    documents = result.scalars().all()

    # Build checklist
    checklist = {}

    for doc_type in REQUIRED_DOCS:
        # Find documents of this type
        matching = [d for d in documents if d.doc_type == doc_type]

        if matching:
            # Pick the one with highest confidence
            best = max(matching, key=lambda d: d.classification_confidence or 0)
            checklist[doc_type] = {
                "status": "available",
                "confidence": best.classification_confidence,
                "filename": best.original_filename,
                "classified_as": best.doc_type
            }
        else:
            checklist[doc_type] = {
                "status": "missing",
                "confidence": None,
                "filename": None,
                "classified_as": None
            }

    return {
        "case_id": case_id,
        "checklist": checklist,
        "completeness": len([c for c in checklist.values() if c["status"] == "available"]) / len(REQUIRED_DOCS)
    }
```

### Step 4.3: Update Frontend to Use New Endpoint

**Frontend Component** (pseudo-code):

```typescript
// Fetch document checklist
const response = await fetch(`/api/v1/cases/${caseId}/document-checklist`);
const data = await response.json();

// Render checklist
data.checklist.forEach((docType, info) => {
    if (info.status === "available") {
        // Show green checkmark
        renderCheckmark(docType, info.confidence);
    } else {
        // Show red X or "missing" label
        renderMissing(docType);
    }
});

// Show completeness percentage
renderCompleteness(data.completeness * 100);
```

---

## PART 5: Testing

### Test 1: Verify Database Queries Work

```bash
# Start Python shell
cd backend
python

# Test a simple query
from app.db.database import get_db_session
from app.services.stages.stage7_retriever import classify_query, retrieve_lender_data
import asyncio

async def test():
    query_type, params = classify_query("lenders for 650 CIBIL")
    print(f"Query Type: {query_type}")
    print(f"Params: {params}")

    data = await retrieve_lender_data(query_type, params)
    print(f"Found {len(data)} lenders")
    print(data[0] if data else "No data")

asyncio.run(test())
```

### Test 2: Test Document Classification

```bash
# Upload a bank statement PDF via your frontend or:
curl -X POST http://localhost:8000/api/v1/cases/{case_id}/documents \
  -F "file=@bank_statement.pdf"

# Check if it was classified
curl http://localhost:8000/api/v1/cases/{case_id}/document-checklist
```

### Test 3: Test Lender Copilot

```bash
# Query the copilot
curl -X POST http://localhost:8000/api/v1/copilot/query \
  -H "Content-Type: application/json" \
  -d '{"query": "lenders for 650 CIBIL"}'

# Should return lender list, not "No lenders found"
```

---

## PART 6: Deployment Checklist

### Before Deploying

- [ ] All database queries use `text()` and named parameters
- [ ] Lender data is loaded in database
- [ ] LLM API key is set (or fallback mode works)
- [ ] Document upload triggers OCR + classification
- [ ] Document checklist endpoint returns correct data
- [ ] Frontend shows real document status (not cached/random)
- [ ] All tests pass

### After Deploying

- [ ] Test document upload → classification
- [ ] Test copilot with various queries
- [ ] Monitor error logs for database query issues
- [ ] Check classification accuracy
- [ ] Verify LLM API calls are working

---

## Common Issues & Solutions

### Issue: "No lenders found" in copilot
**Solution**: Check if lender data is loaded. Run `SELECT COUNT(*) FROM lender_products;`

### Issue: Database query errors
**Solution**: Make sure you replaced `db.fetch()` with `db.execute(text(...))`

### Issue: Document always shows "unknown"
**Solution**: Check if OCR extraction is working. View document.ocr_text in database.

### Issue: Classification confidence is low
**Solution**: Improve OCR quality or retrain ML model with more training data.

### Issue: LLM API errors
**Solution**: Verify API key is correct and has credits. Check LLM_BASE_URL is correct.

---

## Quick Commands Reference

```bash
# Check database
psql -d dsa_case_os -c "SELECT COUNT(*) FROM lenders;"

# Load lender data
cd backend && python scripts/ingest_lender_data.py --policy-csv "..." --pincode-csv "..."

# Restart backend
uvicorn app.main:app --reload

# Test copilot
curl -X POST http://localhost:8000/api/v1/copilot/query \
  -H "Content-Type: application/json" \
  -d '{"query": "hello"}'

# View logs
tail -f logs/app.log
```

---

## Next Steps

1. **Fix the database queries first** (most critical)
2. **Verify lender data is loaded**
3. **Test copilot with simple query**
4. **Add auto-classification to document upload**
5. **Update frontend to show correct status**
6. **Configure LLM API (optional, has fallback)**

**Ready to implement? Start with PART 1 (fixing database queries) - that's the blocker for the copilot!**
