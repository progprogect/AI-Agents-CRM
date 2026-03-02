/** Step 4: RAG - Enable toggle only. Documents managed on dedicated RAG page. */

"use client";

import React, { useCallback } from "react";
import Link from "next/link";
import { Toggle } from "@/components/shared/Toggle";
import { Select } from "@/components/shared/Select";
import type { AgentConfigFormData } from "@/lib/utils/agentConfig";

const PROVIDER_OPTIONS = [
  { value: "openai", label: "OpenAI" },
  { value: "google_ai_studio", label: "Google AI Studio (Gemini)" },
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
          Knowledge Base (RAG)
        </h3>
        <p className="text-sm text-gray-600 mb-6">
          Enable RAG to provide context-aware responses based on documents
          about the agent and company.
        </p>
      </div>

      <Toggle
        label="Enable RAG"
        checked={ragEnabled}
        onChange={handleToggleRAG}
        description="Retrieval-Augmented Generation allows the agent to use your documents for context-aware responses."
      />

      {ragEnabled && (
        <div className="mt-4 space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <Select
              label="Embeddings provider"
              value={config.rag_embeddings_provider || "openai"}
              onChange={(e) => onUpdate({ rag_embeddings_provider: e.target.value })}
              options={PROVIDER_OPTIONS}
            />
            <Select
              label="Vision provider (image descriptions)"
              value={config.rag_vision_provider || "openai"}
              onChange={(e) => onUpdate({ rag_vision_provider: e.target.value })}
              options={PROVIDER_OPTIONS}
            />
          </div>
          <div className="p-4 bg-gray-50 rounded-sm border border-gray-200">
          {agentId ? (
            <p className="text-sm text-gray-700">
              <Link
                href={`/admin/agents/${agentId}/rag`}
                className="text-[#251D1C] hover:text-[#443C3C] underline font-medium"
              >
                Manage documents
              </Link>
              {" "}— upload files, organize in folders (PDF, txt, md, json, images).
            </p>
          ) : (
            <p className="text-sm text-gray-700">
              After creating the agent, you&apos;ll add documents on the{" "}
              <span className="font-medium">RAG page</span> — folders, PDFs, images.
            </p>
          )}
          </div>
        </div>
      )}
    </div>
  );
};
