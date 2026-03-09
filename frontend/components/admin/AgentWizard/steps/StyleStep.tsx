/** Step 2: Style and Tone. */

"use client";

import React, { useMemo } from "react";
import { useTranslations } from "next-intl";
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

export const StyleStep: React.FC<StyleStepProps> = ({
  config,
  errors,
  onUpdate,
}) => {
  const t = useTranslations("Wizard");
  const TONE_OPTIONS = useMemo(
    () => [
      { value: "friendly_professional", label: t("toneFriendly") },
      { value: "formal", label: t("toneFormal") },
      { value: "casual", label: t("toneCasual") },
      { value: "warm", label: t("toneWarm") },
    ],
    [t]
  );
  const FORMALITY_OPTIONS = useMemo(
    () => [
      { value: "formal", label: t("formalityFormal") },
      { value: "semi_formal", label: t("formalitySemiFormal") },
      { value: "casual", label: t("formalityCasual") },
    ],
    [t]
  );
  const MESSAGE_LENGTH_OPTIONS = useMemo(
    () => [
      { value: "short", label: t("lengthShort") },
      { value: "short_to_medium", label: t("lengthShortMedium") },
      { value: "medium", label: t("lengthMedium") },
      { value: "medium_to_long", label: t("lengthMediumLong") },
      { value: "long", label: t("lengthLong") },
    ],
    [t]
  );
  const PERSUASION_OPTIONS = useMemo(
    () => [
      { value: "none", label: t("persuasionNone") },
      { value: "soft", label: t("persuasionSoft") },
      { value: "moderate", label: t("persuasionModerate") },
      { value: "strong", label: t("persuasionStrong") },
    ],
    [t]
  );
  return (
    <div className="space-y-6">
      <div>
        <h3 className="text-lg font-semibold text-gray-900 mb-4">
          {t("styleTitle")}
        </h3>
        <p className="text-sm text-gray-600 mb-6">
          {t("styleDesc")}
        </p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <div>
          <Select
            label={t("tone")}
            value={config.tone || "friendly_professional"}
            onChange={(e) => onUpdate({ tone: e.target.value })}
            options={TONE_OPTIONS}
            error={getFieldError(errors, "tone")}
          />
        </div>

        <div>
          <Select
            label={t("formalityLevel")}
            value={config.formality || "semi_formal"}
            onChange={(e) => onUpdate({ formality: e.target.value })}
            options={FORMALITY_OPTIONS}
            error={getFieldError(errors, "formality")}
          />
        </div>

        <div className="md:col-span-2">
          <Slider
            label={t("empathyLevel")}
            value={config.empathy_level ?? 7}
            min={0}
            max={10}
            onChange={(e) =>
              onUpdate({ empathy_level: parseInt(e.target.value) })
            }
            error={getFieldError(errors, "empathy_level")}
          />
          <p className="mt-1 text-xs text-gray-500">
            {t("empathyHint")}
          </p>
        </div>

        <div className="md:col-span-2">
          <Slider
            label={t("depthLevel")}
            value={config.depth_level ?? 5}
            min={0}
            max={10}
            onChange={(e) =>
              onUpdate({ depth_level: parseInt(e.target.value) })
            }
            error={getFieldError(errors, "depth_level")}
          />
          <p className="mt-1 text-xs text-gray-500">
            {t("depthHint")}
          </p>
        </div>

        <div>
          <Select
            label={t("messageLength")}
            value={config.message_length || "short_to_medium"}
            onChange={(e) => onUpdate({ message_length: e.target.value })}
            options={MESSAGE_LENGTH_OPTIONS}
            error={getFieldError(errors, "message_length")}
          />
        </div>

        <div>
          <Select
            label={t("persuasionLevel")}
            value={config.persuasion || "soft"}
            onChange={(e) => onUpdate({ persuasion: e.target.value })}
            options={PERSUASION_OPTIONS}
            error={getFieldError(errors, "persuasion")}
          />
        </div>
      </div>

      {/* Preview */}
      <div className="mt-8 p-6 bg-[#EEEAE7]/10 border border-[#251D1C]/20 rounded-sm">
        <h4 className="text-sm font-medium text-gray-700 mb-4">{t("stylePreview")}</h4>
        <div className="bg-white p-4 rounded-sm border border-[#251D1C]/20">
          <p className="text-sm text-gray-600 mb-2">
            <strong>{t("tone")}:</strong> {TONE_OPTIONS.find((o) => o.value === config.tone)?.label || t("toneFriendly")}
          </p>
          <p className="text-sm text-gray-600 mb-2">
            <strong>{t("formality")}:</strong> {FORMALITY_OPTIONS.find((o) => o.value === config.formality)?.label || t("formalitySemiFormal")}
          </p>
          <p className="text-sm text-gray-600 mb-2">
            <strong>{t("empathy")}:</strong> {config.empathy_level ?? 7}/10
          </p>
          <p className="text-sm text-gray-600 mb-2">
            <strong>{t("depth")}:</strong> {config.depth_level ?? 5}/10
          </p>
          <p className="text-sm text-gray-600">
            <strong>{t("messageLength")}:</strong> {MESSAGE_LENGTH_OPTIONS.find((o) => o.value === config.message_length)?.label || t("lengthShortMedium")}
          </p>
        </div>
      </div>
    </div>
  );
};
