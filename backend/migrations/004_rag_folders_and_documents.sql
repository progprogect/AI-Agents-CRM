-- RAG folders and extended documents
-- Run with: psql $DATABASE_PUBLIC_URL -f migrations/004_rag_folders_and_documents.sql

-- rag_folders
CREATE TABLE IF NOT EXISTS rag_folders (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_id VARCHAR(255) NOT NULL,
    parent_id UUID REFERENCES rag_folders(id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(agent_id, parent_id, name)
);
CREATE INDEX IF NOT EXISTS idx_rag_folders_agent_parent ON rag_folders(agent_id, parent_id);

-- Extend rag_documents
ALTER TABLE rag_documents ADD COLUMN IF NOT EXISTS folder_id UUID REFERENCES rag_folders(id) ON DELETE SET NULL;
ALTER TABLE rag_documents ADD COLUMN IF NOT EXISTS file_type VARCHAR(50) DEFAULT 'text';
ALTER TABLE rag_documents ADD COLUMN IF NOT EXISTS file_url TEXT;
ALTER TABLE rag_documents ADD COLUMN IF NOT EXISTS original_filename VARCHAR(255);
ALTER TABLE rag_documents ADD COLUMN IF NOT EXISTS file_size BIGINT;
ALTER TABLE rag_documents ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT NOW();
ALTER TABLE rag_documents ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT NOW();
