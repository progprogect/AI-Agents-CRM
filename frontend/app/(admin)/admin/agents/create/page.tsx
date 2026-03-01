/** Create agent page. */

"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { AgentWizard } from "@/components/admin/AgentWizard";

export default function CreateAgentPage() {
  const router = useRouter();
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
        <div className="mb-4 p-4 bg-[#F5D76E]/10 border border-[#D4AF37]/20 rounded-sm">
          <p className="text-sm text-gray-700">
            <strong>
              {(() => {
                try {
                  const draft = JSON.parse(
                    localStorage.getItem("agent_wizard_draft") || "{}"
                  );
                  if (draft.isEdit) return "Editing agent:";
                  return draft.isClone
                    ? "Cloning agent:"
                    : "Draft detected:";
                } catch {
                  return "Draft detected:";
                }
              })()}
            </strong>{" "}
            {(() => {
              try {
                const draft = JSON.parse(
                  localStorage.getItem("agent_wizard_draft") || "{}"
                );
                if (draft.isEdit) {
                  return `Configuration for "${draft.editingAgentId}" has been loaded. Make your changes and click "Update Agent" when ready.`;
                }
                return draft.isClone
                  ? `Configuration from "${draft.sourceAgentId}" has been loaded. Please review and update the Agent ID.`
                  : "Your previous progress has been restored.";
              } catch {
                return "Your previous progress has been restored.";
              }
            })()}
          </p>
        </div>
      )}
      <AgentWizard onSuccess={handleSuccess} onCancel={handleCancel} />
    </div>
  );
}

