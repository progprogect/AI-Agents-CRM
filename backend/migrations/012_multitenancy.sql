-- Multitenancy: organizations, members, LLM keys + organization_id on all owned tables
-- Run with: psql $DATABASE_PUBLIC_URL -f migrations/012_multitenancy.sql

-- ─── New tables ──────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS organizations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(255) NOT NULL,
    slug VARCHAR(100) UNIQUE NOT NULL,
    is_active BOOLEAN DEFAULT TRUE,
    created_by VARCHAR(255) NOT NULL,  -- email of the platform admin who created it
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS organization_members (
    organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    email VARCHAR(255) NOT NULL,
    role VARCHAR(20) NOT NULL DEFAULT 'member',  -- owner | admin | member
    invited_by VARCHAR(255),
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (organization_id, email)
);

CREATE INDEX IF NOT EXISTS idx_org_members_email ON organization_members(email);
CREATE INDEX IF NOT EXISTS idx_org_members_org ON organization_members(organization_id);

CREATE TABLE IF NOT EXISTS organization_llm_keys (
    organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    provider VARCHAR(20) NOT NULL,  -- openai | google
    encrypted_key TEXT NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (organization_id, provider)
);

-- ─── Add organization_id to owned tables ─────────────────────────────────────

ALTER TABLE agents ADD COLUMN IF NOT EXISTS organization_id UUID REFERENCES organizations(id);
ALTER TABLE channel_bindings ADD COLUMN IF NOT EXISTS organization_id UUID REFERENCES organizations(id);
ALTER TABLE rag_folders ADD COLUMN IF NOT EXISTS organization_id UUID REFERENCES organizations(id);
ALTER TABLE rag_documents ADD COLUMN IF NOT EXISTS organization_id UUID REFERENCES organizations(id);
ALTER TABLE notification_configs ADD COLUMN IF NOT EXISTS organization_id UUID REFERENCES organizations(id);
ALTER TABLE audit_logs ADD COLUMN IF NOT EXISTS organization_id UUID;

-- ─── Indexes ─────────────────────────────────────────────────────────────────

CREATE INDEX IF NOT EXISTS idx_agents_org ON agents(organization_id);
CREATE INDEX IF NOT EXISTS idx_channel_bindings_org ON channel_bindings(organization_id);
CREATE INDEX IF NOT EXISTS idx_rag_folders_org ON rag_folders(organization_id);
CREATE INDEX IF NOT EXISTS idx_rag_documents_org ON rag_documents(organization_id);
CREATE INDEX IF NOT EXISTS idx_notification_configs_org ON notification_configs(organization_id);
CREATE INDEX IF NOT EXISTS idx_audit_logs_org ON audit_logs(organization_id);

-- ─── Backfill: create the default organization ───────────────────────────────
-- All existing data (agents, bindings, etc.) is assigned to this org.
-- All existing admin_users get owner role in this org.
-- Super admins from env are handled at application level (they are platform admins).

DO $$
DECLARE
    default_org_id UUID := '00000000-0000-0000-0000-000000000001';
    default_created_by TEXT := 'platform-migration';
BEGIN
    -- Create the default organization if it doesn't exist
    INSERT INTO organizations (id, name, slug, is_active, created_by, created_at)
    VALUES (
        default_org_id,
        'Default Organization',
        'default',
        TRUE,
        default_created_by,
        NOW()
    )
    ON CONFLICT (id) DO NOTHING;

    -- Assign all existing agents to default org
    UPDATE agents SET organization_id = default_org_id WHERE organization_id IS NULL;

    -- Assign all existing channel_bindings
    UPDATE channel_bindings SET organization_id = default_org_id WHERE organization_id IS NULL;

    -- Assign all existing rag_folders
    UPDATE rag_folders SET organization_id = default_org_id WHERE organization_id IS NULL;

    -- Assign all existing rag_documents
    UPDATE rag_documents SET organization_id = default_org_id WHERE organization_id IS NULL;

    -- Assign all existing notification_configs
    UPDATE notification_configs SET organization_id = default_org_id WHERE organization_id IS NULL;

    -- Assign all existing audit_logs
    UPDATE audit_logs SET organization_id = default_org_id WHERE organization_id IS NULL;

    -- Migrate existing admin_users → organization_members with owner role
    INSERT INTO organization_members (organization_id, email, role, invited_by, is_active, created_at)
    SELECT
        default_org_id,
        email,
        'owner',
        created_by,
        is_active,
        created_at
    FROM admin_users
    ON CONFLICT (organization_id, email) DO NOTHING;

END $$;
