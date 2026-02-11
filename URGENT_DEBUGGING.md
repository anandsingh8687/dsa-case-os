# 🚨 Urgent Debugging Guide

## Issue 1: Still Only 1 Lender Showing

### Root Cause Investigation:

**Hypothesis 1: Program Type Filter**
The system filters lenders by `program_type`. If your case is set to "banking" program, it will ONLY evaluate lenders with "banking" products.

**Check this:**
```bash
docker compose -f docker/docker-compose.yml exec -T db psql -U postgres -d dsa_case_os < check_lenders_program.sql
```

This will show how many lenders match each program type.

---

### **Quick Test: Check Case Program Type**

```bash
docker compose -f docker/docker-compose.yml exec -T db psql -U postgres -d dsa_case_os -c "SELECT case_id, borrower_name, program_type FROM cases WHERE case_id LIKE 'CASE-20260210%' ORDER BY created_at DESC LIMIT 5;"
```

**Expected Output:**
- If `program_type = 'banking'` → Only ~8-10 lenders will be evaluated
- If `program_type = 'income'` → Only ~6-8 lenders will be evaluated
- If `program_type = 'hybrid'` → All ~24 products will be evaluated

---

## Issue 2: WhatsApp QR Still Not Loading

### **Step 1: Hard Refresh Browser**
Press: **Cmd + Shift + R** (or Ctrl + Shift + R)

### **Step 2: Clear All Browser Cache**
1. Open DevTools (F12)
2. Right-click the refresh button
3. Select "Empty Cache and Hard Reload"

### **Step 3: Check API Response**

In browser console (Network tab), filter for "generate-qr" and check:
- Does the request get sent?
- What's the response status?
- What's the response body?

---

## 🔧 **Complete Fix Commands**

Run these in order:

```bash
cd /Users/aparajitasharma/Downloads/dsa-case-os

# 1. Check program types
docker compose -f docker/docker-compose.yml exec -T db psql -U postgres -d dsa_case_os < check_lenders_program.sql

# 2. Check case details
docker compose -f docker/docker-compose.yml exec -T db psql -U postgres -d dsa_case_os -c "SELECT case_id, borrower_name, program_type FROM cases WHERE case_id = 'CASE-20260210-0016';"

# 3. Restart backend (to pick up JS changes)
docker compose -f docker/docker-compose.yml restart backend

# 4. Check backend logs
docker compose -f docker/docker-compose.yml logs backend --tail 50

# 5. Check WhatsApp logs
docker compose -f docker/docker-compose.yml logs whatsapp --tail 30
```

---

## 🎯 **What to Look For**

### **In Database Results:**

If program_type filtering shows:
- **banking**: ~8-10 products available
- **income**: ~6-8 products available
- **hybrid** or **NULL**: ~24 products available

### **In Browser Console:**

When clicking "Run Eligibility Scoring":
- Should see: `GET /api/v1/eligibility/case/CASE-XXX/results`
- Check response: `total_lenders_evaluated` field
- If it says `1`, that's the actual scoring result (not cached)

---

## 🔍 **Verify It's Not Just This Profile**

This borrower might legitimately only match 1 lender due to:
- Low CIBIL score
- New business (low vintage)
- High existing debt (FOIR)
- Specific entity type not accepted

**Test with a different case** to verify lenders are working:
1. Go to Dashboard
2. Open a different case (like SHIVRAJ TRADERS)
3. Run eligibility scoring there
4. See how many lenders match

---

## 📊 **Expected Behavior After All Fixes**

### **For VANASHREE ASSOCIATES:**
- Depends on profile quality
- Could legitimately be 1-3 lenders if profile is weak

### **For SHIVRAJ TRADERS (better profile):**
- Should see 5-10+ lenders matched
- Higher CIBIL = more matches

---

## 🚀 **Action Items**

1. ✅ Run the SQL check for program types
2. ✅ Hard refresh browser (Cmd+Shift+R)
3. ✅ Check a DIFFERENT case to see if lenders work there
4. ✅ Share the results of all three

This will tell us if it's:
- A) Program type filter (expected behavior)
- B) Profile is weak (expected behavior)
- C) Actual bug (needs more fixing)
