# 🚀 START HERE - Quick Fix Guide

## What's Wrong?

You have two main issues:

### 1. ❌ Document Classification Not Working
- Uploaded PDFs show as "unknown"
- Frontend shows random green checkmarks for documents you didn't upload
- System has a classifier but it's not being triggered

### 2. ❌ Lender Copilot Returning "No lenders found"
- All queries return empty results
- Database queries are using wrong method
- Lender data may not be loaded

---

## Quick Fix (5 Steps)

### STEP 1: Fix Database Queries (CRITICAL) ⚠️

**Problem**: Code uses `db.fetch()` which doesn't exist in SQLAlchemy AsyncSession

**Solution**: Replace the retriever file

```bash
cd /path/to/dsa-case-os/backend/app/services/stages

# Backup the old file
mv stage7_retriever.py stage7_retriever_OLD.py

# Use the fixed version
mv stage7_retriever_FIXED.py stage7_retriever.py
```

**What was fixed**:
- Changed `db.fetch()` → `db.execute(text())`
- Changed `$1, $2` params → `:param_name`
- Added `from sqlalchemy import text`
- Fixed result mapping: `dict(row._mapping)`

---

### STEP 2: Check if Lender Data Exists

```bash
# Connect to database
psql -U postgres -d dsa_case_os

# Check if data is loaded
SELECT COUNT(*) FROM lenders;          -- Should be 25+
SELECT COUNT(*) FROM lender_products;  -- Should be 87+
SELECT COUNT(*) FROM lender_pincodes;  -- Should be 21,000+
```

**If any return 0**, you need to load data:

```bash
cd backend
python scripts/ingest_lender_data.py \
  --policy-csv "path/to/Lender Policy.csv" \
  --pincode-csv "path/to/Pincode list.csv"
```

---

### STEP 3: Test Copilot

```bash
# Restart your backend
uvicorn app.main:app --reload --port 8000

# Test the copilot
curl -X POST http://localhost:8000/api/v1/copilot/query \
  -H "Content-Type: application/json" \
  -d '{"query": "lenders for 650 CIBIL"}'

# Should now return lender data, not "No lenders found"
```

---

### STEP 4: Configure LLM API (Optional)

The copilot works in two modes:
1. **With API**: Natural language responses using Kimi 2.5
2. **Without API**: Template-based responses (fallback mode)

**To enable full LLM responses**:

```bash
# Create .env file
cd backend
echo 'LLM_API_KEY=your-moonshot-api-key-here' >> .env
echo 'LLM_MODEL=moonshot-v1-8k' >> .env
echo 'LLM_BASE_URL=https://api.moonshot.cn/v1' >> .env
```

Get API key from: https://platform.moonshot.cn/

---

### STEP 5: Fix Document Classification (Frontend Issue)

The document status issue is because:
- Backend classifier exists and works
- But frontend is showing cached/hardcoded status

**Backend fix needed**:

Add this endpoint to `backend/app/api/v1/endpoints/cases.py`:

```python
@router.get("/{case_id}/document-checklist")
async def get_document_checklist(case_id: str, db: AsyncSession = Depends(get_db)):
    """Get actual document status for a case."""

    # Required document types
    required = ["gst_certificate", "bank_statement", "itr", "aadhaar", "pan_personal"]

    # Get uploaded documents
    docs = await db.execute(
        select(Document).where(Document.case_id == UUID(case_id))
    )
    uploaded = docs.scalars().all()

    # Build checklist
    checklist = {}
    for doc_type in required:
        matching = [d for d in uploaded if d.doc_type == doc_type]
        if matching:
            best = max(matching, key=lambda d: d.classification_confidence or 0)
            checklist[doc_type] = {
                "status": "available",
                "confidence": best.classification_confidence
            }
        else:
            checklist[doc_type] = {"status": "missing", "confidence": None}

    return checklist
```

**Frontend fix**: Call this endpoint instead of showing hardcoded status

---

## Verification Checklist

After applying fixes:

- [ ] STEP 1: Replaced retriever file with fixed version
- [ ] STEP 2: Verified lender data exists (COUNT > 0)
- [ ] STEP 3: Tested copilot - returns lender data
- [ ] STEP 4: (Optional) Set LLM_API_KEY for better responses
- [ ] STEP 5: Frontend shows correct document status

---

## Test Commands

```bash
# Test 1: Check database data
psql -d dsa_case_os -c "SELECT lender_name FROM lenders LIMIT 5;"

# Test 2: Test copilot CIBIL query
curl -X POST http://localhost:8000/api/v1/copilot/query \
  -H "Content-Type: application/json" \
  -d '{"query": "Which lenders fund below 650 CIBIL?"}'

# Test 3: Test copilot pincode query
curl -X POST http://localhost:8000/api/v1/copilot/query \
  -H "Content-Type: application/json" \
  -d '{"query": "who serves pincode 400001"}'

# Test 4: Test copilot comparison
curl -X POST http://localhost:8000/api/v1/copilot/query \
  -H "Content-Type: application/json" \
  -d '{"query": "compare Bajaj and IIFL for business loans"}'

# All should return lender data (not "No lenders found")
```

---

## Additional Documentation

I've created detailed guides for you:

1. **FIXES_REQUIRED.md** - Complete problem analysis
2. **IMPLEMENTATION_GUIDE.md** - Step-by-step code fixes
3. **stage7_retriever_FIXED.py** - Ready-to-use fixed file
4. **START_HERE.md** - This quick reference (you are here)

---

## What Happens After Fixes?

### ✅ Lender Copilot Will:
- Return accurate lender matches for CIBIL queries
- Show lenders by pincode
- Compare multiple lenders
- Filter by vintage, turnover, entity type
- Work in hybrid mode (DB data + general knowledge)

### ✅ Document Classification Will:
- Show only actually uploaded documents
- Automatically classify PDFs after upload
- Display confidence scores
- Update status in real-time

---

## Common Issues & Solutions

### Issue: Still getting "No lenders found"
**Check**:
1. Did you replace the retriever file? `ls -la stage7_retriever.py`
2. Did you restart the backend? `pkill uvicorn && uvicorn app.main:app --reload`
3. Is lender data loaded? `psql -d dsa_case_os -c "SELECT COUNT(*) FROM lenders;"`

### Issue: Database query errors
**Check**: Look for error message. Common causes:
- Old file still being used (didn't replace correctly)
- Database connection issues
- Table doesn't exist (need to run migrations)

### Issue: LLM API errors
**Check**:
- Is API key correct in .env?
- Does API have credits?
- Try without API key first (fallback mode still works)

---

## Priority Order

**Do in this order**:

1. **FIRST**: Fix database queries (STEP 1) ← BLOCKING ISSUE
2. **SECOND**: Verify lender data loaded (STEP 2) ← BLOCKING ISSUE
3. **THIRD**: Test copilot works (STEP 3) ← VERIFY FIX
4. **FOURTH**: Set API key (STEP 4) ← OPTIONAL
5. **FIFTH**: Fix frontend status (STEP 5) ← NICE TO HAVE

**Start with STEP 1 - that's the main blocker!**

---

## Need Help?

If something doesn't work:

1. Check backend logs: `tail -f logs/app.log`
2. Check database connection: `psql -d dsa_case_os -c "SELECT 1;"`
3. Verify Python imports: `python -c "from sqlalchemy import text; print('OK')"`
4. Test simple query: `psql -d dsa_case_os -c "SELECT * FROM lenders LIMIT 1;"`

---

## Next Steps After Fixes

Once everything works:

1. **Train classifier with real documents** - Improve classification accuracy
2. **Add more lender data** - Update CSV files with latest policies
3. **Monitor copilot queries** - See what users ask most
4. **Optimize database** - Add indexes if queries are slow
5. **Add analytics** - Track classification accuracy & query success rate

---

## TL;DR - Absolute Minimum

If you only do ONE thing:

```bash
cd backend/app/services/stages
mv stage7_retriever.py stage7_retriever_OLD.py
mv stage7_retriever_FIXED.py stage7_retriever.py
pkill uvicorn
uvicorn app.main:app --reload
```

Then test:
```bash
curl -X POST http://localhost:8000/api/v1/copilot/query \
  -H "Content-Type: application/json" \
  -d '{"query": "hello"}'
```

Should return helpful response, not "No lenders found"!

---

**Good luck! 🚀**
