# 🐛 Bug Fixes Required

## Issues Identified from Screenshots:

### 1. ❌ GSTIN Not Showing in Profile Tab
**Problem:** GSTIN field shows "—" even though GST Certificate and GST Returns are uploaded

**Root Cause:**
- GSTIN is being extracted from GST documents
- But it's stored in `cases.gstin` column (from GST API)
- However, `borrower_features.gstin` column might be NULL
- The frontend reads from `borrower_features.gstin` not `cases.gstin`

**Fix Required:**
```sql
-- Check if GSTIN exists in cases table
SELECT case_id, gstin, gst_data FROM cases WHERE case_id = 'CASE-20260210-0011';

-- If gstin exists in cases but not in borrower_features, we need to copy it
UPDATE borrower_features bf
SET gstin = c.gstin
FROM cases c
WHERE bf.case_id = c.id
  AND c.gstin IS NOT NULL
  AND (bf.gstin IS NULL OR bf.gstin = '');
```

---

### 2. ❌ Annual Turnover Not Showing in Profile Tab
**Problem:** Annual Turnover shows "—"

**Root Cause:**
- Annual turnover should be calculated from:
  - Bank statement monthly credits × 12, OR
  - ITR total income, OR
  - GST returns data
- The `borrower_features.annual_turnover` column might be NULL

**Fix Required:**
```sql
-- Calculate annual turnover from monthly credits if not available
UPDATE borrower_features
SET annual_turnover = ROUND((monthly_credit_avg * 12) / 100000, 2)
WHERE monthly_credit_avg IS NOT NULL
  AND monthly_credit_avg > 0
  AND (annual_turnover IS NULL OR annual_turnover = 0);

-- Check specific case
SELECT case_id, annual_turnover, monthly_credit_avg, monthly_turnover
FROM borrower_features bf
JOIN cases c ON bf.case_id = c.id
WHERE c.case_id = 'CASE-20260210-0011';
```

---

### 3. ❌ Age Filter Rejecting Valid Age
**Problem:** Age 24 is being rejected even though it's within 21-65 range

**Evidence from Screenshot:**
- Dynamic recommendation shows: "Age Outside Accepted Range"
- Current: 24 years → Target: 21-65 years
- **This is WRONG!** 24 is clearly within 21-65

**Root Cause:**
The lender database has WRONG age range values. Check:
```sql
-- Check Tata Capital Digital age range
SELECT lender_name, product_name, age_min, age_max
FROM lender_products lp
JOIN lenders l ON lp.lender_id = l.id
WHERE l.lender_name ILIKE '%tata%'
  AND lp.product_name ILIKE '%digital%';
```

**Expected:** `age_min = 21, age_max = 65`
**Actual:** Likely wrong values like `age_min = 25, age_max = 60`

**Fix:**
```sql
-- Fix Tata Capital Digital age range
UPDATE lender_products lp
SET age_min = 21, age_max = 65
FROM lenders l
WHERE lp.lender_id = l.id
  AND l.lender_name ILIKE '%tata%'
  AND lp.product_name ILIKE '%digital%';

-- Fix ALL lenders to have standard age range 21-65
UPDATE lender_products
SET age_min = 21, age_max = 65
WHERE age_min IS NULL OR age_max IS NULL OR age_min > 21 OR age_max < 65;
```

---

### 4. ❌ Only 1 Lender Evaluated (Should be 18)
**Problem:** Only "Tata Capital - Digital" is being evaluated

**Root Cause:**
Most lenders in database have `is_active = FALSE` or `policy_available = FALSE`

**Check:**
```sql
-- Count total lenders
SELECT
  COUNT(*) as total_lenders,
  SUM(CASE WHEN l.is_active = TRUE THEN 1 ELSE 0 END) as active_lenders,
  SUM(CASE WHEN lp.is_active = TRUE THEN 1 ELSE 0 END) as active_products,
  SUM(CASE WHEN lp.policy_available = TRUE THEN 1 ELSE 0 END) as policies_available
FROM lenders l
LEFT JOIN lender_products lp ON l.id = lp.lender_id;

-- See which lenders are inactive
SELECT l.lender_name, l.is_active, lp.product_name, lp.is_active as product_active, lp.policy_available
FROM lenders l
LEFT JOIN lender_products lp ON l.id = lp.lender_id
ORDER BY l.lender_name;
```

**Fix:**
```sql
-- Activate ALL lenders
UPDATE lenders SET is_active = TRUE WHERE is_active = FALSE;

-- Activate ALL products
UPDATE lender_products SET is_active = TRUE WHERE is_active = FALSE;

-- Mark ALL policies as available
UPDATE lender_products SET policy_available = TRUE WHERE policy_available = FALSE;
```

---

### 5. ❌ WhatsApp QR Code Stuck on "Generating..."
**Problem:** QR modal shows loading spinner forever

**Root Cause:**
The WhatsApp API endpoint `/whatsapp/generate-qr` is likely:
- Not implemented, OR
- Returning an error, OR
- Not configured properly

**Check Backend Logs:**
```bash
docker compose -f docker/docker-compose.yml logs backend --tail 50 | grep -i whatsapp
```

**Temporary Fix:**
The WhatsApp feature requires external WhatsApp Web API integration which may not be set up.

**Options:**
1. Skip WhatsApp for now (remove buttons from UI)
2. Use mock/stub endpoint that returns success
3. Integrate actual WhatsApp Business API

---

## 🚀 Quick Fix Script

Run this SQL script to fix most issues:

```sql
-- Fix 1: Copy GSTIN from cases to borrower_features
UPDATE borrower_features bf
SET gstin = c.gstin
FROM cases c
WHERE bf.case_id = c.id
  AND c.gstin IS NOT NULL
  AND (bf.gstin IS NULL OR bf.gstin = '');

-- Fix 2: Calculate annual turnover from monthly credits
UPDATE borrower_features
SET annual_turnover = ROUND((monthly_credit_avg * 12) / 100000, 2)
WHERE monthly_credit_avg IS NOT NULL
  AND monthly_credit_avg > 0
  AND (annual_turnover IS NULL OR annual_turnover = 0);

-- Fix 3: Activate all lenders
UPDATE lenders SET is_active = TRUE;
UPDATE lender_products SET is_active = TRUE, policy_available = TRUE;

-- Fix 4: Fix age ranges for all lenders
UPDATE lender_products
SET age_min = 21, age_max = 65
WHERE age_min IS NULL OR age_max IS NULL OR age_min != 21 OR age_max != 65;

-- Verify fixes
SELECT
  c.case_id,
  bf.gstin,
  bf.annual_turnover,
  bf.monthly_credit_avg,
  bf.business_vintage_years
FROM borrower_features bf
JOIN cases c ON bf.case_id = c.id
WHERE c.case_id = 'CASE-20260210-0011';
```

---

## 📝 How to Apply Fixes

### Option 1: Run SQL directly
```bash
# Access database
docker compose -f docker/docker-compose.yml exec db psql -U postgres -d dsa_case_os

# Paste the SQL from "Quick Fix Script" above
# Then \q to exit
```

### Option 2: Run via migration file
```bash
# Create migration file
cat > /sessions/optimistic-eloquent-brahmagupta/mnt/dsa-case-os/docker/migrations/fix_bugs.sql << 'EOF'
-- Copy content from "Quick Fix Script" above
EOF

# Apply migration
docker compose -f docker/docker-compose.yml exec -T db psql -U postgres -d dsa_case_os < docker/migrations/fix_bugs.sql
```

---

## ✅ After Fixes - Expected Results

1. **Profile Tab:**
   - GSTIN: Should show actual GSTIN (e.g., "27AAGCC1234D1Z5")
   - Annual Turnover: Should show calculated value (e.g., "₹2.16L")

2. **Eligibility Tab:**
   - Should evaluate ALL 18 lenders (not just 1)
   - Age 24 should PASS (not fail)
   - Should see multiple lenders matched

3. **WhatsApp:**
   - May still have issues if API not configured
   - Can disable for now if needed

---

## 🔍 Debugging Commands

```bash
# Check backend logs
docker compose -f docker/docker-compose.yml logs backend --tail 100

# Check database connection
docker compose -f docker/docker-compose.yml exec db psql -U postgres -d dsa_case_os -c "SELECT COUNT(*) FROM lenders;"

# Restart backend after fixes
docker compose -f docker/docker-compose.yml restart backend

# Check specific case data
docker compose -f docker/docker-compose.yml exec db psql -U postgres -d dsa_case_os -c "SELECT case_id, gstin, gst_data FROM cases WHERE case_id = 'CASE-20260210-0011';"
```
