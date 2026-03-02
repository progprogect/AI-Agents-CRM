-- CRM Stages migration
-- Adds configurable CRM pipeline stages to replace hardcoded marketing_status

CREATE TABLE IF NOT EXISTS crm_stages (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name        VARCHAR(100) NOT NULL,
    color       VARCHAR(7) NOT NULL DEFAULT '#BEBAB7',
    position    INTEGER NOT NULL DEFAULT 0,
    is_default  BOOLEAN NOT NULL DEFAULT FALSE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

INSERT INTO crm_stages (name, color, position, is_default) VALUES
    ('New',         '#3B82F6', 0, TRUE),
    ('Booked',      '#22C55E', 1, TRUE),
    ('No Response', '#9A9590', 2, TRUE),
    ('Rejected',    '#EF4444', 3, TRUE)
ON CONFLICT DO NOTHING;

ALTER TABLE conversations ADD COLUMN IF NOT EXISTS crm_stage_id UUID REFERENCES crm_stages(id);

UPDATE conversations c SET crm_stage_id = s.id
FROM crm_stages s
WHERE c.crm_stage_id IS NULL
  AND (
    (c.marketing_status = 'NEW'         AND s.name = 'New')
 OR (c.marketing_status = 'BOOKED'      AND s.name = 'Booked')
 OR (c.marketing_status = 'NO_RESPONSE' AND s.name = 'No Response')
 OR (c.marketing_status = 'REJECTED'    AND s.name = 'Rejected')
  );

UPDATE conversations
SET crm_stage_id = (SELECT id FROM crm_stages WHERE name = 'New' LIMIT 1)
WHERE crm_stage_id IS NULL;

CREATE INDEX IF NOT EXISTS idx_conversations_crm_stage_id ON conversations(crm_stage_id);
