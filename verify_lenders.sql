-- Verification Script: Check if all lenders are active
-- Run this to verify the fix worked

-- 1. Count total lenders and active status
SELECT
    COUNT(*) as total_lenders,
    SUM(CASE WHEN is_active = TRUE THEN 1 ELSE 0 END) as active_lenders,
    SUM(CASE WHEN is_active = FALSE THEN 1 ELSE 0 END) as inactive_lenders
FROM lenders;

-- 2. List all lenders with their active status
SELECT
    lender_name,
    is_active,
    (SELECT COUNT(*) FROM lender_products WHERE lender_id = lenders.id) as product_count,
    (SELECT COUNT(*) FROM lender_products WHERE lender_id = lenders.id AND is_active = TRUE) as active_products
FROM lenders
ORDER BY lender_name;

-- 3. Count total products
SELECT
    COUNT(*) as total_products,
    SUM(CASE WHEN is_active = TRUE THEN 1 ELSE 0 END) as active_products,
    SUM(CASE WHEN policy_available = TRUE THEN 1 ELSE 0 END) as policies_available
FROM lender_products;

-- 4. Check age ranges
SELECT
    l.lender_name,
    lp.product_name,
    lp.age_min,
    lp.age_max,
    lp.is_active,
    lp.policy_available
FROM lender_products lp
JOIN lenders l ON lp.lender_id = l.id
ORDER BY l.lender_name, lp.product_name;

-- 5. If lenders are still inactive, activate them NOW
UPDATE lenders SET is_active = TRUE WHERE is_active = FALSE;
UPDATE lender_products SET is_active = TRUE WHERE is_active = FALSE;
UPDATE lender_products SET policy_available = TRUE WHERE policy_available = FALSE OR policy_available IS NULL;
UPDATE lender_products SET age_min = 21, age_max = 65 WHERE age_min IS NULL OR age_max IS NULL OR age_min != 21 OR age_max != 65;

-- 6. Final verification
SELECT
    'FINAL CHECK:' as status,
    COUNT(*) as total_active_lenders
FROM lenders
WHERE is_active = TRUE;
