/** Per-agent questionnaire management — editor + completed submissions. */

"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { api, ApiError } from "@/lib/api";
import { LoadingSpinner } from "@/components/shared/LoadingSpinner";
import { QuestionnaireEditor } from "@/components/admin/QuestionnaireEditor";
import { QuestionnaireSubmissions } from "@/components/admin/QuestionnaireSubmissions";
import type { QuestionnaireField, QuestionnaireTemplate } from "@/lib/types/questionnaire";

type TabId = "editor" | "submissions";

export default function AgentQuestionnairePage() {
  const params = useParams<{ agentId: string }>();
  const agentId = params?.agentId as string;

  const [template, setTemplate] = useState<QuestionnaireTemplate | null>(null);
  const [submissionsCount, setSubmissionsCount] = useState<number>(0);
  /** Human-readable agent title for the header (falls back to agent_id). */
  const [agentDisplayName, setAgentDisplayName] = useState<string>("");
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<TabId>("editor");

  useEffect(() => {
    if (!agentId) return;
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [agentId]);

  const load = async () => {
    try {
      setIsLoading(true);
      setError(null);
      setAgentDisplayName(agentId);
      const [data, agent] = await Promise.all([
        api.getQuestionnaireTemplate(agentId),
        api.getAgent(agentId).catch(() => null),
      ]);
      setTemplate(data.template);
      setSubmissionsCount(data.submissions_count);
      const display =
        agent?.config?.profile?.agent_display_name?.trim() || agent?.agent_id || agentId;
      setAgentDisplayName(display);
    } catch (err) {
      if (err instanceof ApiError) setError(err.message);
      else setError("Не удалось загрузить анкету");
    } finally {
      setIsLoading(false);
    }
  };

  const handleSave = async (welcome: string, completion: string, fields: QuestionnaireField[]) => {
    try {
      setIsSaving(true);
      setError(null);
      setSuccessMsg(null);
      const saved = await api.updateQuestionnaireTemplate(agentId, {
        welcome_message: welcome,
        completion_message: completion,
        fields,
      });
      setTemplate(saved);
      setSuccessMsg("Анкета сохранена");
      setTimeout(() => setSuccessMsg(null), 3000);
    } catch (err) {
      if (err instanceof ApiError) setError(err.message);
      else setError("Не удалось сохранить анкету");
    } finally {
      setIsSaving(false);
    }
  };

  if (isLoading) {
    return (
      <div className="flex items-center justify-center min-h-screen bg-white">
        <LoadingSpinner size="lg" />
      </div>
    );
  }

  if (!template) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-white via-[#EEEAE7]/5 to-[#251D1C]/10">
        <div className="container mx-auto px-4 py-8">
          <div className="text-sm text-gray-500 mb-1">
            <Link href="/admin/questionnaires" className="hover:underline">
              Анкеты
            </Link>
          </div>
          <h1 className="text-3xl font-bold text-gray-900 mb-4">Анкета агента</h1>
          <div className="bg-red-50 border-l-4 border-red-500 p-4 rounded-sm max-w-xl">
            <p className="text-sm text-red-700">{error || "Не удалось загрузить анкету"}</p>
          </div>
          <button
            type="button"
            onClick={() => void load()}
            className="mt-4 inline-flex items-center rounded-sm border border-[#251D1C] bg-white px-4 py-2 text-sm font-medium text-gray-900 hover:bg-[#EEEAE7]"
          >
            Повторить
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-white via-[#EEEAE7]/5 to-[#251D1C]/10">
      <div className="container mx-auto px-4 py-8">
        <div className="mb-6 flex items-center justify-between">
          <div>
            <div className="text-sm text-gray-500 mb-1">
              <Link href="/admin/questionnaires" className="hover:underline">
                Анкеты
              </Link>{" "}
              /
            </div>
            <h1 className="text-3xl font-bold text-gray-900">Анкета агента</h1>
            <p className="text-gray-600 mt-1">
              <span className="font-medium text-gray-800">{agentDisplayName || agentId}</span>
              {agentDisplayName && agentDisplayName !== agentId ? (
                <span className="block text-xs text-gray-500 mt-0.5 font-mono">{agentId}</span>
              ) : null}
            </p>
          </div>
        </div>

        <div className="mb-6 border-b border-[#BEBAB7]">
          <nav className="flex gap-1">
            <TabButton
              active={activeTab === "editor"}
              onClick={() => setActiveTab("editor")}
            >
              Редактирование
            </TabButton>
            <TabButton
              active={activeTab === "submissions"}
              onClick={() => setActiveTab("submissions")}
            >
              Заполненные анкеты ({submissionsCount})
            </TabButton>
          </nav>
        </div>

        {error && (
          <div className="bg-red-50 border-l-4 border-red-500 p-4 mb-6 rounded-sm">
            <p className="text-sm text-red-700">{error}</p>
          </div>
        )}
        {successMsg && (
          <div className="bg-green-50 border-l-4 border-green-500 p-4 mb-6 rounded-sm">
            <p className="text-sm text-green-700">{successMsg}</p>
          </div>
        )}

        {activeTab === "editor" ? (
          <QuestionnaireEditor
            template={template}
            onSave={handleSave}
            isSaving={isSaving}
          />
        ) : (
          <QuestionnaireSubmissions agentId={agentId} template={template} />
        )}
      </div>
    </div>
  );
}

function TabButton({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      onClick={onClick}
      className={`px-4 py-2 text-sm font-medium border-b-2 -mb-px transition-colors ${
        active
          ? "border-[#251D1C] text-[#251D1C]"
          : "border-transparent text-gray-600 hover:text-[#251D1C]"
      }`}
    >
      {children}
    </button>
  );
}
