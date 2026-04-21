-- Migration 012: Questionnaire feature
-- Per-agent template (one row per agent), append-only submissions and responses.
-- Each answer change creates a new row in questionnaire_responses so history is preserved.

-- Template: welcome message + ordered list of fields (JSONB).
CREATE TABLE IF NOT EXISTS questionnaire_templates (
    agent_id         VARCHAR(255) PRIMARY KEY REFERENCES agents(agent_id) ON DELETE CASCADE,
    welcome_message  TEXT NOT NULL DEFAULT '',
    fields           JSONB NOT NULL DEFAULT '[]'::jsonb,
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Submission: one per fill/edit session (in_progress | completed | cancelled).
CREATE TABLE IF NOT EXISTS questionnaire_submissions (
    submission_id    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_id         VARCHAR(255) NOT NULL REFERENCES agents(agent_id) ON DELETE CASCADE,
    external_user_id TEXT NOT NULL,
    channel          VARCHAR(50) NOT NULL DEFAULT 'telegram',
    -- Free-form id of the chat conversation at schedule time (matches
    -- conversations.conversation_id VARCHAR(255) shape from the initial schema).
    conversation_id  VARCHAR(255) NULL,
    status           VARCHAR(20) NOT NULL DEFAULT 'in_progress',
    -- in_progress | completed | cancelled
    source           VARCHAR(20) NOT NULL DEFAULT 'fill',
    -- fill | edit
    started_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at     TIMESTAMPTZ NULL,
    cancelled_at     TIMESTAMPTZ NULL
);

CREATE INDEX IF NOT EXISTS idx_q_submissions_user
    ON questionnaire_submissions(agent_id, external_user_id, started_at DESC);
CREATE INDEX IF NOT EXISTS idx_q_submissions_started
    ON questionnaire_submissions(agent_id, started_at DESC);

-- Append-only answers. One row per answer; the latest row per
-- (agent_id, external_user_id, field_key) is the "current" value.
CREATE TABLE IF NOT EXISTS questionnaire_responses (
    response_id      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    submission_id    UUID NOT NULL REFERENCES questionnaire_submissions(submission_id) ON DELETE CASCADE,
    agent_id         VARCHAR(255) NOT NULL REFERENCES agents(agent_id) ON DELETE CASCADE,
    external_user_id TEXT NOT NULL,
    field_key        VARCHAR(40) NOT NULL,
    value            TEXT NOT NULL,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_q_responses_latest
    ON questionnaire_responses(agent_id, external_user_id, field_key, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_q_responses_submission
    ON questionnaire_responses(submission_id, created_at ASC);
