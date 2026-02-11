-- Add WhatsApp columns to cases table

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name='cases' AND column_name='whatsapp_number') THEN
        ALTER TABLE cases ADD COLUMN whatsapp_number VARCHAR(20);
        RAISE NOTICE 'Added whatsapp_number column';
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name='cases' AND column_name='whatsapp_session_id') THEN
        ALTER TABLE cases ADD COLUMN whatsapp_session_id VARCHAR(255);
        RAISE NOTICE 'Added whatsapp_session_id column';
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name='cases' AND column_name='whatsapp_linked_at') THEN
        ALTER TABLE cases ADD COLUMN whatsapp_linked_at TIMESTAMPTZ;
        RAISE NOTICE 'Added whatsapp_linked_at column';
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name='cases' AND column_name='whatsapp_qr_generated_at') THEN
        ALTER TABLE cases ADD COLUMN whatsapp_qr_generated_at TIMESTAMPTZ;
        RAISE NOTICE 'Added whatsapp_qr_generated_at column';
    END IF;
END $$;

SELECT column_name, data_type
FROM information_schema.columns
WHERE table_name = 'cases'
AND column_name LIKE 'whatsapp%'
ORDER BY column_name;
