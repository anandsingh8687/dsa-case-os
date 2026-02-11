-- Add GST columns to cases table if they don't exist

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name='cases' AND column_name='gstin') THEN
        ALTER TABLE cases ADD COLUMN gstin VARCHAR(15);
        RAISE NOTICE 'Added gstin column';
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name='cases' AND column_name='gst_data') THEN
        ALTER TABLE cases ADD COLUMN gst_data JSONB;
        RAISE NOTICE 'Added gst_data column';
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name='cases' AND column_name='gst_fetched_at') THEN
        ALTER TABLE cases ADD COLUMN gst_fetched_at TIMESTAMPTZ;
        RAISE NOTICE 'Added gst_fetched_at column';
    END IF;
END $$;

SELECT column_name, data_type
FROM information_schema.columns
WHERE table_name = 'cases'
AND column_name IN ('gstin', 'gst_data', 'gst_fetched_at', 'business_vintage_years')
ORDER BY column_name;
