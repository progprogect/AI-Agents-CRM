/** Step 3: Communication Examples. */

"use client";

import React, { useMemo, useEffect } from "react";
import { Textarea } from "@/components/shared/Textarea";
import { Button } from "@/components/shared/Button";
import type { AgentConfigFormData, ConversationExample } from "@/lib/utils/agentConfig";
import { DEFAULT_EXAMPLES } from "@/lib/utils/agentConfig";
import type { ValidationError } from "@/lib/utils/validation";
import { getFieldError } from "@/lib/utils/validation";

interface ExamplesStepProps {
  config: Partial<AgentConfigFormData>;
  errors: ValidationError[];
  onUpdate: (config: Partial<AgentConfigFormData>) => void;
}

export const ExamplesStep: React.FC<ExamplesStepProps> = ({
  config,
  errors,
  onUpdate,
}) => {
  // Initialize examples with defaults if not present
  useEffect(() => {
    if (!config.examples || config.examples.length === 0) {
      onUpdate({ examples: [...DEFAULT_EXAMPLES] });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []); // Only run on mount - examples are initialized in generateDefaultConfig

  const examples = useMemo(() => {
    if (config.examples && config.examples.length > 0) {
      return config.examples;
    }
    return DEFAULT_EXAMPLES;
  }, [config.examples]);

  const standardExamples = examples.slice(0, 3);
  const customExamples = examples.slice(3);

  const handleUpdateExample = (
    index: number,
    field: "user_message" | "agent_response",
    value: string
  ) => {
    const updated = [...examples];
    updated[index] = {
      ...updated[index],
      [field]: value,
    };
    onUpdate({ examples: updated });
  };

  const handleAddCustomExample = () => {
    if (examples.length >= 7) {
      return; // Maximum 7 examples
    }
    const newExample: ConversationExample = {
      id: `custom_${Date.now()}`,
      user_message: "",
      agent_response: "",
      category: "custom",
    };
    onUpdate({ examples: [...examples, newExample] });
  };

  const handleRemoveCustomExample = (index: number) => {
    const updated = examples.filter((_, i) => i !== index);
    onUpdate({ examples: updated });
  };

  return (
    <div className="space-y-6">
      <div>
        <h3 className="text-lg font-semibold text-gray-900 mb-4">
          Communication Examples
        </h3>
        <p className="text-sm text-gray-600 mb-6">
          Provide examples of how you want the agent to communicate. These examples
          will guide the agent's style and tone. Examples should be in English, but
          the agent will respond in the user's language.
        </p>
      </div>

      {/* Standard Examples */}
      <div className="space-y-6">
        <div>
          <h4 className="text-md font-medium text-gray-900 mb-2">
            Standard Examples (Editable)
          </h4>
          <p className="text-xs text-gray-500 mb-4">
            These are common questions patients ask. You can edit them to match your
            preferred style.
          </p>
        </div>

        {standardExamples.map((example, index) => (
          <div
            key={example.id}
            className="p-4 bg-gray-50 rounded-sm border border-gray-200 space-y-4"
          >
            <div className="flex items-center justify-between mb-2">
              <h5 className="text-sm font-medium text-gray-900">
                Example {index + 1}: {example.category === "booking" && "Booking"}
                {example.category === "info" && "Services Information"}
                {example.category === "hours" && "Working Hours"}
              </h5>
            </div>
            <Textarea
              label="User Message"
              value={example.user_message}
              onChange={(e) =>
                handleUpdateExample(index, "user_message", e.target.value)
              }
              error={getFieldError(errors, `examples[${index}].user_message`)}
              placeholder="e.g., How can I book an appointment?"
              rows={2}
              maxLength={500}
              helperText={`${example.user_message.length}/500 characters`}
            />
            <Textarea
              label="Agent Response"
              value={example.agent_response}
              onChange={(e) =>
                handleUpdateExample(index, "agent_response", e.target.value)
              }
              error={getFieldError(errors, `examples[${index}].agent_response`)}
              placeholder="Enter the desired agent response..."
              rows={4}
              maxLength={2000}
              helperText={`${example.agent_response.length}/2000 characters`}
            />
          </div>
        ))}
      </div>

      {/* Custom Examples */}
      <div className="space-y-4">
        <div className="flex items-center justify-between">
          <div>
            <h4 className="text-md font-medium text-gray-900">
              Custom Examples
            </h4>
            <p className="text-xs text-gray-500 mt-1">
              Add your own examples to demonstrate specific communication scenarios.
              Maximum 4 custom examples.
            </p>
          </div>
          <Button
            variant="secondary"
            size="sm"
            onClick={handleAddCustomExample}
            disabled={examples.length >= 7}
          >
            Add Custom Example
          </Button>
        </div>

        {customExamples.length === 0 ? (
          <div className="text-center py-8 bg-gray-50 rounded-sm border border-gray-200">
            <p className="text-sm text-gray-600 mb-4">
              No custom examples added yet.
            </p>
            <p className="text-xs text-gray-500">
              Click "Add Custom Example" to add your own communication examples.
            </p>
          </div>
        ) : (
          <div className="space-y-4">
            {customExamples.map((example, index) => {
              const actualIndex = index + 3; // Offset by standard examples
              return (
                <div
                  key={example.id}
                  className="p-4 bg-white rounded-sm border border-[#251D1C]/20 space-y-4"
                >
                  <div className="flex items-center justify-between mb-2">
                    <h5 className="text-sm font-medium text-gray-900">
                      Custom Example {index + 1}
                    </h5>
                    <Button
                      variant="danger"
                      size="sm"
                      onClick={() => handleRemoveCustomExample(actualIndex)}
                    >
                      Remove
                    </Button>
                  </div>
                  <Textarea
                    label="User Message"
                    value={example.user_message}
                    onChange={(e) =>
                      handleUpdateExample(actualIndex, "user_message", e.target.value)
                    }
                    error={getFieldError(
                      errors,
                      `examples[${actualIndex}].user_message`
                    )}
                    placeholder="e.g., What insurance do you accept?"
                    rows={2}
                    maxLength={500}
                    helperText={`${example.user_message.length}/500 characters`}
                  />
                  <Textarea
                    label="Agent Response"
                    value={example.agent_response}
                    onChange={(e) =>
                      handleUpdateExample(
                        actualIndex,
                        "agent_response",
                        e.target.value
                      )
                    }
                    error={getFieldError(
                      errors,
                      `examples[${actualIndex}].agent_response`
                    )}
                    placeholder="Enter the desired agent response..."
                    rows={4}
                    maxLength={2000}
                    helperText={`${example.agent_response.length}/2000 characters`}
                  />
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* Info Box */}
      <div className="mt-6 p-4 bg-blue-50 border border-blue-200 rounded-sm">
        <p className="text-sm text-blue-800">
          <strong>Tip:</strong> These examples demonstrate the desired communication
          style. The agent will learn from these examples to match your preferred
          tone, formality level, and response style. Make sure examples reflect the
          style settings you configured in the previous step.
        </p>
      </div>

      {/* Error Display */}
      {getFieldError(errors, "examples") && (
        <div className="p-3 bg-red-50 border border-red-200 rounded-sm">
          <p className="text-sm text-red-600">
            {getFieldError(errors, "examples")}
          </p>
        </div>
      )}
    </div>
  );
};

