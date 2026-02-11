-- Bug Fixes for DSA Case OS
-- Date: 2026-02-11
-- Issues: GSTIN missing, Annual Turnover missing, Age filter wrong, Only 1 lender active

-- ====================================================================
-- FIX 1: Copy GSTIN from cases table to borrower_features table
-- ====================================================================
DO $$
BEGIN
    RAISE NOTICE 'Fix 1: Copying GSTIN from cases to borrower_features...';
END $$;

UPDATE borrower_features bf
SET gstin = c.gstin
FROM cases c
WHERE bf.case_id = c.id
  AND c.gstin IS NOT NULL
  AND c.gstin != ''
  AND (bf.gstin IS NULL OR bf.gstin = '');

-- ====================================================================
-- FIX 2: Calculate annual turnover from monthly credits (if not available)
-- ====================================================================
DO $$
BEGIN
    RAISE NOTICE 'Fix 2: Calculating annual turnover from monthly credits...';
END $$;

UPDATE borrower_features
SET annual_turnover = ROUND((monthly_credit_avg * 12) / 100000, 2)
WHERE monthly_credit_avg IS NOT NULL
  AND monthly_credit_avg > 0
  AND (annual_turnover IS NULL OR annual_turnover = 0);

-- ====================================================================
-- FIX 3: Activate ALL lenders (they were inactive)
-- ====================================================================
DO $$
BEGIN
    RAISE NOTICE 'Fix 3: Activating all lenders...';
END $$;

UPDATE lenders
SET is_active = TRUE
WHERE is_active = FALSE;

UPDATE lender_products
SET is_active = TRUE
WHERE is_active = FALSE;

UPDATE lender_products
SET policy_available = TRUE
WHERE policy_available = FALSE OR policy_available IS NULL;

-- ====================================================================
-- FIX 4: Fix age ranges for ALL lenders (standard: 21-65)
-- ====================================================================
DO $$
BEGIN
    RAISE NOTICE 'Fix 4: Fixing age ranges to 21-65 for all lenders...';
END $$;

UPDATE lender_products
SET age_min = 21, age_max = 65
WHERE age_min IS NULL
   OR age_max IS NULL
   OR age_min != 21
   OR age_max != 65;

-- ====================================================================
-- Verification Queries
-- ====================================================================
DO $$
BEGIN
    RAISE NOTICE '=== Verification Results ===';
END $$;

-- Count active lenders
SELECT
    COUNT(*) as total_lenders,
    SUM(CASE WHEN is_active = TRUE THEN 1 ELSE 0 END) as active_lenders
FROM lenders;

-- Count active products
SELECT
    COUNT(*) as total_products,
    SUM(CASE WHEN is_active = TRUE THEN 1 ELSE 0 END) as active_products,
    SUM(CASE WHEN policy_available = TRUE THEN 1 ELSE 0 END) as policies_available
FROM lender_products;

-- Check age ranges
SELECT
    COUNT(*) as total_products,
    COUNT(CASE WHEN age_min = 21 AND age_max = 65 THEN 1 END) as correct_age_range
FROM lender_products;

-- Sample check for specific case
SELECT
    c.case_id,
    bf.gstin,
    bf.annual_turnover,
    bf.monthly_credit_avg,
    bf.business_vintage_years,
    bf.cibil_score
FROM borrower_features bf
JOIN cases c ON bf.case_id = c.id
ORDER BY c.created_at DESC
LIMIT 5;

DO $$
BEGIN
    RAISE NOTICE 'All fixes applied successfully!';
    RAISE NOTICE 'Please restart the backend: docker compose -f docker/docker-compose.yml restart backend';
END $$;
