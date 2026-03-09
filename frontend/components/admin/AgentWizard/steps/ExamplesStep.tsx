/** Step 3: Communication Examples. */

"use client";

import React, { useMemo, useEffect } from "react";
import { useTranslations } from "next-intl";
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
  const t = useTranslations("Wizard");
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
          {t("examplesTitle")}
        </h3>
        <p className="text-sm text-gray-600 mb-6">
          {t("examplesDesc")}
        </p>
      </div>

      {/* Standard Examples */}
      <div className="space-y-6">
        <div>
          <h4 className="text-md font-medium text-gray-900 mb-2">
            {t("standardExamples")}
          </h4>
          <p className="text-xs text-gray-500 mb-4">
            {t("standardExamplesHint")}
          </p>
        </div>

        {standardExamples.map((example, index) => (
          <div
            key={example.id}
            className="p-4 bg-gray-50 rounded-sm border border-gray-200 space-y-4"
          >
            <div className="flex items-center justify-between mb-2">
              <h5 className="text-sm font-medium text-gray-900">
                {t("exampleN", { n: index + 1 })}: {example.category === "booking" && t("exampleBooking")}
                {example.category === "info" && t("exampleInfo")}
                {example.category === "hours" && t("exampleHours")}
              </h5>
            </div>
            <Textarea
              label={t("userMessage")}
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
              label={t("agentResponse")}
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
              {t("customExamples")}
            </h4>
            <p className="text-xs text-gray-500 mt-1">
              {t("customExamplesHint")}
            </p>
          </div>
          <Button
            variant="secondary"
            size="sm"
            onClick={handleAddCustomExample}
            disabled={examples.length >= 7}
          >
            {t("addCustomExample")}
          </Button>
        </div>

        {customExamples.length === 0 ? (
          <div className="text-center py-8 bg-gray-50 rounded-sm border border-gray-200">
            <p className="text-sm text-gray-600 mb-4">
              {t("noCustomExamples")}
            </p>
            <p className="text-xs text-gray-500">
              {t("addCustomExampleHint")}
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
                      {t("customExample", { n: index + 1 })}
                    </h5>
                    <Button
                      variant="danger"
                      size="sm"
                      onClick={() => handleRemoveCustomExample(actualIndex)}
                    >
                      {t("remove")}
                    </Button>
                  </div>
                  <Textarea
                    label={t("userMessage")}
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
                    label={t("agentResponse")}
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
          <strong>Tip:</strong> {t("examplesTip")}
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

