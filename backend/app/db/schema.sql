-- ═══════════════════════════════════════════════════════════════
-- DSA CASE OS - Master Database Schema
-- This is THE source of truth for all tables.
-- Every Cowork task must use this schema as-is.
-- ═══════════════════════════════════════════════════════════════

-- Extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ─── USERS ────────────────────────────────────────────────────
CREATE TABLE users (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    email           VARCHAR(255) UNIQUE NOT NULL,
    phone           VARCHAR(15),
    full_name       VARCHAR(255) NOT NULL,
    hashed_password VARCHAR(512) NOT NULL,
    role            VARCHAR(20) DEFAULT 'dsa',      -- dsa, admin, team_lead
    organization    VARCHAR(255),
    is_active       BOOLEAN DEFAULT TRUE,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

-- ─── CASES ────────────────────────────────────────────────────
CREATE TABLE cases (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    case_id         VARCHAR(20) UNIQUE NOT NULL,     -- CASE-YYYYMMDD-XXXX
    user_id         UUID NOT NULL REFERENCES users(id),
    status          VARCHAR(30) NOT NULL DEFAULT 'created',
    program_type    VARCHAR(10),                      -- banking, income, hybrid

    -- Borrower basics (manual overrides)
    borrower_name       VARCHAR(255),
    entity_type         VARCHAR(20),
    business_vintage_years FLOAT,
    cibil_score_manual  INTEGER,
    monthly_turnover_manual FLOAT,
    industry_type       VARCHAR(100),
    pincode             VARCHAR(10),
    loan_amount_requested FLOAT,

    -- GST data
    gstin               VARCHAR(15),                      -- GSTIN extracted from documents
    gst_data            JSONB,                             -- Raw GST API response
    gst_fetched_at      TIMESTAMPTZ,                       -- When GST data was fetched

    -- Completeness
    completeness_score  FLOAT DEFAULT 0.0,

    -- Timestamps
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_cases_user_id ON cases(user_id);
CREATE INDEX idx_cases_case_id ON cases(case_id);
CREATE INDEX idx_cases_status ON cases(status);

-- ─── DOCUMENTS ────────────────────────────────────────────────
CREATE TABLE documents (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    case_id         UUID NOT NULL REFERENCES cases(id) ON DELETE CASCADE,

    -- File info
    original_filename   VARCHAR(512),
    storage_key         VARCHAR(512) NOT NULL,       -- S3 key or local path
    file_size_bytes     BIGINT,
    mime_type           VARCHAR(100),
    file_hash           VARCHAR(64),                  -- SHA-256 for dedup

    -- Classification
    doc_type            VARCHAR(30) DEFAULT 'unknown',
    classification_confidence FLOAT DEFAULT 0.0,
    status              VARCHAR(20) DEFAULT 'uploaded',

    -- OCR
    ocr_text            TEXT,
    ocr_confidence      FLOAT,
    page_count          INTEGER,

    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_documents_case_id ON documents(case_id);
CREATE INDEX idx_documents_doc_type ON documents(doc_type);
CREATE INDEX idx_documents_file_hash ON documents(file_hash);

-- ─── EXTRACTED FIELDS ─────────────────────────────────────────
-- Key-value pairs extracted from each document
CREATE TABLE extracted_fields (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    document_id     UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    case_id         UUID NOT NULL REFERENCES cases(id) ON DELETE CASCADE,

    field_name      VARCHAR(100) NOT NULL,           -- e.g., "pan_number", "gstin"
    field_value     TEXT,
    confidence      FLOAT DEFAULT 0.0,
    source          VARCHAR(20) DEFAULT 'extraction', -- extraction, manual, computed

    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_extracted_fields_case_id ON extracted_fields(case_id);
CREATE INDEX idx_extracted_fields_document_id ON extracted_fields(document_id);

-- ─── BORROWER FEATURE VECTOR ──────────────────────────────────
-- One row per case - the assembled feature vector
CREATE TABLE borrower_features (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    case_id         UUID UNIQUE NOT NULL REFERENCES cases(id) ON DELETE CASCADE,

    -- Identity
    full_name           VARCHAR(255),
    pan_number          VARCHAR(10),
    aadhaar_number      VARCHAR(12),
    dob                 DATE,

    -- Business
    entity_type         VARCHAR(20),
    business_vintage_years FLOAT,
    gstin               VARCHAR(15),
    industry_type       VARCHAR(100),
    pincode             VARCHAR(10),

    -- Financial
    annual_turnover     FLOAT,
    avg_monthly_balance FLOAT,
    monthly_credit_avg  FLOAT,
    monthly_turnover    FLOAT,                           -- Average monthly credits (same as monthly_credit_avg)
    emi_outflow_monthly FLOAT,
    bounce_count_12m    INTEGER,
    cash_deposit_ratio  FLOAT,
    itr_total_income    FLOAT,

    -- Credit
    cibil_score         INTEGER,
    active_loan_count   INTEGER,
    overdue_count       INTEGER,
    enquiry_count_6m    INTEGER,

    -- Meta
    feature_completeness FLOAT DEFAULT 0.0,          -- % of fields populated
    created_at          TIMESTAMPTZ DEFAULT NOW(),
    updated_at          TIMESTAMPTZ DEFAULT NOW()
);

-- ─── LENDER RULES (Knowledge Base 3A) ────────────────────────
CREATE TABLE lenders (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    lender_name     VARCHAR(255) NOT NULL,
    lender_code     VARCHAR(20) UNIQUE,
    is_active       BOOLEAN DEFAULT TRUE,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE lender_products (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    lender_id       UUID NOT NULL REFERENCES lenders(id),
    product_name    VARCHAR(255) NOT NULL,           -- BL, STBL, HTBL, MTBL, SBL, PL, OD, LAP, Digital, Direct
    program_type    VARCHAR(10),                      -- banking, income, hybrid

    -- Hard filters (from Lender Policy CSV)
    min_vintage_years       FLOAT,                    -- "Min. Vintage" column
    min_cibil_score         INTEGER,                  -- "Min. Score" column
    min_turnover_annual     FLOAT,                    -- "Min. Turnover" in Lakhs
    max_ticket_size         FLOAT,                    -- "Max Ticket size" in Lakhs
    min_abb                 FLOAT,                    -- "ABB" - Avg Bank Balance minimum
    abb_to_emi_ratio        VARCHAR(100),             -- ABB-to-EMI ratio rule text
    eligible_entity_types   JSONB DEFAULT '[]',       -- "Entity" column parsed
    age_min                 INTEGER,                  -- "Age" range - min
    age_max                 INTEGER,                  -- "Age" range - max
    minimum_turnover_alt    FLOAT,                    -- "Minimum Turnover" (alt column) in Lakhs

    -- DPD (Days Past Due) rules
    no_30plus_dpd_months    INTEGER,                  -- "No 30+" - months lookback
    no_60plus_dpd_months    INTEGER,                  -- "60+" - months lookback
    no_90plus_dpd_months    INTEGER,                  -- "90+" - months lookback
    max_enquiries_rule      VARCHAR(255),             -- "Enquiries" rule text
    max_overdue_amount      FLOAT,                    -- "No Overdues" threshold
    emi_bounce_rule         VARCHAR(255),             -- "EMI bounce" rule text
    bureau_check_detail     TEXT,                     -- "Bureau Check" detailed rules

    -- Banking requirements
    banking_months_required INTEGER,                  -- "Banking Statement" months
    bank_source_type        VARCHAR(50),              -- "Bank Source" - AA, PDF, Scorme etc.
    ownership_proof_required BOOLEAN DEFAULT FALSE,   -- "Ownership Proof"
    ownership_proof_detail  VARCHAR(255),
    gst_required            BOOLEAN DEFAULT FALSE,    -- "GST" requirement
    gst_detail              VARCHAR(255),

    -- Verification requirements
    tele_pd_required        BOOLEAN DEFAULT FALSE,
    video_kyc_required      BOOLEAN DEFAULT FALSE,
    fi_required             BOOLEAN DEFAULT FALSE,    -- Field Investigation
    fi_detail               VARCHAR(255),
    kyc_documents           VARCHAR(512),             -- "KYC Doc" - PAN, Aadhaar, Udyam etc.

    -- Tenure
    tenor_min_months        INTEGER,                  -- "Tenor Min"
    tenor_max_months        INTEGER,                  -- "Tenor Max"

    -- Disbursement track record
    disb_till_date          FLOAT,                    -- in Crores

    -- Legacy fields
    max_foir                FLOAT,
    eligible_industries     JSONB DEFAULT '[]',
    excluded_industries     JSONB DEFAULT '[]',
    min_ticket_size         FLOAT,
    required_documents      JSONB DEFAULT '[]',
    interest_rate_range     VARCHAR(50),
    expected_tat_days       INTEGER,
    processing_fee_pct      FLOAT,
    usps                    TEXT,

    -- Version tracking
    source_file             VARCHAR(512),
    version                 INTEGER DEFAULT 1,
    is_active               BOOLEAN DEFAULT TRUE,
    policy_available        BOOLEAN DEFAULT TRUE,     -- some lenders marked "Policy not available"
    created_at              TIMESTAMPTZ DEFAULT NOW(),
    updated_at              TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_lender_products_lender_id ON lender_products(lender_id);
CREATE INDEX idx_lender_products_program_type ON lender_products(program_type);

-- ─── PINCODE SERVICEABILITY (from Pincode list Lender Wise.csv) ─
-- Each row = one pincode, linked to a lender
CREATE TABLE lender_pincodes (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    lender_id       UUID NOT NULL REFERENCES lenders(id),
    lender_column_name VARCHAR(50) NOT NULL,         -- column header from CSV: GODREJ, BAJAJ, etc.
    pincode         VARCHAR(10) NOT NULL,

    UNIQUE(lender_id, pincode)
);

CREATE INDEX idx_lender_pincodes_pincode ON lender_pincodes(pincode);
CREATE INDEX idx_lender_pincodes_lender_id ON lender_pincodes(lender_id);

-- ─── LENDER BRANCHES (optional enrichment) ────────────────────
CREATE TABLE lender_branches (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    lender_id       UUID NOT NULL REFERENCES lenders(id),
    branch_name     VARCHAR(255),
    city            VARCHAR(100),
    state           VARCHAR(100),
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- ─── LENDER RMs / SPOCs ───────────────────────────────────────
CREATE TABLE lender_rms (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    lender_id       UUID NOT NULL REFERENCES lenders(id),
    branch_id       UUID REFERENCES lender_branches(id),
    product_type    VARCHAR(20),                      -- BL, PL, SBL, LAP etc.
    rm_name         VARCHAR(255),
    phone           VARCHAR(20),
    email           VARCHAR(255),
    designation     VARCHAR(100),
    is_primary      BOOLEAN DEFAULT TRUE,             -- primary vs secondary SPOC
    is_active       BOOLEAN DEFAULT TRUE,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- ─── ELIGIBILITY RESULTS ──────────────────────────────────────
CREATE TABLE eligibility_results (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    case_id         UUID NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
    lender_product_id UUID NOT NULL REFERENCES lender_products(id),

    -- Results
    hard_filter_status  VARCHAR(10) NOT NULL,         -- pass / fail
    hard_filter_details JSONB DEFAULT '{}',           -- which filters failed
    eligibility_score   FLOAT,                        -- 0-100
    approval_probability VARCHAR(10),                 -- high, medium, low
    expected_ticket_min  FLOAT,
    expected_ticket_max  FLOAT,
    confidence          FLOAT,                        -- 0-1 data completeness
    missing_for_improvement JSONB DEFAULT '[]',
    rank                INTEGER,

    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_eligibility_case_id ON eligibility_results(case_id);

-- ─── CASE REPORTS ─────────────────────────────────────────────
CREATE TABLE case_reports (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    case_id         UUID NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
    report_type     VARCHAR(20) DEFAULT 'full',       -- full, summary, whatsapp
    storage_key     VARCHAR(512),                      -- S3 key or local path
    report_data     JSONB,                             -- structured report data
    generated_at    TIMESTAMPTZ DEFAULT NOW()
);

-- ─── CHATBOT QUERIES LOG ──────────────────────────────────────
CREATE TABLE copilot_queries (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id         UUID REFERENCES users(id),
    query_text      TEXT NOT NULL,
    response_text   TEXT,
    sources_used    JSONB DEFAULT '[]',
    response_time_ms INTEGER,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_copilot_queries_user_id ON copilot_queries(user_id);

-- ─── QUICK SCANS ─────────────────────────────────────────────
CREATE TABLE quick_scans (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    loan_type       VARCHAR(10) NOT NULL,            -- BL, PL, HL, LAP
    pincode         VARCHAR(10),
    scan_data       JSONB NOT NULL,                  -- request + response snapshot
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_quick_scans_user_id ON quick_scans(user_id);
CREATE INDEX idx_quick_scans_created_at ON quick_scans(created_at);

-- ─── LEAD CRM ────────────────────────────────────────────────
CREATE TABLE leads (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    assigned_to     UUID REFERENCES users(id),
    customer_name   VARCHAR(255),
    phone           VARCHAR(20),
    email           VARCHAR(255),
    loan_type_interest VARCHAR(20),                  -- BL, PL, HL, LAP, UNKNOWN
    loan_amount_approx FLOAT,
    city            VARCHAR(100),
    pincode         VARCHAR(10),
    source          VARCHAR(20),                     -- call, whatsapp, referral, etc.
    stage           VARCHAR(30) DEFAULT 'new',
    case_id         UUID REFERENCES cases(id),
    next_followup_date DATE,
    last_activity_at TIMESTAMPTZ DEFAULT NOW(),
    created_by      UUID REFERENCES users(id),
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_leads_assigned_to ON leads(assigned_to);
CREATE INDEX idx_leads_stage ON leads(stage);
CREATE INDEX idx_leads_case_id ON leads(case_id);

CREATE TABLE lead_activities (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    lead_id         UUID NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
    user_id         UUID REFERENCES users(id),
    activity_type   VARCHAR(30),                     -- call, whatsapp, email, note, stage_change
    notes           TEXT,
    call_outcome    VARCHAR(30),
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_lead_activities_lead_id ON lead_activities(lead_id);

-- ─── SUBMISSION TRACKER ──────────────────────────────────────
CREATE TABLE lender_submissions (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    case_id         UUID NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
    lender_name     VARCHAR(255) NOT NULL,
    product_type    VARCHAR(20),
    stage           VARCHAR(30) DEFAULT 'submitted',
    submitted_date  DATE,
    sanctioned_amount FLOAT,
    disbursed_amount FLOAT,
    disbursement_date DATE,
    rejection_reason VARCHAR(255),
    notes           TEXT,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_lender_submissions_case_id ON lender_submissions(case_id);
CREATE INDEX idx_lender_submissions_stage ON lender_submissions(stage);

CREATE TABLE submission_queries (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    submission_id   UUID NOT NULL REFERENCES lender_submissions(id) ON DELETE CASCADE,
    query_text      TEXT,
    response_text   TEXT,
    raised_date     DATE,
    resolved_date   DATE,
    status          VARCHAR(20) DEFAULT 'open',
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_submission_queries_submission_id ON submission_queries(submission_id);

-- ─── COMMISSION TRACKING ─────────────────────────────────────
CREATE TABLE dsa_commission_rates (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    lender_name     VARCHAR(255) NOT NULL,
    loan_type       VARCHAR(20) NOT NULL,
    commission_pct  FLOAT NOT NULL,
    notes           VARCHAR(255),
    updated_at      TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(user_id, lender_name, loan_type)
);

CREATE INDEX idx_commission_rates_user_id ON dsa_commission_rates(user_id);

CREATE TABLE commission_payouts (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    case_id         UUID NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
    user_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    lender_name     VARCHAR(255),
    disbursed_amount FLOAT,
    commission_pct  FLOAT,
    commission_amount FLOAT,
    disbursement_date DATE,
    expected_payout_date DATE,
    actual_payout_date DATE,
    payout_status   VARCHAR(20) DEFAULT 'pending',
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_commission_payouts_case_id ON commission_payouts(case_id);
CREATE INDEX idx_commission_payouts_user_id ON commission_payouts(user_id);
