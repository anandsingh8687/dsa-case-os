"""Add multi-tenancy, subscriptions, and RAG pgvector tables.

Revision ID: 20260223_0001
Revises:
Create Date: 2026-02-23 00:00:00
"""

from alembic import op


revision = "20260223_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute('CREATE EXTENSION IF NOT EXISTS "pgcrypto";')
    op.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp";')
    op.execute(
        """
        DO $$
        BEGIN
          IF EXISTS (SELECT 1 FROM pg_available_extensions WHERE name = 'vector') THEN
            CREATE EXTENSION IF NOT EXISTS "vector";
          END IF;
        END $$;
        """
    )

    op.execute(
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
        """
    )
    op.execute(
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
        """
    )
    op.execute(
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
        """
    )

    op.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS organization_id UUID;")
    op.execute("ALTER TABLE users ALTER COLUMN role SET DEFAULT 'agent';")
    op.execute("CREATE INDEX IF NOT EXISTS idx_users_organization_id ON users(organization_id);")

    for table_name in [
        "cases",
        "documents",
        "document_processing_jobs",
        "extracted_fields",
        "borrower_features",
        "quick_scans",
        "copilot_queries",
        "case_reports",
        "eligibility_results",
        "leads",
        "lender_submissions",
        "submission_queries",
        "dsa_commission_rates",
        "commission_payouts",
        "lender_pincodes",
        "lender_branches",
        "lender_rms",
        "lender_products",
        "lenders",
    ]:
        op.execute(f"ALTER TABLE {table_name} ADD COLUMN IF NOT EXISTS organization_id UUID;")
        op.execute(f"CREATE INDEX IF NOT EXISTS idx_{table_name}_organization_id ON {table_name}(organization_id);")
    op.execute("ALTER TABLE cases ADD COLUMN IF NOT EXISTS business_address TEXT;")

    op.execute(
        """
        INSERT INTO subscription_plans (code, name, monthly_price_inr, monthly_case_limit, monthly_bank_analysis_limit, features_json)
        VALUES
          ('free', 'Free', 0, 20, 20, '{"team":false,"insights":false}'),
          ('starter', 'Starter', 799, 100, 100, '{"team":true,"insights":false}'),
          ('pro', 'Pro', 1999, 500, 500, '{"team":true,"insights":true}')
        ON CONFLICT (code) DO NOTHING;
        """
    )

    op.execute(
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
        """
    )
    op.execute(
        """
        DO $$
        BEGIN
          IF EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'vector') THEN
            ALTER TABLE lender_documents ADD COLUMN IF NOT EXISTS embedding VECTOR(384);
          END IF;
        END $$;
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_lender_documents_dedupe
        ON lender_documents (organization_id, lender_name, product_type, COALESCE(section_title, ''), md5(chunk_text));
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_lender_documents_org ON lender_documents(organization_id);")

    op.execute(
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
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_case_share_links_case_id ON case_share_links(case_id);")
    op.execute("CREATE INDEX IF NOT EXISTS idx_case_share_links_expires_at ON case_share_links(expires_at);")


def downgrade() -> None:
    # Non-destructive downgrade for production safety.
    pass
