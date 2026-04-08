/** Step 4: RAG - Enable toggle only. Documents managed on dedicated RAG page. */

"use client";

import React, { useCallback, useMemo } from "react";
import Link from "next/link";
import { useTranslations } from "next-intl";
import { Toggle } from "@/components/shared/Toggle";
import { Select } from "@/components/shared/Select";
import { Input } from "@/components/shared/Input";
import { Slider } from "@/components/shared/Slider";
import type { AgentConfigFormData } from "@/lib/utils/agentConfig";

const EMBEDDINGS_PROVIDER_OPTIONS = [
  { value: "openai", label: "OpenAI (text-embedding-3-small)" },
  { value: "google_ai_studio", label: "Google AI Studio (text-embedding-004)" },
];

const VISION_PROVIDER_OPTIONS = [
  { value: "openai", label: "OpenAI (gpt-4o)" },
  { value: "google_ai_studio", label: "Google AI Studio (Gemini)" },
];

/** Touch targets ≥48px (web.dev / Material); slightly larger base font on small viewports. */
const selectTouchClass = "min-h-12 text-base sm:text-sm";

interface RAGStepProps {
  config: Partial<AgentConfigFormData>;
  onUpdate: (config: Partial<AgentConfigFormData>) => void;
  agentId?: string;
}

export const RAGStep: React.FC<RAGStepProps> = ({
  config,
  onUpdate,
  agentId,
}) => {
  const t = useTranslations("Wizard");
  const ragEnabled = config.rag_enabled || false;

  const googleVisionModelOptions = useMemo(
    () => [
      { value: "", label: t("visionModelDefaultOption") },
      { value: "gemini-3.1-pro-preview", label: t("visionModelGemini31ProPreview") },
      { value: "gemini-3-flash-preview", label: t("visionModelGemini3FlashPreview") },
      { value: "gemini-3.1-flash-lite-preview", label: t("visionModelGemini31FlashLitePreview") },
      { value: "gemini-2.5-pro", label: t("visionModelGemini25Pro") },
      { value: "gemini-2.5-flash", label: t("visionModelGemini25Flash") },
      { value: "gemini-2.5-flash-lite", label: t("visionModelGemini25FlashLite") },
    ],
    [t]
  );

  const handleVisionProviderChange = useCallback(
    (value: string) => {
      if (value === "google_ai_studio") {
        onUpdate({
          rag_vision_provider: value,
          rag_vision_model:
            config.rag_vision_model && config.rag_vision_model.trim() !== ""
              ? config.rag_vision_model
              : "gemini-3.1-pro-preview",
        });
      } else {
        onUpdate({ rag_vision_provider: value, rag_vision_model: undefined });
      }
    },
    [onUpdate, config.rag_vision_model]
  );

  const handleToggleRAG = useCallback(
    (enabled: boolean) => {
      onUpdate({
        rag_enabled: enabled,
        rag_documents: [],
      });
    },
    [onUpdate]
  );

  return (
    <div className="space-y-6">
      <div>
        <h3 className="text-lg font-semibold text-gray-900 mb-4">
          {t("ragTitle")}
        </h3>
        <p className="text-sm text-gray-600 mb-6">
          {t("ragDesc")}
        </p>
      </div>

      <Toggle
        label={t("enableRAG")}
        checked={ragEnabled}
        onChange={handleToggleRAG}
        description={t("ragDescription")}
      />

      {ragEnabled && (
        <div className="mt-4 space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <Select
              label={t("embeddingsProvider")}
              value={config.rag_embeddings_provider || "openai"}
              onChange={(e) => onUpdate({ rag_embeddings_provider: e.target.value })}
              options={EMBEDDINGS_PROVIDER_OPTIONS}
              className={selectTouchClass}
            />
            <Select
              label={t("visionProvider")}
              value={config.rag_vision_provider || "openai"}
              onChange={(e) => handleVisionProviderChange(e.target.value)}
              options={VISION_PROVIDER_OPTIONS}
              className={selectTouchClass}
            />
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <Input
              type="number"
              label={t("ragTopK")}
              value={config.rag_top_k ?? 6}
              min={1}
              max={50}
              onChange={(e) => {
                const raw = parseInt(e.target.value, 10);
                const v = Number.isNaN(raw) ? 6 : Math.min(50, Math.max(1, raw));
                onUpdate({ rag_top_k: v });
              }}
              helperText={t("ragTopKHint")}
            />
            <div className="md:col-span-1">
              <Slider
                label={t("ragScoreThreshold")}
                value={config.rag_score_threshold ?? 0.2}
                min={0}
                max={1}
                step={0.05}
                onChange={(e) =>
                  onUpdate({ rag_score_threshold: parseFloat(e.target.value) })
                }
              />
              <p className="mt-1 text-xs text-gray-500">{t("ragScoreThresholdHint")}</p>
            </div>
          </div>
          {(config.rag_vision_provider || "openai") === "google_ai_studio" && (
            <div>
              <Select
                label={t("visionModelLabel")}
                value={config.rag_vision_model ?? ""}
                onChange={(e) =>
                  onUpdate({
                    rag_vision_model: e.target.value === "" ? undefined : e.target.value,
                  })
                }
                options={googleVisionModelOptions}
                className={selectTouchClass}
              />
              <p className="mt-1 text-xs text-gray-500 break-words">{t("visionModelHint")}</p>
              <p className="mt-1 text-xs text-amber-800 bg-amber-50 border border-amber-200 rounded-sm px-2 py-1.5 break-words leading-snug">
                {t("visionModelPreviewNote")}
              </p>
            </div>
          )}
          <div className="p-4 bg-gray-50 rounded-sm border border-gray-200">
          {agentId ? (
            <p className="text-sm text-gray-700">
              <Link
                href={`/admin/agents/${agentId}/rag`}
                className="text-[#251D1C] hover:text-[#443C3C] underline font-medium"
              >
                {t("manageDocuments")}
              </Link>
              {" "}{t("manageDocumentsHint")}
            </p>
          ) : (
            <p className="text-sm text-gray-700">
              {t("ragAfterCreate")}
            </p>
          )}
          </div>
        </div>
      )}
    </div>
  );
};
