-- Migration: Add GST API and Monthly Turnover fields
-- Date: 2026-02-10
-- Author: Claude AI
-- Description: Adds fields for GST API integration and monthly turnover calculation

-- Add GST fields to cases table
ALTER TABLE cases
ADD COLUMN IF NOT EXISTS gstin VARCHAR(15),
ADD COLUMN IF NOT EXISTS gst_data JSONB,
ADD COLUMN IF NOT EXISTS gst_fetched_at TIMESTAMPTZ;

-- Add index on gstin for faster lookups
CREATE INDEX IF NOT EXISTS idx_cases_gstin ON cases(gstin);

-- Add monthly_turnover to borrower_features table
ALTER TABLE borrower_features
ADD COLUMN IF NOT EXISTS monthly_turnover FLOAT;

-- Add comment to document the new columns
COMMENT ON COLUMN cases.gstin IS 'GST Identification Number extracted from documents';
COMMENT ON COLUMN cases.gst_data IS 'Raw GST API response data from taxpayer.irisgst.com';
COMMENT ON COLUMN cases.gst_fetched_at IS 'Timestamp when GST data was fetched from API';
COMMENT ON COLUMN borrower_features.monthly_turnover IS 'Average monthly turnover (same as monthly_credit_avg from bank statements)';
