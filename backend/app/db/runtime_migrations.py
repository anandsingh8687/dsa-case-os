"""Idempotent runtime migrations for feature rollouts.

This project historically used `create_all` + schema bootstrap instead of Alembic.
To keep production upgrades safe, this module applies additive migrations with
`IF NOT EXISTS` semantics on startup.
"""

from __future__ import annotations

import logging

import asyncpg

logger = logging.getLogger(__name__)


RUNTIME_MIGRATIONS: list[str] = [
    # Extensions
    'CREATE EXTENSION IF NOT EXISTS "pgcrypto";',
    'CREATE EXTENSION IF NOT EXISTS "uuid-ossp";',
    """
    DO $$
    BEGIN
        IF EXISTS (SELECT 1 FROM pg_available_extensions WHERE name = 'vector') THEN
            CREATE EXTENSION IF NOT EXISTS "vector";
        END IF;
    END $$;
    """,
    # Organizations and subscriptions
    """
    CREATE TABLE IF NOT EXISTS organizations (
        id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
        name VARCHAR(255) NOT NULL,
        slug VARCHAR(255) UNIQUE NOT NULL,
        is_active BOOLEAN DEFAULT TRUE,
        created_by UUID,
        created_at TIMESTAMPTZ DEFAULT NOW(),
        updated_at TIMESTAMPTZ DEFAULT NOW()
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS subscription_plans (
        id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
        code VARCHAR(30) UNIQUE NOT NULL,
        name VARCHAR(100) NOT NULL,
        monthly_price_inr INTEGER NOT NULL DEFAULT 0,
        monthly_case_limit INTEGER NOT NULL DEFAULT 20,
        monthly_bank_analysis_limit INTEGER NOT NULL DEFAULT 20,
        features_json TEXT,
        is_active BOOLEAN DEFAULT TRUE,
        created_at TIMESTAMPTZ DEFAULT NOW()
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS organization_subscriptions (
        id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
        organization_id UUID REFERENCES organizations(id) ON DELETE CASCADE,
        plan_id UUID REFERENCES subscription_plans(id),
        status VARCHAR(20) DEFAULT 'active',
        starts_at TIMESTAMPTZ DEFAULT NOW(),
        ends_at TIMESTAMPTZ,
        cases_used INTEGER DEFAULT 0,
        bank_analyses_used INTEGER DEFAULT 0,
        razorpay_subscription_id VARCHAR(100),
        created_at TIMESTAMPTZ DEFAULT NOW(),
        updated_at TIMESTAMPTZ DEFAULT NOW()
    );
    """,
    # Ensure server-side UUID defaults exist even on metadata-created tables.
    """
    DO $$
    BEGIN
      BEGIN
        EXECUTE 'ALTER TABLE organizations ALTER COLUMN id SET DEFAULT gen_random_uuid()';
      EXCEPTION WHEN undefined_function THEN
        EXECUTE 'ALTER TABLE organizations ALTER COLUMN id SET DEFAULT uuid_generate_v4()';
      END;
    END $$;
    """,
    "ALTER TABLE organizations ALTER COLUMN is_active SET DEFAULT TRUE;",
    """
    DO $$
    BEGIN
      BEGIN
        EXECUTE 'ALTER TABLE subscription_plans ALTER COLUMN id SET DEFAULT gen_random_uuid()';
      EXCEPTION WHEN undefined_function THEN
        EXECUTE 'ALTER TABLE subscription_plans ALTER COLUMN id SET DEFAULT uuid_generate_v4()';
      END;
    END $$;
    """,
    "ALTER TABLE subscription_plans ALTER COLUMN is_active SET DEFAULT TRUE;",
    """
    DO $$
    BEGIN
      BEGIN
        EXECUTE 'ALTER TABLE organization_subscriptions ALTER COLUMN id SET DEFAULT gen_random_uuid()';
      EXCEPTION WHEN undefined_function THEN
        EXECUTE 'ALTER TABLE organization_subscriptions ALTER COLUMN id SET DEFAULT uuid_generate_v4()';
      END;
    END $$;
    """,
    # User/tenant columns
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS organization_id UUID;",
    "CREATE INDEX IF NOT EXISTS idx_users_organization_id ON users(organization_id);",
    "ALTER TABLE users ALTER COLUMN role SET DEFAULT 'agent';",
    # Case/document tenant columns
    "ALTER TABLE cases ADD COLUMN IF NOT EXISTS organization_id UUID;",
    "CREATE INDEX IF NOT EXISTS idx_cases_organization_id ON cases(organization_id);",
    "ALTER TABLE cases ADD COLUMN IF NOT EXISTS business_address TEXT;",
    "ALTER TABLE documents ADD COLUMN IF NOT EXISTS organization_id UUID;",
    "CREATE INDEX IF NOT EXISTS idx_documents_organization_id ON documents(organization_id);",
    "ALTER TABLE document_processing_jobs ADD COLUMN IF NOT EXISTS organization_id UUID;",
    "CREATE INDEX IF NOT EXISTS idx_doc_jobs_organization_id ON document_processing_jobs(organization_id);",
    "ALTER TABLE extracted_fields ADD COLUMN IF NOT EXISTS organization_id UUID;",
    "CREATE INDEX IF NOT EXISTS idx_extracted_fields_organization_id ON extracted_fields(organization_id);",
    "ALTER TABLE borrower_features ADD COLUMN IF NOT EXISTS organization_id UUID;",
    "CREATE INDEX IF NOT EXISTS idx_borrower_features_organization_id ON borrower_features(organization_id);",
    "ALTER TABLE quick_scans ADD COLUMN IF NOT EXISTS organization_id UUID;",
    "CREATE INDEX IF NOT EXISTS idx_quick_scans_org_id ON quick_scans(organization_id);",
    "ALTER TABLE copilot_queries ADD COLUMN IF NOT EXISTS organization_id UUID;",
    "CREATE INDEX IF NOT EXISTS idx_copilot_queries_org_id ON copilot_queries(organization_id);",
    "ALTER TABLE case_reports ADD COLUMN IF NOT EXISTS organization_id UUID;",
    "CREATE INDEX IF NOT EXISTS idx_case_reports_org_id ON case_reports(organization_id);",
    "ALTER TABLE eligibility_results ADD COLUMN IF NOT EXISTS organization_id UUID;",
    "CREATE INDEX IF NOT EXISTS idx_eligibility_org_id ON eligibility_results(organization_id);",
    "ALTER TABLE leads ADD COLUMN IF NOT EXISTS organization_id UUID;",
    "CREATE INDEX IF NOT EXISTS idx_leads_org_id ON leads(organization_id);",
    "ALTER TABLE lender_submissions ADD COLUMN IF NOT EXISTS organization_id UUID;",
    "CREATE INDEX IF NOT EXISTS idx_lender_submissions_org_id ON lender_submissions(organization_id);",
    "ALTER TABLE submission_queries ADD COLUMN IF NOT EXISTS organization_id UUID;",
    "CREATE INDEX IF NOT EXISTS idx_submission_queries_org_id ON submission_queries(organization_id);",
    "ALTER TABLE dsa_commission_rates ADD COLUMN IF NOT EXISTS organization_id UUID;",
    "CREATE INDEX IF NOT EXISTS idx_dsa_commission_rates_org_id ON dsa_commission_rates(organization_id);",
    "ALTER TABLE commission_payouts ADD COLUMN IF NOT EXISTS organization_id UUID;",
    "CREATE INDEX IF NOT EXISTS idx_commission_payouts_org_id ON commission_payouts(organization_id);",
    "ALTER TABLE lender_pincodes ADD COLUMN IF NOT EXISTS organization_id UUID;",
    "CREATE INDEX IF NOT EXISTS idx_lender_pincodes_org_id ON lender_pincodes(organization_id);",
    "ALTER TABLE lender_branches ADD COLUMN IF NOT EXISTS organization_id UUID;",
    "CREATE INDEX IF NOT EXISTS idx_lender_branches_org_id ON lender_branches(organization_id);",
    "ALTER TABLE lender_rms ADD COLUMN IF NOT EXISTS organization_id UUID;",
    "CREATE INDEX IF NOT EXISTS idx_lender_rms_org_id ON lender_rms(organization_id);",
    "ALTER TABLE lender_products ADD COLUMN IF NOT EXISTS organization_id UUID;",
    "CREATE INDEX IF NOT EXISTS idx_lender_products_org_id ON lender_products(organization_id);",
    "ALTER TABLE lenders ADD COLUMN IF NOT EXISTS organization_id UUID;",
    "CREATE INDEX IF NOT EXISTS idx_lenders_org_id ON lenders(organization_id);",
    # Subscription plan seed
    """
    INSERT INTO subscription_plans (code, name, monthly_price_inr, monthly_case_limit, monthly_bank_analysis_limit, features_json)
    VALUES
      ('free', 'Free', 0, 20, 20, '{"team":false,"insights":false}'),
      ('starter', 'Starter', 799, 100, 100, '{"team":true,"insights":false}'),
      ('pro', 'Pro', 1999, 500, 500, '{"team":true,"insights":true}')
    ON CONFLICT (code) DO NOTHING;
    """,
    # RAG documents (always create table; use pgvector column only when extension exists)
    """
    CREATE TABLE IF NOT EXISTS lender_documents (
        id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
        organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
        lender_name VARCHAR(255) NOT NULL,
        product_type VARCHAR(255) NOT NULL,
        section_title VARCHAR(255),
        chunk_text TEXT NOT NULL,
        embedding_json TEXT NOT NULL DEFAULT '[]',
        source_file VARCHAR(1024),
        last_updated TIMESTAMPTZ DEFAULT NOW(),
        created_at TIMESTAMPTZ DEFAULT NOW()
    );
    """,
    "ALTER TABLE lender_documents ADD COLUMN IF NOT EXISTS embedding_json TEXT NOT NULL DEFAULT '[]';",
    """
    DO $$
    BEGIN
      IF EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'vector') THEN
        ALTER TABLE lender_documents ADD COLUMN IF NOT EXISTS embedding VECTOR(384);
      END IF;
    END $$;
    """,
    """
    CREATE UNIQUE INDEX IF NOT EXISTS uq_lender_documents_dedupe
    ON lender_documents (organization_id, lender_name, product_type, COALESCE(section_title, ''), md5(chunk_text));
    """,
    "CREATE INDEX IF NOT EXISTS idx_lender_documents_org ON lender_documents(organization_id);",
    # Secure share links for oversized email collaboration payloads
    """
    CREATE TABLE IF NOT EXISTS case_share_links (
        id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
        case_id UUID NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
        organization_id UUID REFERENCES organizations(id) ON DELETE SET NULL,
        created_by_user_id UUID,
        token_hash VARCHAR(128) NOT NULL UNIQUE,
        expires_at TIMESTAMPTZ NOT NULL,
        max_downloads INTEGER NOT NULL DEFAULT 10,
        download_count INTEGER NOT NULL DEFAULT 0,
        is_active BOOLEAN NOT NULL DEFAULT TRUE,
        last_accessed_at TIMESTAMPTZ,
        created_at TIMESTAMPTZ DEFAULT NOW()
    );
    """,
    "CREATE INDEX IF NOT EXISTS idx_case_share_links_case_id ON case_share_links(case_id);",
    "CREATE INDEX IF NOT EXISTS idx_case_share_links_expires_at ON case_share_links(expires_at);",
]


POST_MIGRATION_DATA_FIXES: list[str] = [
    "UPDATE organizations SET is_active = TRUE WHERE is_active IS NULL;",
    "UPDATE subscription_plans SET is_active = TRUE WHERE is_active IS NULL;",
    # Create one organization per user where missing.
    """
    INSERT INTO organizations (name, slug, created_by)
    SELECT
      CONCAT(COALESCE(NULLIF(u.full_name, ''), SPLIT_PART(u.email, '@', 1)), ' Org') AS name,
      LOWER(REGEXP_REPLACE(
        CONCAT(COALESCE(NULLIF(SPLIT_PART(u.email, '@', 1), ''), 'org'), '-', SUBSTRING(u.id::text, 1, 8)),
        '[^a-z0-9\\-]+',
        '-',
        'g'
      )) AS slug,
      u.id
    FROM users u
    WHERE u.organization_id IS NULL
    ON CONFLICT (slug) DO NOTHING;
    """,
    """
    UPDATE users u
    SET organization_id = o.id
    FROM organizations o
    WHERE u.organization_id IS NULL AND o.created_by = u.id;
    """,
    """
    UPDATE users
    SET role = CASE
        WHEN role IN ('admin', 'super_admin', 'dsa_owner', 'agent') THEN role
        WHEN role = 'dsa' THEN 'dsa_owner'
        ELSE 'agent'
    END;
    """,
    """
    UPDATE cases c
    SET organization_id = u.organization_id
    FROM users u
    WHERE c.organization_id IS NULL AND c.user_id = u.id;
    """,
    """
    UPDATE documents d
    SET organization_id = c.organization_id
    FROM cases c
    WHERE d.organization_id IS NULL AND d.case_id = c.id;
    """,
    """
    UPDATE document_processing_jobs j
    SET organization_id = c.organization_id
    FROM cases c
    WHERE j.organization_id IS NULL AND j.case_id = c.id;
    """,
    """
    UPDATE extracted_fields ef
    SET organization_id = c.organization_id
    FROM cases c
    WHERE ef.organization_id IS NULL AND ef.case_id = c.id;
    """,
    """
    UPDATE borrower_features bf
    SET organization_id = c.organization_id
    FROM cases c
    WHERE bf.organization_id IS NULL AND bf.case_id = c.id;
    """,
]


async def apply_runtime_migrations(conn: asyncpg.Connection) -> None:
    """Apply additive migration statements safely."""
    for stmt in RUNTIME_MIGRATIONS:
        try:
            await conn.execute(stmt)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Runtime migration statement failed (continuing): %s", exc)

    for stmt in POST_MIGRATION_DATA_FIXES:
        try:
            await conn.execute(stmt)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Runtime data backfill statement failed (continuing): %s", exc)
