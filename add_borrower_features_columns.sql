-- Add monthly_turnover column to borrower_features table

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name='borrower_features' AND column_name='monthly_turnover') THEN
        ALTER TABLE borrower_features ADD COLUMN monthly_turnover FLOAT;
        RAISE NOTICE 'Added monthly_turnover column to borrower_features';
    END IF;
END $$;

-- Verify column was added
SELECT column_name, data_type
FROM information_schema.columns
WHERE table_name = 'borrower_features'
AND column_name IN ('monthly_turnover', 'monthly_credit_avg', 'business_vintage_years')
ORDER BY column_name;
