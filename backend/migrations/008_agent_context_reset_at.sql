-- Agent context watermark: messages before this instant are not passed to LLM/escalation
ALTER TABLE conversations ADD COLUMN IF NOT EXISTS agent_context_reset_at TIMESTAMPTZ NULL;
