-- Migration: Add WhatsApp integration fields
-- Date: 2026-02-10
-- Description: Adds fields for per-case WhatsApp chat integration

-- Add WhatsApp fields to cases table
ALTER TABLE cases
ADD COLUMN IF NOT EXISTS whatsapp_number VARCHAR(20),           -- Linked WhatsApp number (+91XXXXXXXXXX)
ADD COLUMN IF NOT EXISTS whatsapp_session_id VARCHAR(100),      -- Unique session ID for this case
ADD COLUMN IF NOT EXISTS whatsapp_linked_at TIMESTAMPTZ,        -- When WhatsApp was linked
ADD COLUMN IF NOT EXISTS whatsapp_qr_generated_at TIMESTAMPTZ;  -- Last QR generation time

-- Create index for WhatsApp lookups
CREATE INDEX IF NOT EXISTS idx_cases_whatsapp_number ON cases(whatsapp_number);
CREATE INDEX IF NOT EXISTS idx_cases_whatsapp_session_id ON cases(whatsapp_session_id);

-- Create WhatsApp messages table
CREATE TABLE IF NOT EXISTS whatsapp_messages (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    case_id         UUID NOT NULL REFERENCES cases(id) ON DELETE CASCADE,

    -- Message details
    message_id      VARCHAR(100),                -- WhatsApp message ID
    from_number     VARCHAR(20) NOT NULL,        -- Sender number
    to_number       VARCHAR(20) NOT NULL,        -- Recipient number
    message_type    VARCHAR(20) DEFAULT 'text',  -- text, image, document, audio, video
    message_body    TEXT,                        -- Text content
    media_url       TEXT,                        -- URL for media messages

    -- Direction
    direction       VARCHAR(10) NOT NULL,        -- inbound, outbound

    -- Status
    status          VARCHAR(20) DEFAULT 'sent',  -- sent, delivered, read, failed

    -- Timestamps
    sent_at         TIMESTAMPTZ DEFAULT NOW(),
    delivered_at    TIMESTAMPTZ,
    read_at         TIMESTAMPTZ,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- Create indexes for message queries
CREATE INDEX IF NOT EXISTS idx_whatsapp_messages_case_id ON whatsapp_messages(case_id);
CREATE INDEX IF NOT EXISTS idx_whatsapp_messages_message_id ON whatsapp_messages(message_id);
CREATE INDEX IF NOT EXISTS idx_whatsapp_messages_from_number ON whatsapp_messages(from_number);
CREATE INDEX IF NOT EXISTS idx_whatsapp_messages_created_at ON whatsapp_messages(created_at DESC);

-- Add comment
COMMENT ON TABLE whatsapp_messages IS 'Stores WhatsApp messages for per-case chat integration';
COMMENT ON COLUMN cases.whatsapp_session_id IS 'Unique session ID used for QR code linking';
