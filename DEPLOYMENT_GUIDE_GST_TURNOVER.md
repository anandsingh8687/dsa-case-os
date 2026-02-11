# Deployment Guide: GST API & Monthly Turnover Features

**Quick deployment guide for the GST API integration and monthly turnover features**

---

## Prerequisites

- PostgreSQL database running
- Python 3.10+ environment
- Backend server not running (will restart)

---

## Step 1: Database Migration

Apply the schema changes:

```bash
cd /sessions/charming-practical-curie/mnt/dsa-case-os/backend

# Option A: Using psql
psql -h localhost -U postgres -d dsa_case_os -f migrations/add_gst_and_turnover_fields.sql

# Option B: Using SQLAlchemy (columns will be created automatically on app startup)
# No action needed - columns will be created when the app starts
```

**Verify migration:**
```sql
-- Check if columns exist
\d cases
\d borrower_features

-- Should see:
-- cases: gstin, gst_data, gst_fetched_at
-- borrower_features: monthly_turnover
```

---

## Step 2: Update Python Dependencies

No new dependencies required. All features use existing packages:
- `httpx` - Already in requirements (for GST API calls)
- `re` - Python stdlib (for GSTIN extraction)
- `datetime` - Python stdlib (for vintage calculation)

---

## Step 3: Restart Backend Server

```bash
cd /sessions/charming-practical-curie/mnt/dsa-case-os/backend

# Stop existing server (if running)
pkill -f "uvicorn app.main:app" || true

# Start server
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Or use your existing start script
./start.sh  # if you have one
```

**Verify startup:**
- Check logs for no errors
- API should be running at `http://localhost:8000`
- Swagger docs: `http://localhost:8000/docs`

---

## Step 4: Verify New API Endpoint

Test the GST data endpoint:

```bash
# Get your auth token
TOKEN="your-jwt-token-here"

# Test endpoint (should return 404 if no GST data yet)
curl -X GET "http://localhost:8000/api/cases/CASE-20260210-0001/gst-data" \
  -H "Authorization: Bearer $TOKEN"
```

**Expected responses:**
- **404:** `{"detail": "No GST data available for this case"}` - Normal for cases without GST documents
- **200:** Returns GST data JSON - Success!

---

## Step 5: Test End-to-End Flow

### Test Case 1: GST API Integration

1. **Create a new case:**
```bash
curl -X POST "http://localhost:8000/api/cases/" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "borrower_name": "Test Company",
    "program_type": "Banking"
  }'
```

2. **Upload a GST document** (PDF with GSTIN in text)

3. **Check logs** for GST extraction:
```bash
tail -f backend/logs/app.log | grep -i "gst\|gstin"
```

Expected log messages:
```
INFO: Found GSTIN 22BTTPR3963C1ZF in document abc123
INFO: Fetching GST data for GSTIN 22BTTPR3963C1ZF
INFO: Successfully saved GST data for case CASE-20260210-0001
```

4. **Verify case updated:**
```bash
curl -X GET "http://localhost:8000/api/cases/{case_id}" \
  -H "Authorization: Bearer $TOKEN"
```

Should show:
```json
{
  "case_id": "CASE-20260210-0001",
  "borrower_name": "LAKSHMI TRADERS",
  "entity_type": "proprietorship",
  "business_vintage_years": 1.85,
  "gstin": "22BTTPR3963C1ZF"
}
```

### Test Case 2: Monthly Turnover

1. **Upload bank statements** to the case

2. **Run extraction:**
```bash
curl -X POST "http://localhost:8000/api/extraction/extract/{case_id}" \
  -H "Authorization: Bearer $TOKEN"
```

3. **Check feature vector:**
```bash
curl -X GET "http://localhost:8000/api/extraction/features/{case_id}" \
  -H "Authorization: Bearer $TOKEN"
```

Should show:
```json
{
  "monthly_credit_avg": 450000,
  "monthly_turnover": 450000,
  "avg_monthly_balance": 125000,
  ...
}
```

---

## Step 6: Frontend Verification

1. **Open the frontend** (usually `http://localhost:3000`)

2. **Navigate to a case** with GST/bank data

3. **Click Profile tab**

4. **Verify fields display:**
   - Business Vintage Years: `1.85`
   - Monthly Turnover: `450000`
   - Monthly Credit Avg: `450000`

---

## Rollback Plan (if needed)

If issues occur, rollback database changes:

```sql
-- Remove new columns
ALTER TABLE cases
DROP COLUMN IF EXISTS gstin,
DROP COLUMN IF EXISTS gst_data,
DROP COLUMN IF EXISTS gst_fetched_at;

ALTER TABLE borrower_features
DROP COLUMN IF EXISTS monthly_turnover;
```

Then restart with previous codebase version.

---

## Monitoring & Logs

**What to monitor:**

1. **GST API calls:**
```bash
grep "GST API" backend/logs/app.log | tail -20
```

2. **GSTIN extraction:**
```bash
grep "GSTIN" backend/logs/app.log | tail -20
```

3. **Feature assembly:**
```bash
grep "monthly_turnover" backend/logs/app.log | tail -20
```

**Common issues:**

| Issue | Solution |
|-------|----------|
| GST API timeout | Check network, verify API key is valid |
| No GSTIN found | OCR quality issue, check document clarity |
| Monthly turnover is None | Bank statement not uploaded or parsing failed |
| Business vintage not showing | GST data not fetched, check logs |

---

## Performance Impact

**Expected:**
- GST API call: ~2-5 seconds per document (async, non-blocking)
- Database queries: No noticeable impact (indexed fields)
- Storage: ~5-10 KB per case for GST data (JSONB)

**No impact on:**
- Document upload speed
- OCR processing
- Classification
- Frontend rendering

---

## Security Notes

**GST API Key:**
- Currently hardcoded in `gst_api.py`
- **Recommendation:** Move to environment variable

**To improve security:**
```python
# In app/core/config.py
GST_API_KEY = os.getenv("GST_API_KEY", "default-key")

# In gst_api.py
from app.core.config import settings
API_KEY = settings.GST_API_KEY
```

---

## Support Checklist

Before requesting support, verify:

- [ ] Database migration ran successfully
- [ ] Backend server restarted
- [ ] No errors in startup logs
- [ ] New API endpoint accessible
- [ ] Test document uploaded successfully
- [ ] Logs show GST extraction attempt

---

## Success Criteria

✅ **Deployment successful if:**

1. Database has new columns (gstin, gst_data, monthly_turnover)
2. Backend starts without errors
3. GST documents trigger API calls
4. Case fields auto-populate from GST
5. Bank analysis populates monthly_turnover
6. Frontend displays new fields correctly

---

**Deployment completed by:** [Your Name]
**Date:** February 10, 2026
**Version:** 1.0
