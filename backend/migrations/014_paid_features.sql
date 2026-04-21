-- Migration 014: Paid features — per-feature payment gates
-- Adds feature gates (voice/images), custom paywall messages per feature,
-- a free-message-limit toggle, and per-user feature access overrides.

ALTER TABLE payment_settings
    ADD COLUMN IF NOT EXISTS feature_gates            JSONB NOT NULL DEFAULT '{"voice": false, "images": false}',
    ADD COLUMN IF NOT EXISTS paywall_messages          JSONB NOT NULL DEFAULT '{}',
    ADD COLUMN IF NOT EXISTS free_message_limit_enabled BOOLEAN NOT NULL DEFAULT false;

ALTER TABLE user_subscriptions
    ADD COLUMN IF NOT EXISTS feature_overrides JSONB NULL;

COMMENT ON COLUMN payment_settings.feature_gates IS
    'Feature flags that require a paid subscription, e.g. {"voice": true, "images": false}';
COMMENT ON COLUMN payment_settings.paywall_messages IS
    'Custom paywall text per feature, e.g. {"voice": "Voice requires subscription.", "images": "Image analysis requires subscription.", "limit_reached": "Free limit reached."}';
COMMENT ON COLUMN payment_settings.free_message_limit_enabled IS
    'When true the free_messages counter is enforced; when false all text messages are free regardless of count';
COMMENT ON COLUMN user_subscriptions.feature_overrides IS
    'Per-user feature access overrides (null = use global setting), e.g. {"voice": true, "images": false}';
