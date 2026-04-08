-- RAG chunk storage for semantic search with bounded context
-- Run with: psql $DATABASE_PUBLIC_URL -f migrations/009_rag_chunks.sql

CREATE TABLE IF NOT EXISTS rag_chunks (
    agent_id VARCHAR(255) NOT NULL,
    document_id VARCHAR(255) NOT NULL,
    chunk_index INTEGER NOT NULL,
    content TEXT NOT NULL,
    embedding JSONB NOT NULL,
    metadata JSONB DEFAULT '{}',
    PRIMARY KEY (agent_id, document_id, chunk_index),
    CONSTRAINT fk_rag_chunks_document
        FOREIGN KEY (agent_id, document_id)
        REFERENCES rag_documents(agent_id, document_id)
        ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_rag_chunks_agent_id ON rag_chunks(agent_id);
