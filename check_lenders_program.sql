-- Check which lenders match which program types
SELECT 
  l.lender_name,
  lp.product_name,
  lp.program_type,
  lp.is_active,
  lp.policy_available
FROM lender_products lp
JOIN lenders l ON lp.lender_id = l.id
WHERE l.is_active = TRUE
ORDER BY lp.program_type, l.lender_name;

-- Count by program type
SELECT 
  program_type,
  COUNT(*) as product_count
FROM lender_products
WHERE is_active = TRUE
GROUP BY program_type;
