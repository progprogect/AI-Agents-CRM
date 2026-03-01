/** Validation utilities for agent configuration. */

import type { AgentConfigFormData } from "./agentConfig";

export interface ValidationError {
  field: string;
  message: string;
}

/**
 * Validate agent configuration form data.
 */
export function validateAgentConfig(
  formData: Partial<AgentConfigFormData>
): ValidationError[] {
  const errors: ValidationError[] = [];

  // Basic Info validation
  // Agent ID is auto-generated, but validate format if present
  if (formData.agent_id && !/^[a-z0-9_]+$/.test(formData.agent_id)) {
    errors.push({
      field: "agent_id",
      message: "Agent ID must contain only lowercase letters, numbers, and underscores",
    });
  }

  if (!formData.agent_display_name || formData.agent_display_name.trim() === "") {
    errors.push({
      field: "agent_display_name",
      message: "Agent display name is required",
    });
  }

  if (!formData.clinic_display_name || formData.clinic_display_name.trim() === "") {
    errors.push({
      field: "clinic_display_name",
      message: "Company display name is required",
    });
  }

  if (!formData.specialty || formData.specialty.trim() === "") {
    errors.push({
      field: "specialty",
      message: "Specialty is required",
    });
  }

  // Languages validation
  if (!formData.languages || formData.languages.length === 0) {
    errors.push({
      field: "languages",
      message: "At least one language must be selected",
    });
  }

  // Examples validation
  if (formData.examples) {
    if (formData.examples.length < 3) {
      errors.push({
        field: "examples",
        message: "At least 3 examples are required",
      });
    }
    if (formData.examples.length > 7) {
      errors.push({
        field: "examples",
        message: "Maximum 7 examples allowed (3 standard + 4 custom)",
      });
    }
    formData.examples.forEach((example, index) => {
      if (!example.user_message || example.user_message.trim() === "") {
        errors.push({
          field: `examples[${index}].user_message`,
          message: "User message is required",
        });
      } else if (example.user_message.length > 500) {
        errors.push({
          field: `examples[${index}].user_message`,
          message: "User message must be 500 characters or less",
        });
      }
      if (!example.agent_response || example.agent_response.trim() === "") {
        errors.push({
          field: `examples[${index}].agent_response`,
          message: "Agent response is required",
        });
      } else if (example.agent_response.length > 2000) {
        errors.push({
          field: `examples[${index}].agent_response`,
          message: "Agent response must be 2000 characters or less",
        });
      }
    });
  }

  // RAG: documents are managed on RAG page, no inline validation needed

  return errors;
}

/**
 * Get error message for a specific field.
 */
export function getFieldError(
  errors: ValidationError[],
  field: string
): string | undefined {
  return errors.find((e) => e.field === field)?.message;
}


