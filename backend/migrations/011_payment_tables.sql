-- Migration 011: Payment integration tables
-- Supports Telegram-native (YooKassa/Stars) and external-link (Stripe) providers.
-- DB is the single source of truth for access; providers only trigger updates.

-- Payment settings per channel binding
CREATE TABLE IF NOT EXISTS payment_settings (
    setting_id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    binding_id          UUID NOT NULL UNIQUE REFERENCES channel_bindings(binding_id) ON DELETE CASCADE,
    enabled             BOOLEAN NOT NULL DEFAULT FALSE,
    provider            VARCHAR(50) NOT NULL DEFAULT 'telegram_native',
    -- telegram_native | external_link
    free_messages       INT NOT NULL DEFAULT 10,
    grace_messages      INT NOT NULL DEFAULT 3,
    sandbox_mode        BOOLEAN NOT NULL DEFAULT FALSE,
    provider_secret_name TEXT,                     -- key in secrets table (not the token itself)
    sandbox_secret_name  TEXT,                     -- key in secrets table for test token
    payment_title       VARCHAR(200) DEFAULT 'Подписка',
    payment_description TEXT DEFAULT 'Доступ к чат-боту',
    invoice_resend_hours INT NOT NULL DEFAULT 24,
    support_contact      TEXT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Plans available for a binding (e.g. "1 month / 30 msgs / 299 RUB")
CREATE TABLE IF NOT EXISTS payment_plans (
    plan_id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    binding_id      UUID NOT NULL REFERENCES channel_bindings(binding_id) ON DELETE CASCADE,
    name            VARCHAR(200) NOT NULL,
    duration_days   INT NOT NULL,
    price_amount    BIGINT NOT NULL,       -- smallest currency unit (kopeks / cents / Stars)
    currency        VARCHAR(10) NOT NULL DEFAULT 'RUB',
    messages_limit  INT,                   -- NULL = unlimited within period
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    sort_order      INT NOT NULL DEFAULT 0,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_payment_plans_binding ON payment_plans(binding_id) WHERE is_active;

-- Per-user subscription state (the access source of truth)
CREATE TABLE IF NOT EXISTS user_subscriptions (
    sub_id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    binding_id          UUID NOT NULL REFERENCES channel_bindings(binding_id) ON DELETE CASCADE,
    external_user_id    TEXT NOT NULL,
    status              VARCHAR(20) NOT NULL DEFAULT 'free',
    -- free | active | expired | manual
    plan_id             UUID REFERENCES payment_plans(plan_id),
    expires_at          TIMESTAMPTZ,
    messages_used       INT NOT NULL DEFAULT 0,
    messages_limit      INT,               -- snapshot from plan at activation time
    period_started_at   TIMESTAMPTZ,
    invoice_sent_at     TIMESTAMPTZ,       -- last time invoice was sent (throttle)
    grace_messages_used INT NOT NULL DEFAULT 0,
    manual_override     BOOLEAN NOT NULL DEFAULT FALSE,
    notes               TEXT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(binding_id, external_user_id)
);

CREATE INDEX IF NOT EXISTS idx_user_subs_lookup ON user_subscriptions(binding_id, external_user_id);
CREATE INDEX IF NOT EXISTS idx_user_subs_expires ON user_subscriptions(expires_at) WHERE status = 'active';

-- Payment transaction history (idempotent via UNIQUE provider_charge_id)
CREATE TABLE IF NOT EXISTS payment_transactions (
    txn_id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    sub_id              UUID NOT NULL REFERENCES user_subscriptions(sub_id),
    binding_id          UUID NOT NULL,
    external_user_id    TEXT NOT NULL,
    provider            VARCHAR(50) NOT NULL,
    -- telegram_native | external_link
    provider_charge_id  TEXT UNIQUE,       -- NULL for pending; set on completion
    plan_id             UUID REFERENCES payment_plans(plan_id),
    amount              BIGINT,
    currency            VARCHAR(10),
    status              VARCHAR(20) NOT NULL DEFAULT 'pending',
    -- pending | completed | failed | refunded
    invoice_payload     TEXT,              -- signed payload string
    raw_payload         JSONB,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_txn_sub ON payment_transactions(sub_id);
CREATE INDEX IF NOT EXISTS idx_txn_binding ON payment_transactions(binding_id, created_at DESC);
