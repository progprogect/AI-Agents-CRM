-- Migration 015: Per-user Telegram reminders (vet care etc.)
-- Scoped to (agent_id, binding_id, external_user_id); independent of conversation /restart.

CREATE TABLE IF NOT EXISTS user_reminders (
    reminder_id      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_id         VARCHAR(255) NOT NULL REFERENCES agents(agent_id) ON DELETE CASCADE,
    binding_id       VARCHAR(255) NOT NULL REFERENCES channel_bindings(binding_id) ON DELETE CASCADE,
    external_user_id TEXT NOT NULL,
    category         VARCHAR(32) NOT NULL,
    -- vaccination | treatment | food_order | other
    schedule_kind    VARCHAR(16) NOT NULL,
    -- once | recurring
    schedule_spec    JSONB NOT NULL DEFAULT '{}'::jsonb,
    user_note        TEXT NOT NULL DEFAULT '',
    status           VARCHAR(16) NOT NULL DEFAULT 'active',
    -- active | cancelled | completed
    next_fire_at     TIMESTAMPTZ NOT NULL,
    last_fired_at    TIMESTAMPTZ NULL,
    recurring_fires_done INT NOT NULL DEFAULT 0,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    cancelled_at     TIMESTAMPTZ NULL
);

CREATE INDEX IF NOT EXISTS idx_user_reminders_user_active
    ON user_reminders(binding_id, external_user_id, status);
CREATE INDEX IF NOT EXISTS idx_user_reminders_next_fire
    ON user_reminders(next_fire_at)
    WHERE status = 'active';
