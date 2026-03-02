/** Step 5: LLM Settings. */

"use client";

import React from "react";
import { Select } from "@/components/shared/Select";
import { Slider } from "@/components/shared/Slider";
import { Input } from "@/components/shared/Input";
import type { AgentConfigFormData } from "@/lib/utils/agentConfig";
import type { ValidationError } from "@/lib/utils/validation";
import { getFieldError } from "@/lib/utils/validation";

interface LLMStepProps {
  config: Partial<AgentConfigFormData>;
  errors: ValidationError[];
  onUpdate: (config: Partial<AgentConfigFormData>) => void;
}

const PROVIDER_OPTIONS = [
  { value: "openai", label: "OpenAI" },
  { value: "google_ai_studio", label: "Google AI Studio (Gemini)" },
];

const OPENAI_MODELS = [
  { value: "gpt-4.1", label: "GPT-4.1 (Smartest Non-Reasoning) ⭐", description: "Smartest non-reasoning model" },
  { value: "gpt-4o", label: "GPT-4o (Fast & Intelligent) ⭐", description: "Fast, intelligent, flexible GPT model" },
  { value: "gpt-4o-mini", label: "GPT-4o Mini (Fast & Affordable) ⭐", description: "Fast, affordable small model for focused tasks" },
  { value: "gpt-4-turbo", label: "GPT-4 Turbo (Legacy)", description: "An older high-intelligence GPT model" },
  { value: "gpt-4", label: "GPT-4 (Legacy)", description: "An older high-intelligence GPT model" },
  { value: "gpt-3.5-turbo", label: "GPT-3.5 Turbo (Legacy)", description: "Legacy GPT model for cheaper chat tasks" },
];

const GEMINI_MODELS = [
  { value: "gemini-1.5-pro", label: "Gemini 1.5 Pro ⭐", description: "Most capable Gemini model" },
  { value: "gemini-1.5-flash", label: "Gemini 1.5 Flash", description: "Fast and efficient" },
  { value: "gemini-1.0-pro", label: "Gemini 1.0 Pro", description: "Previous generation" },
];

export const LLMStep: React.FC<LLMStepProps> = ({
  config,
  errors,
  onUpdate,
}) => {
  const provider = config.llm_provider || "openai";
  const modelOptions = provider === "google_ai_studio" ? GEMINI_MODELS : OPENAI_MODELS;
  const defaultModel = provider === "google_ai_studio" ? "gemini-1.5-flash" : "gpt-4o-mini";
  const currentModel = config.llm_model || defaultModel;
  const selectedModel = modelOptions.find((m) => m.value === currentModel)
    || modelOptions[0];

  const handleProviderChange = (newProvider: string) => {
    const newDefault = newProvider === "google_ai_studio" ? "gemini-1.5-flash" : "gpt-4o-mini";
    onUpdate({ llm_provider: newProvider, llm_model: newDefault });
  };

  return (
    <div className="space-y-6">
      <div>
        <h3 className="text-lg font-semibold text-gray-900 mb-4">
          LLM Settings
        </h3>
        <p className="text-sm text-gray-600 mb-6">
          Configure the language model parameters for agent responses.
        </p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <div className="md:col-span-2">
          <Select
            label="Provider"
            value={provider}
            onChange={(e) => handleProviderChange(e.target.value)}
            options={PROVIDER_OPTIONS}
          />
        </div>
        <div className="md:col-span-2">
          <Select
            label="Model"
            value={currentModel}
            onChange={(e) => onUpdate({ llm_model: e.target.value })}
            options={modelOptions.map(({ value, label }) => ({ value, label }))}
            error={getFieldError(errors, "llm_model")}
          />
          {selectedModel?.description && (
            <p className="mt-1 text-xs text-gray-600 italic">
              {selectedModel.description}
            </p>
          )}
          <p className="mt-1 text-xs text-gray-500">
            Choose the model for generating responses. Set GOOGLE_AI_STUDIO_API env for Gemini.
          </p>
        </div>

        <div className="md:col-span-2">
          <Slider
            label="Temperature"
            value={config.llm_temperature ?? 0.2}
            min={0}
            max={2}
            step={0.1}
            onChange={(e) =>
              onUpdate({ llm_temperature: parseFloat(e.target.value) })
            }
            error={getFieldError(errors, "llm_temperature")}
          />
          <p className="mt-1 text-xs text-gray-500">
            Controls randomness (0 = deterministic, 2 = very creative). Recommended: 0.2 for consistent responses.
          </p>
        </div>

        <div className="md:col-span-2">
          <Input
            type="number"
            label="Max Output Tokens"
            value={config.llm_max_tokens ?? 600}
            onChange={(e) =>
              onUpdate({ llm_max_tokens: parseInt(e.target.value) || 600 })
            }
            error={getFieldError(errors, "llm_max_tokens")}
            min={1}
            max={4096}
            helperText="Maximum length of generated responses (1-4096 tokens)"
          />
        </div>
      </div>

      {/* Preview */}
      <div className="mt-8 p-6 bg-[#EEEAE7]/10 border border-[#251D1C]/20 rounded-sm">
        <h4 className="text-sm font-medium text-gray-700 mb-4">
          LLM Configuration Preview
        </h4>
        <div className="bg-white p-4 rounded-sm border border-[#251D1C]/20 space-y-2 text-sm">
          <p className="text-gray-600">
            <strong>Provider:</strong> {provider === "google_ai_studio" ? "Google AI Studio" : "OpenAI"}
          </p>
          <p className="text-gray-600">
            <strong>Model:</strong> {currentModel}
          </p>
          <p className="text-gray-600">
            <strong>Temperature:</strong> {config.llm_temperature ?? 0.2}
          </p>
          <p className="text-gray-600">
            <strong>Max Tokens:</strong> {config.llm_max_tokens ?? 600}
          </p>
        </div>
      </div>
    </div>
  );
};
