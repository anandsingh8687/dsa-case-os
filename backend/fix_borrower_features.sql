-- Fix borrower_features table to match SQLAlchemy model
-- Add created_at and updated_at columns

BEGIN;

-- Check if columns already exist before adding them
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'borrower_features' AND column_name = 'created_at'
    ) THEN
        ALTER TABLE borrower_features
        ADD COLUMN created_at TIMESTAMPTZ DEFAULT NOW();
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'borrower_features' AND column_name = 'updated_at'
    ) THEN
        ALTER TABLE borrower_features
        ADD COLUMN updated_at TIMESTAMPTZ DEFAULT NOW();
    END IF;

    -- Remove old last_updated column if it exists
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'borrower_features' AND column_name = 'last_updated'
    ) THEN
        -- Copy last_updated to updated_at before dropping
        UPDATE borrower_features SET updated_at = last_updated WHERE last_updated IS NOT NULL;
        ALTER TABLE borrower_features DROP COLUMN last_updated;
    END IF;
END $$;

COMMIT;
