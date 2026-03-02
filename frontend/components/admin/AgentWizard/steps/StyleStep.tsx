/** Step 2: Style and Tone. */

"use client";

import React from "react";
import { Select } from "@/components/shared/Select";
import { Slider } from "@/components/shared/Slider";
import type { AgentConfigFormData } from "@/lib/utils/agentConfig";
import type { ValidationError } from "@/lib/utils/validation";
import { getFieldError } from "@/lib/utils/validation";

interface StyleStepProps {
  config: Partial<AgentConfigFormData>;
  errors: ValidationError[];
  onUpdate: (config: Partial<AgentConfigFormData>) => void;
}

const TONE_OPTIONS = [
  { value: "friendly_professional", label: "Friendly & Professional" },
  { value: "formal", label: "Formal" },
  { value: "casual", label: "Casual" },
  { value: "warm", label: "Warm" },
];

const FORMALITY_OPTIONS = [
  { value: "formal", label: "Formal" },
  { value: "semi_formal", label: "Semi-Formal" },
  { value: "casual", label: "Casual" },
];

const MESSAGE_LENGTH_OPTIONS = [
  { value: "short", label: "Short" },
  { value: "short_to_medium", label: "Short to Medium" },
  { value: "medium", label: "Medium" },
  { value: "medium_to_long", label: "Medium to Long" },
  { value: "long", label: "Long" },
];

const PERSUASION_OPTIONS = [
  { value: "none", label: "None" },
  { value: "soft", label: "Soft" },
  { value: "moderate", label: "Moderate" },
  { value: "strong", label: "Strong" },
];

export const StyleStep: React.FC<StyleStepProps> = ({
  config,
  errors,
  onUpdate,
}) => {
  return (
    <div className="space-y-6">
      <div>
        <h3 className="text-lg font-semibold text-gray-900 mb-4">
          Style & Tone
        </h3>
        <p className="text-sm text-gray-600 mb-6">
          Configure the communication style and tone of the agent.
        </p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <div>
          <Select
            label="Tone"
            value={config.tone || "friendly_professional"}
            onChange={(e) => onUpdate({ tone: e.target.value })}
            options={TONE_OPTIONS}
            error={getFieldError(errors, "tone")}
          />
        </div>

        <div>
          <Select
            label="Formality Level"
            value={config.formality || "semi_formal"}
            onChange={(e) => onUpdate({ formality: e.target.value })}
            options={FORMALITY_OPTIONS}
            error={getFieldError(errors, "formality")}
          />
        </div>

        <div className="md:col-span-2">
          <Slider
            label="Empathy Level"
            value={config.empathy_level ?? 7}
            min={0}
            max={10}
            onChange={(e) =>
              onUpdate({ empathy_level: parseInt(e.target.value) })
            }
            error={getFieldError(errors, "empathy_level")}
          />
          <p className="mt-1 text-xs text-gray-500">
            How empathetic and understanding the agent should be (0-10)
          </p>
        </div>

        <div className="md:col-span-2">
          <Slider
            label="Depth Level"
            value={config.depth_level ?? 5}
            min={0}
            max={10}
            onChange={(e) =>
              onUpdate({ depth_level: parseInt(e.target.value) })
            }
            error={getFieldError(errors, "depth_level")}
          />
          <p className="mt-1 text-xs text-gray-500">
            How detailed and thorough responses should be (0-10)
          </p>
        </div>

        <div>
          <Select
            label="Message Length"
            value={config.message_length || "short_to_medium"}
            onChange={(e) => onUpdate({ message_length: e.target.value })}
            options={MESSAGE_LENGTH_OPTIONS}
            error={getFieldError(errors, "message_length")}
          />
        </div>

        <div>
          <Select
            label="Persuasion Level"
            value={config.persuasion || "soft"}
            onChange={(e) => onUpdate({ persuasion: e.target.value })}
            options={PERSUASION_OPTIONS}
            error={getFieldError(errors, "persuasion")}
          />
        </div>
      </div>

      {/* Preview */}
      <div className="mt-8 p-6 bg-[#EEEAE7]/10 border border-[#251D1C]/20 rounded-sm">
        <h4 className="text-sm font-medium text-gray-700 mb-4">Style Preview</h4>
        <div className="bg-white p-4 rounded-sm border border-[#251D1C]/20">
          <p className="text-sm text-gray-600 mb-2">
            <strong>Tone:</strong> {TONE_OPTIONS.find((o) => o.value === config.tone)?.label || "Friendly & Professional"}
          </p>
          <p className="text-sm text-gray-600 mb-2">
            <strong>Formality:</strong> {FORMALITY_OPTIONS.find((o) => o.value === config.formality)?.label || "Semi-Formal"}
          </p>
          <p className="text-sm text-gray-600 mb-2">
            <strong>Empathy:</strong> {config.empathy_level ?? 7}/10
          </p>
          <p className="text-sm text-gray-600 mb-2">
            <strong>Depth:</strong> {config.depth_level ?? 5}/10
          </p>
          <p className="text-sm text-gray-600">
            <strong>Message Length:</strong> {MESSAGE_LENGTH_OPTIONS.find((o) => o.value === config.message_length)?.label || "Short to Medium"}
          </p>
        </div>
      </div>
    </div>
  );
};
