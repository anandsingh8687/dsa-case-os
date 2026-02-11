# 🔧 Quick Fix Instructions

## Issues You're Facing:

1. ❌ GSTIN not showing in Profile tab
2. ❌ Annual Turnover not showing in Profile tab
3. ❌ Age 24 being rejected (should pass 21-65 range)
4. ❌ Only 1 lender evaluated (should be 18)
5. ⚠️ WhatsApp QR stuck on loading

---

## ✅ Solution: Run This One Command

```bash
cd /sessions/optimistic-eloquent-brahmagupta/mnt/dsa-case-os

docker compose -f docker/docker-compose.yml exec -T db psql -U postgres -d dsa_case_os < docker/migrations/fix_bugs_20260211.sql
```

This will fix issues #1, #2, #3, and #4.

---

## 🔄 After Running the Fix

1. **Restart Backend:**
   ```bash
   docker compose -f docker/docker-compose.yml restart backend
   ```

2. **Refresh Browser:**
   - Hard refresh: `Ctrl + Shift + R` (or `Cmd + Shift + R` on Mac)

3. **Reopen the Case:**
   - Go to Dashboard
   - Click on "VANASHREE ASSOCIATES" case
   - Go to Eligibility tab
   - Click "Run Eligibility Scoring"

---

## ✅ Expected Results After Fix:

### Profile Tab:
- **GSTIN:** Will show the actual GST number (not "—")
- **Annual Turnover:** Will show calculated value like "₹2.16L"

### Eligibility Tab:
- **Total Evaluated:** Should show 18 lenders (not just 1)
- **Matched:** Will show how many lenders passed
- **Age Filter:** Age 24 will PASS (not fail)

---

## 🐛 WhatsApp Issue (Separate)

The WhatsApp QR is stuck because the backend API is not fully implemented.

**Temporary Solution:**
Skip WhatsApp features for now. The other features (Dynamic Recommendations, Upload-First Workflow) are working.

**To Disable WhatsApp Buttons:**
Comment out WhatsApp buttons in the UI if needed (optional).

---

## 🆘 If Issues Persist

1. **Check backend logs:**
   ```bash
   docker compose -f docker/docker-compose.yml logs backend --tail 50
   ```

2. **Check database:**
   ```bash
   docker compose -f docker/docker-compose.yml exec db psql -U postgres -d dsa_case_os -c "SELECT COUNT(*) FROM lenders WHERE is_active = TRUE;"
   ```
   Should return: **18** (or similar)

3. **Manually verify case data:**
   ```bash
   docker compose -f docker/docker-compose.yml exec db psql -U postgres -d dsa_case_os -c "SELECT c.case_id, bf.gstin, bf.annual_turnover FROM borrower_features bf JOIN cases c ON bf.case_id = c.id WHERE c.case_id = 'CASE-20260210-0011';"
   ```

---

## 📝 What the Fix Does:

1. **Copies GSTIN** from `cases` table to `borrower_features` table
2. **Calculates Annual Turnover** from monthly credits (monthly_credit_avg × 12 ÷ 100000)
3. **Activates all 18 lenders** (they were marked inactive)
4. **Fixes age ranges** to standard 21-65 for all lenders

---

## ⏱️ Takes ~10 seconds to run

Just copy-paste the command and hit Enter!
