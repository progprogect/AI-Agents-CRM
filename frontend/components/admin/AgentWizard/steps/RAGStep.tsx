/** Step 4: RAG - Enable toggle only. Documents managed on dedicated RAG page. */

"use client";

import React, { useCallback } from "react";
import Link from "next/link";
import { useTranslations } from "next-intl";
import { Toggle } from "@/components/shared/Toggle";
import { Select } from "@/components/shared/Select";
import type { AgentConfigFormData } from "@/lib/utils/agentConfig";

const EMBEDDINGS_PROVIDER_OPTIONS = [
  { value: "openai", label: "OpenAI (text-embedding-3-small)" },
  { value: "google_ai_studio", label: "Google AI Studio (text-embedding-004)" },
];

const VISION_PROVIDER_OPTIONS = [
  { value: "openai", label: "OpenAI (gpt-4o)" },
  { value: "google_ai_studio", label: "Google AI Studio (Gemini 2.5 Flash)" },
];

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
            />
            <Select
              label={t("visionProvider")}
              value={config.rag_vision_provider || "openai"}
              onChange={(e) => onUpdate({ rag_vision_provider: e.target.value })}
              options={VISION_PROVIDER_OPTIONS}
            />
          </div>
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
