-- Migration 013: add completion_message column to questionnaire_templates
ALTER TABLE questionnaire_templates
    ADD COLUMN IF NOT EXISTS completion_message TEXT NOT NULL DEFAULT '';
