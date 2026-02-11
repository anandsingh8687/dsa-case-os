# Profile Tab Extraction - Fix & Test Guide

## 🎯 Goal
Make the Profile tab show all extracted data: Name, DOB, PAN, GST Number, Bank Statement Data, and all calculated parameters.

---

## 🔍 Step 1: Test If OCR Has Run

The extraction needs OCR text from documents first.

**Test in browser console (F12):**
```javascript
// Open localhost:8000, go to your case, open console (F12), run:
fetch('http://localhost:8000/api/v1/cases/CASE-20260210-0006/documents')
  .then(r => r.json())
  .then(data => {
    console.log('Total documents:', data.documents.length);
    console.log('Documents with OCR:', data.documents.filter(d => d.ocr_text).length);
    console.log('Documents without OCR:', data.documents.filter(d => !d.ocr_text).map(d => d.original_filename));
  });
```

**Expected:** All documents should have `ocr_text`. If not, OCR hasn't run yet.

**Fix if OCR missing:** Wait 15-20 seconds after upload, then refresh the page.

---

## 🔍 Step 2: Test Extraction Endpoint

**Test in browser console:**
```javascript
// Run extraction
fetch('http://localhost:8000/api/v1/extraction/case/CASE-20260210-0006/extract', {
  method: 'POST',
  headers: {
    'Authorization': 'Bearer ' + localStorage.getItem('token'),
    'Content-Type': 'application/json'
  }
})
.then(r => r.json())
.then(data => {
  console.log('Extraction result:', data);
  if (data.status === 'success') {
    console.log('✅ Fields extracted:', data.total_fields_extracted);
    console.log('✅ Completeness:', data.feature_completeness + '%');
  } else {
    console.error('❌ Extraction failed:', data);
  }
})
.catch(err => console.error('❌ Error:', err));
```

**Expected:** Should return `status: "success"` with extracted fields.

**Common Errors:**
- `No documents with OCR text found` → OCR hasn't run yet
- `Error extracting from document` → Check backend logs
- Network error → Backend not running

---

## 🔍 Step 3: Test Feature Vector Retrieval

**Test in browser console:**
```javascript
// Get feature vector
fetch('http://localhost:8000/api/v1/extraction/case/CASE-20260210-0006/features', {
  headers: {
    'Authorization': 'Bearer ' + localStorage.getItem('token')
  }
})
.then(r => r.json())
.then(data => {
  console.log('Feature Vector:', data);
  console.log('Name:', data.full_name);
  console.log('PAN:', data.pan_number);
  console.log('DOB:', data.dob);
  console.log('GSTIN:', data.gstin);
  console.log('CIBIL:', data.cibil_score);
  console.log('Avg Balance:', data.avg_monthly_balance);
  console.log('Monthly Credits:', data.monthly_credit_avg);
})
.catch(err => console.error('❌ Error:', err));
```

**Expected:** Should return all extracted data.

---

## 🐛 Common Issues & Fixes

### Issue 1: "Extracting..." button never finishes

**Cause:** JavaScript error in frontend

**Fix:** Open console (F12), look for red errors. Share them with me.

### Issue 2: "No documents with OCR text found"

**Cause:** OCR hasn't completed yet

**Fix:**
1. Wait 20-30 seconds after uploading documents
2. Refresh the page
3. Check if documents show OCR status
4. Try clicking "Run Extraction" again

### Issue 3: Extraction returns empty data

**Cause:** OCR text is present but extraction logic failing

**Fix:** Check backend logs:
```bash
docker logs dsa_case_os_backend | grep -i "extract\|error" | tail -50
```

Share the errors with me.

### Issue 4: Feature vector is null

**Cause:** Features weren't saved to database

**Fix:**
1. Run extraction again
2. Check if `borrower_features` table has data:
```bash
docker exec dsa_case_os_db psql -U postgres -d dsa_db -c "SELECT case_id, full_name, pan_number, gstin FROM borrower_features;"
```

---

## ✅ Verification Checklist

After running extraction, verify the Profile tab shows:

- [ ] **Identity Section:**
  - [ ] Full Name
  - [ ] PAN Number
  - [ ] Date of Birth

- [ ] **Business Section:**
  - [ ] Entity Type
  - [ ] Business Vintage (years)
  - [ ] GSTIN
  - [ ] Pincode

- [ ] **Financial Section:**
  - [ ] Annual Turnover
  - [ ] Average Monthly Balance (from bank statements)
  - [ ] Monthly Credits (from bank statements)
  - [ ] Bounces in last 12 months

- [ ] **Credit Section:**
  - [ ] CIBIL Score
  - [ ] Active Loans
  - [ ] Overdues

---

## 🚀 Complete Test Flow

1. **Upload documents** at `localhost:8000`
2. **Wait 20 seconds** for OCR to complete
3. **Refresh the page**
4. **Click on case** to open it
5. **Go to "Profile" tab**
6. **Click "Run Extraction"** button
7. **Wait 5-10 seconds**
8. **Verify data appears** in all 4 sections (Identity, Business, Financial, Credit)

---

## 📊 Expected Data Display

The Profile tab should show something like:

```
Identity                  Business
--------------------      --------------------
Name: John Doe           Entity: Proprietorship
PAN: ABCDE1234F          Vintage: 3 yrs
DOB: 1980-05-15          GSTIN: 27ABCDE1234F1Z5
                         Pincode: 400001

Financial                Credit
--------------------      --------------------
Annual Turnover: ₹50L    CIBIL Score: 730
Avg Balance: ₹2,50,000   Active Loans: 2
Monthly Credits: ₹5,00,000  Overdues: 0
Bounces (12m): 0
```

---

## 🔧 If Still Not Working

Run these commands and share the output with me:

```bash
# 1. Check backend logs
docker logs dsa_case_os_backend | tail -100

# 2. Check database for extracted data
docker exec dsa_case_os_db psql -U postgres -d dsa_db -c "
SELECT
  case_id,
  full_name,
  pan_number,
  gstin,
  cibil_score,
  feature_completeness
FROM borrower_features
ORDER BY created_at DESC
LIMIT 5;"

# 3. Check documents table
docker exec dsa_case_os_db psql -U postgres -d dsa_db -c "
SELECT
  original_filename,
  doc_type,
  CASE WHEN ocr_text IS NOT NULL THEN 'YES' ELSE 'NO' END as has_ocr
FROM documents
WHERE case_id = (SELECT id FROM cases WHERE case_id = 'CASE-20260210-0006');"
```

Share all outputs and I'll help fix any remaining issues!
