/** Create agent page. */

"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { useTranslations } from "next-intl";
import { AgentWizard } from "@/components/admin/AgentWizard";

export default function CreateAgentPage() {
  const router = useRouter();
  const t = useTranslations("Wizard");
  // Use lazy initialization to avoid setState in effect
  const [hasDraft] = useState(() => {
    if (typeof window === "undefined") return false;
    try {
      const draft = localStorage.getItem("agent_wizard_draft");
      return !!draft && !!JSON.parse(draft);
    } catch {
      return false;
    }
  });

  const handleSuccess = (result?: { agentId: string; isCreate: boolean; ragEnabled: boolean }) => {
    if (result?.isCreate && result?.ragEnabled) {
      router.push(`/admin/agents/${result.agentId}/rag`);
    } else {
      router.push("/admin/agents");
    }
  };

  const handleCancel = () => {
    router.push("/admin/agents");
  };

  return (
    <div className="p-6">
      {hasDraft && (
        <div className="mb-4 p-4 bg-[#EEEAE7]/10 border border-[#251D1C]/20 rounded-sm">
          <p className="text-sm text-gray-700">
            <strong>
              {(() => {
                try {
                  const draft = JSON.parse(
                    localStorage.getItem("agent_wizard_draft") || "{}"
                  );
                  if (draft.isEdit) return t("draftEditing");
                  return draft.isClone
                    ? t("draftCloning")
                    : t("draftDetected");
                } catch {
                  return t("draftDetected");
                }
              })()}
            </strong>{" "}
            {(() => {
              try {
                const draft = JSON.parse(
                  localStorage.getItem("agent_wizard_draft") || "{}"
                );
                if (draft.isEdit) {
                  return t("draftEditLoaded", { id: draft.editingAgentId });
                }
                return draft.isClone
                  ? t("draftCloneLoaded", { id: draft.sourceAgentId })
                  : t("draftRestored");
              } catch {
                return t("draftRestored");
              }
            })()}
          </p>
        </div>
      )}
      <AgentWizard onSuccess={handleSuccess} onCancel={handleCancel} />
    </div>
  );
}

