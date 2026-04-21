/** Questionnaires section — list of agents with a link to per-agent editor. */

"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api, ApiError } from "@/lib/api";
import { linkButtonSecondarySmClassName } from "@/components/shared/Button";
import { LoadingSpinner } from "@/components/shared/LoadingSpinner";
import type { Agent } from "@/lib/types";
import type { QuestionnaireResponsePayload } from "@/lib/types/questionnaire";

interface AgentRow {
  agent: Agent;
  fields_count: number;
  submissions_count: number;
  welcome_preview: string;
}

export default function QuestionnairesIndexPage() {
  const [rows, setRows] = useState<AgentRow[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    void load();
  }, []);

  const load = async () => {
    try {
      setIsLoading(true);
      setError(null);
      const agents = await api.listAgents();
      const enriched = await Promise.all(
        agents.map(async (agent) => {
          try {
            const data: QuestionnaireResponsePayload = await api.getQuestionnaireTemplate(agent.agent_id);
            const preview = (data.template.welcome_message || "").slice(0, 120);
            return {
              agent,
              fields_count: data.template.fields.length,
              submissions_count: data.submissions_count,
              welcome_preview: preview,
            };
          } catch {
            return {
              agent,
              fields_count: 0,
              submissions_count: 0,
              welcome_preview: "",
            };
          }
        })
      );
      setRows(enriched);
    } catch (err) {
      if (err instanceof ApiError) setError(err.message);
      else setError("Failed to load questionnaires");
    } finally {
      setIsLoading(false);
    }
  };

  if (isLoading) {
    return (
      <div className="flex items-center justify-center min-h-screen bg-white">
        <LoadingSpinner size="lg" />
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-white via-[#EEEAE7]/5 to-[#251D1C]/10">
      <div className="container mx-auto px-4 py-8">
        <div className="mb-6">
          <h1 className="text-3xl font-bold text-gray-900">Анкеты</h1>
          <p className="text-gray-600 mt-1">
            Редактируйте анкеты агентов и смотрите, что ответили пользователи. Команда /questionnaire в Telegram
            запускает выбранную для агента анкету.
          </p>
        </div>

        {error && (
          <div className="bg-red-50 border-l-4 border-red-500 p-4 mb-6 rounded-sm">
            <p className="text-sm text-red-700">{error}</p>
          </div>
        )}

        {rows.length === 0 ? (
          <div className="bg-white border border-[#BEBAB7] rounded-sm p-8 text-center text-gray-600">
            Пока нет агентов. Создайте агента, чтобы настроить анкету.
          </div>
        ) : (
          <div className="bg-white border border-[#BEBAB7] rounded-sm overflow-hidden">
            <table className="w-full text-sm">
              <thead className="bg-[#EEEAE7]/50 text-left text-[#443C3C]">
                <tr>
                  <th className="px-4 py-3 font-medium">Агент</th>
                  <th className="px-4 py-3 font-medium">Полей</th>
                  <th className="px-4 py-3 font-medium">Заполнений</th>
                  <th className="px-4 py-3 font-medium">Приветствие</th>
                  <th className="px-4 py-3 font-medium text-right">Действие</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => (
                  <tr
                    key={row.agent.agent_id}
                    className="border-t border-[#BEBAB7]/60 hover:bg-[#EEEAE7]/30"
                  >
                    <td className="px-4 py-3">
                      <div className="font-medium text-gray-900">
                        {row.agent.config?.profile?.agent_display_name || row.agent.agent_id}
                      </div>
                      <div className="text-xs text-gray-500">{row.agent.agent_id}</div>
                    </td>
                    <td className="px-4 py-3">{row.fields_count}</td>
                    <td className="px-4 py-3">{row.submissions_count}</td>
                    <td className="px-4 py-3 text-gray-600 max-w-xs truncate">
                      {row.welcome_preview || <span className="italic text-gray-400">не задано</span>}
                    </td>
                    <td className="px-4 py-3 text-right">
                      <Link
                        href={`/admin/agents/${row.agent.agent_id}/questionnaire`}
                        className={linkButtonSecondarySmClassName}
                      >
                        Открыть
                      </Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
