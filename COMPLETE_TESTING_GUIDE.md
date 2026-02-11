# Complete Feature Testing Guide

## 🎯 What We're Testing

1. ✅ **Flexible Upload Flow** (React Frontend)
2. ✅ **GST Auto-fill Functionality**
3. ✅ **Eligibility Explanations UI**
4. ✅ **LLM Narrative Reports**
5. ✅ **Lender Copilot - Complete Results**
6. ✅ **WhatsApp Integration**

---

## 🧪 Test Plan

### Prerequisites
- Backend running: http://localhost:8000
- Frontend running: http://localhost:5174
- Database migration completed ✅
- WhatsApp columns added ✅

---

## Test 1: Flexible Upload Flow (React Frontend)

**URL:** http://localhost:5174

### Steps:
1. Click "New Case"
2. **VERIFY:** You should see **Step 0** with two workflow cards:
   - [ ] "Fill Form First" (Traditional)
   - [ ] "Upload Documents First" ✨ SMART (with green badge)

### Test 1A: Form-First Workflow (Traditional)
1. Click "Fill Form First"
2. Fill out the form:
   - Borrower Name: Test Borrower
   - Entity Type: Partnership
   - Program Type: Banking Program
   - Industry: Trading
   - Pincode: 110001
   - Loan Amount: 10 Lakhs
3. Click "Next"
4. **VERIFY:** Moves to Step 2 (Upload Documents)
5. Upload any PDF
6. Click "Upload & Continue"
7. **VERIFY:** Shows "Complete" screen with case ID
8. **SUCCESS IF:** Case created without errors ✅

### Test 1B: Docs-First Workflow (SMART)
1. Go back to "New Case"
2. Click "Upload Documents First" ✨
3. **VERIFY:** Case ID is created automatically (should see in logs)
4. Upload a PDF with GST number (any document)
5. Wait 20 seconds
6. **VERIFY:**
   - [ ] "🔍 Extracting GST data..." message appears
   - [ ] Automatically transitions to Step 2 (Review & Complete)
7. **IF GST found:**
   - [ ] Green banner: "GST Data Extracted!"
   - [ ] Borrower name filled ✓
   - [ ] Entity type filled ✓
   - [ ] Pincode filled ✓
   - [ ] Green checkmarks visible
8. **IF NO GST:**
   - [ ] Blue banner: "No GST data extracted"
   - [ ] Form fields empty (manual entry)
9. Fill any remaining fields
10. Click "Complete Case"
11. **VERIFY:** Case completes successfully
12. **SUCCESS IF:** Docs-first workflow works with auto-fill ✅

---

## Test 2: GST Auto-fill (Either Workflow)

**Goal:** Verify GST API integration works

### Steps:
1. Create case using any workflow
2. Upload a document containing valid GSTIN: `27AAACC1206D1ZM`
3. Wait 15-20 seconds for processing
4. Go to backend logs and check:
   ```bash
   docker logs dsa_case_os_backend --tail 50 | grep GST
   ```
5. **VERIFY in logs:**
   - [ ] "Found GSTIN 27AAACC1206D1ZM"
   - [ ] "Fetching GST data for GSTIN"
   - [ ] "Successfully fetched GST data"

### Frontend Verification:
1. In React: Look for "GST Data Detected!" banner
2. Click "Auto-fill Form" button
3. **VERIFY:**
   - [ ] Borrower name populated
   - [ ] Entity type populated
   - [ ] Pincode populated
   - [ ] Green checkmarks appear

### API Test (Manual):
```bash
# Get case ID from created case, then:
curl http://localhost:8000/api/v1/cases/CASE-20260211-0001/gst-data \
  -H "Authorization: Bearer YOUR_TOKEN"

# Expected response:
# {
#   "gst_data": {
#     "gstin": "27AAACC1206D1ZM",
#     "borrower_name": "Some Company Name",
#     "entity_type": "pvt_ltd",
#     "pincode": "400001",
#     "business_vintage_years": 2.5
#   }
# }
```

**SUCCESS IF:** GST extraction and auto-fill works ✅

---

## Test 3: Eligibility Explanations (Static HTML)

**URL:** http://localhost:8000

### Test 3A: When NO Lenders Match
1. Login to static HTML
2. Create a case with very poor profile:
   - CIBIL: 500
   - Bank Balance: ₹5,000
   - Business Vintage: 0.5 years
3. Upload minimal documents
4. Go to "Eligibility" tab
5. Click "Run Eligibility Scoring"
6. **VERIFY:**
   - [ ] Red alert banner: "No Lenders Match This Profile"
   - [ ] Shows top 5 rejected lenders with reasons
   - [ ] Shows "💡 Recommendations to Improve Eligibility" section
   - [ ] Recommendations include:
     - "Work on improving CIBIL score (currently 500)"
     - "Increase average monthly bank balance"
     - "Business vintage is low"

### Test 3B: When SOME Lenders Match
1. Create a case with decent profile:
   - CIBIL: 720
   - Bank Balance: ₹100,000
   - Business Vintage: 3 years
2. Run eligibility scoring
3. **VERIFY:**
   - [ ] Shows matched lenders at top
   - [ ] Collapsible section at bottom: "🔍 Why some lenders didn't match (X rejected)"
   - [ ] Click to expand
   - [ ] Shows rejected lenders with specific reasons

**SUCCESS IF:** Rejection explanations display correctly ✅

---

## Test 4: LLM Narrative Reports

**URL:** http://localhost:8000

### Steps:
1. Login
2. Open any case with eligibility results
3. Go to "Report" tab
4. Click "Generate Report"
5. Wait 10 seconds
6. Look at "Submission Strategy" section

### Verification:
**EXPECTED (LLM Narrative):**
```
Based on the borrower profile with a CIBIL score of 720 and 3 years
of business vintage, we recommend approaching Tata Capital - Digital
Business Loan as the primary target. With an eligibility score of
85/100 and high approval probability, this lender offers...
```

**NOT EXPECTED (Old Bullet Format):**
```
**Primary Target:** Tata Capital
- Score: 85/100
- Probability: HIGH
```

### How to Check:
- [ ] Report has 2-3 **paragraphs**
- [ ] NOT bullet points
- [ ] Mentions lender names naturally
- [ ] Explains WHY it's recommended
- [ ] Professional tone

### If Report Shows Bullet Points:
Check backend logs for LLM errors:
```bash
docker logs dsa_case_os_backend | grep -i "kimi\|llm\|narrative"
```

**SUCCESS IF:** Report uses narrative paragraphs ✅

---

## Test 5: Lender Copilot - Complete Results

**URL:** http://localhost:8000 or http://localhost:5174

### Steps:
1. Go to "Lender Copilot" page/tab
2. Ask: **"Which lenders accept CIBIL below 650?"**
3. Wait for response

### Verification:
- [ ] Response shows **4 or more lenders**
- [ ] Lists: UGro, Protium, Credit Saison, Lendingkart
- [ ] Shows ALL matches (not truncated)
- [ ] NO message like "... and X more lenders"

### More Test Queries:
1. **"Show all lenders funding manufacturing"**
   - Should show **10+ lenders**
   - Not just top 5

2. **"Which lenders work in pincode 110001?"**
   - Should show complete list
   - Not truncated

### Previous Bug (FIXED):
- ❌ Was showing only 4-5 lenders (LIMIT clause)
- ✅ Now shows ALL matching lenders

**SUCCESS IF:** Copilot returns complete results (10+ lenders when available) ✅

---

## Test 6: WhatsApp Integration

**URL:** http://localhost:8000

### Test 6A: WhatsApp Share (Copy Text)
1. Login to static HTML
2. Open any case
3. Go to "Report" tab
4. Generate report
5. Look for "WhatsApp Share" section
6. **VERIFY:**
   - [ ] Section exists with "Copy Text" button
   - [ ] Shows preview of WhatsApp summary
7. Click "Copy Text"
8. **VERIFY:**
   - [ ] Success message: "Copied to clipboard!"
9. Paste into Notes app
10. **VERIFY format:**
```
📋 Case: CASE-20260211-0001

👤 Borrower: ABC Enterprises
🏢 Entity: Private Limited
📍 Location: Mumbai (400001)

💰 Profile:
- CIBIL: 740
- Avg Balance: ₹2.5L
- Vintage: 3 years

🎯 Top Lender: Tata Capital - Digital
- Score: 85/100
- Ticket: ₹2.5L - ₹10L
- Probability: HIGH

✨ Generated by DSA Case OS
```

**SUCCESS IF:** WhatsApp summary copies and formats correctly ✅

### Test 6B: WhatsApp QR Code (Advanced)
**Note:** This requires WhatsApp Web integration setup
1. Go to case
2. Look for WhatsApp section
3. Click "Generate QR Code"
4. **VERIFY:** QR code appears
5. Scan with WhatsApp mobile app
6. **VERIFY:** Chat session links to case

**SUCCESS IF:** QR code generates (full test needs WhatsApp setup) ✅

---

## Test 7: Monthly Turnover Display

**URL:** http://localhost:8000

### Steps:
1. Create case
2. Upload bank statements
3. Go to "Documents" tab
4. Click "Run Extraction"
5. Wait for extraction to complete
6. Go to "Profile" tab
7. Look at "Financial" section

### Verification:
- [ ] "Monthly Turnover" field visible
- [ ] Shows value in ₹ Lakhs
- [ ] Example: "Monthly Turnover: ₹5.25 Lakhs"

**SUCCESS IF:** Monthly turnover displays in Profile tab ✅

---

## Test 8: Complete End-to-End Flow

**Goal:** Create a complete case using all features

### Steps:
1. **Start:** http://localhost:5174 → New Case
2. **Choose:** "Upload Documents First" ✨
3. **Upload:** PDF with GSTIN
4. **Wait:** 20 seconds for GST extraction
5. **Verify:** Auto-fill works (name, entity, pincode)
6. **Complete:** Form and create case
7. **Upload More:** Bank statements
8. **Extract:** Run document extraction
9. **Check Profile:** Verify monthly turnover shows
10. **Run Eligibility:** Score the case
11. **Check Eligibility Tab:** Verify explanations show
12. **Generate Report:** Create intelligence report
13. **Check Report:** Verify narrative format (not bullets)
14. **Copy WhatsApp:** Test copy-to-clipboard
15. **Ask Copilot:** "Which lenders fund this profile?"

### Success Criteria:
- [ ] All steps complete without errors
- [ ] GST auto-fill works
- [ ] Monthly turnover displays
- [ ] Eligibility explanations show
- [ ] Report uses narrative format
- [ ] WhatsApp summary copies
- [ ] Copilot returns complete results

**SUCCESS IF:** Complete flow works end-to-end ✅

---

## 🐛 Common Issues & Solutions

### Issue 1: "Column does not exist" errors
**Solution:** Run both migration scripts:
```bash
docker exec -i dsa_case_os_db psql -U postgres -d dsa_case_os < add_gst_columns.sql
docker exec -i dsa_case_os_db psql -U postgres -d dsa_case_os < add_whatsapp_columns.sql
docker-compose -f docker/docker-compose.yml restart backend
```

### Issue 2: Step 0 (mode selection) not showing
**Solution:** Clear React cache:
```bash
cd frontend
rm -rf node_modules/.vite
npm run dev
```

### Issue 3: GST auto-fill not working
**Check:**
1. Backend logs: `docker logs dsa_case_os_backend | grep GST`
2. API key set: `docker exec dsa_case_os_backend env | grep LLM_API_KEY`
3. Document has valid GSTIN

### Issue 4: Report still shows bullets
**Check:**
1. LLM_API_KEY is set in docker/.env
2. Backend logs: `docker logs dsa_case_os_backend | grep -i kimi`
3. Fallback is working if API fails

### Issue 5: Eligibility explanations not showing
**Check:**
1. Run eligibility scoring first
2. Check if `failure_reasons` array is populated
3. Refresh page (Ctrl+Shift+R)

---

## 📊 Testing Checklist Summary

- [ ] Test 1A: Form-First Workflow
- [ ] Test 1B: Docs-First Workflow ✨
- [ ] Test 2: GST Auto-fill
- [ ] Test 3A: No Lenders Match (explanations)
- [ ] Test 3B: Partial Match (rejections)
- [ ] Test 4: LLM Narrative Reports
- [ ] Test 5: Copilot Complete Results
- [ ] Test 6A: WhatsApp Share Copy
- [ ] Test 6B: WhatsApp QR Code
- [ ] Test 7: Monthly Turnover Display
- [ ] Test 8: Complete End-to-End Flow

---

## 🎉 Success Criteria

**Phase 2 is COMPLETE when:**
- ✅ All 3 fixes working (LLM reports, eligibility UI, flexible flow)
- ✅ No database column errors
- ✅ GST auto-fill functioning
- ✅ Complete end-to-end case creation works
- ✅ All 10 tests pass

---

## 📞 If You Need Help

**Share with me:**
1. Which test failed
2. Error message (screenshot or text)
3. Backend logs: `docker logs dsa_case_os_backend --tail 100`
4. Browser console errors (F12)

I'll help debug immediately! 🚀
