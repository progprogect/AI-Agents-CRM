-- Rename doctor_display_name -> agent_display_name in agents.config JSONB
-- Run with: psql $DATABASE_URL -f migrations/003_doctor_to_agent_display_name.sql
UPDATE agents
SET config = jsonb_set(
  config #- '{profile,doctor_display_name}',
  '{profile,agent_display_name}',
  config->'profile'->'doctor_display_name'
)
WHERE config->'profile'->'doctor_display_name' IS NOT NULL;
