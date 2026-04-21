/** Submissions tab: table of fill/edit sessions and per-submission timeline. */

"use client";

import React, { useEffect, useMemo, useState } from "react";
import { api, ApiError } from "@/lib/api";
import { LoadingSpinner } from "@/components/shared/LoadingSpinner";
import type {
  QuestionnaireTemplate,
  QuestionnaireSubmissionListItem,
  QuestionnaireSubmissionDetail,
  QuestionnaireResponseItem,
} from "@/lib/types/questionnaire";

interface Props {
  agentId: string;
  template: QuestionnaireTemplate;
}

const STATUS_LABEL: Record<string, string> = {
  in_progress: "В процессе",
  completed: "Завершено",
  cancelled: "Отменено",
};

const SOURCE_LABEL: Record<string, string> = {
  fill: "Заполнение",
  edit: "Редактирование",
};

export const QuestionnaireSubmissions: React.FC<Props> = ({ agentId, template }) => {
  const [items, setItems] = useState<QuestionnaireSubmissionListItem[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState<string>("");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [selectedDetail, setSelectedDetail] = useState<QuestionnaireSubmissionDetail | null>(null);

  const labelByKey = useMemo(() => {
    const acc: Record<string, string> = {};
    for (const f of template.fields) acc[f.key] = f.label;
    return acc;
  }, [template.fields]);

  useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [agentId, statusFilter]);

  const load = async () => {
    try {
      setIsLoading(true);
      setError(null);
      const params: Parameters<typeof api.listQuestionnaireSubmissions>[1] = {
        limit: 100,
      };
      if (statusFilter) {
        params.status = statusFilter as typeof params.status;
      }
      const rows = await api.listQuestionnaireSubmissions(agentId, params);
      setItems(rows);
    } catch (err) {
      if (err instanceof ApiError) setError(err.message);
      else setError("Не удалось загрузить заполненные анкеты");
    } finally {
      setIsLoading(false);
    }
  };

  const openDetail = async (submissionId: string) => {
    setSelectedId(submissionId);
    setSelectedDetail(null);
    try {
      const detail = await api.getQuestionnaireSubmission(submissionId);
      setSelectedDetail(detail);
    } catch (err) {
      if (err instanceof ApiError) setError(err.message);
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3">
        <label className="text-sm text-gray-700">Статус:</label>
        <select
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value)}
          className="border border-[#BEBAB7] rounded-sm px-2 py-1 text-sm"
        >
          <option value="">Все</option>
          <option value="in_progress">В процессе</option>
          <option value="completed">Завершено</option>
          <option value="cancelled">Отменено</option>
        </select>
      </div>

      {error && (
        <div className="bg-red-50 border-l-4 border-red-500 p-3 rounded-sm">
          <p className="text-sm text-red-700">{error}</p>
        </div>
      )}

      {isLoading ? (
        <div className="flex justify-center py-10">
          <LoadingSpinner />
        </div>
      ) : items.length === 0 ? (
        <div className="bg-white border border-[#BEBAB7] rounded-sm p-6 text-center text-gray-600">
          Пока никто не заполнял эту анкету.
        </div>
      ) : (
        <div className="bg-white border border-[#BEBAB7] rounded-sm overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-[#EEEAE7]/50 text-left text-[#443C3C]">
              <tr>
                <th className="px-4 py-3 font-medium">Пользователь</th>
                <th className="px-4 py-3 font-medium">Канал</th>
                <th className="px-4 py-3 font-medium">Тип</th>
                <th className="px-4 py-3 font-medium">Статус</th>
                <th className="px-4 py-3 font-medium">Ответов</th>
                <th className="px-4 py-3 font-medium">Начало</th>
                <th className="px-4 py-3 font-medium">Завершение</th>
              </tr>
            </thead>
            <tbody>
              {items.map(({ submission, answers_count }) => (
                <tr
                  key={submission.submission_id}
                  className="border-t border-[#BEBAB7]/60 hover:bg-[#EEEAE7]/30 cursor-pointer"
                  onClick={() => openDetail(submission.submission_id)}
                >
                  <td className="px-4 py-3 font-mono text-xs text-gray-700">
                    {submission.external_user_id}
                  </td>
                  <td className="px-4 py-3">{submission.channel}</td>
                  <td className="px-4 py-3">{SOURCE_LABEL[submission.source] || submission.source}</td>
                  <td className="px-4 py-3">
                    <StatusBadge status={submission.status} />
                  </td>
                  <td className="px-4 py-3">{answers_count}</td>
                  <td className="px-4 py-3 text-gray-600">{formatTime(submission.started_at)}</td>
                  <td className="px-4 py-3 text-gray-600">
                    {submission.completed_at
                      ? formatTime(submission.completed_at)
                      : submission.cancelled_at
                      ? formatTime(submission.cancelled_at)
                      : "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {selectedId && (
        <SubmissionDrawer
          detail={selectedDetail}
          labelByKey={labelByKey}
          onClose={() => {
            setSelectedId(null);
            setSelectedDetail(null);
          }}
        />
      )}
    </div>
  );
};

function StatusBadge({ status }: { status: string }) {
  const color =
    status === "completed"
      ? "bg-green-100 text-green-800"
      : status === "cancelled"
      ? "bg-gray-100 text-gray-600"
      : "bg-amber-100 text-amber-800";
  return (
    <span className={`inline-block px-2 py-0.5 rounded-sm text-xs font-medium ${color}`}>
      {STATUS_LABEL[status] || status}
    </span>
  );
}

function formatTime(iso: string): string {
  try {
    const d = new Date(iso);
    return d.toLocaleString();
  } catch {
    return iso;
  }
}

interface DrawerProps {
  detail: QuestionnaireSubmissionDetail | null;
  labelByKey: Record<string, string>;
  onClose: () => void;
}

const SubmissionDrawer: React.FC<DrawerProps> = ({ detail, labelByKey, onClose }) => {
  return (
    <div className="fixed inset-0 z-40 flex justify-end bg-black/30" onClick={onClose}>
      <aside
        className="w-full md:w-[520px] bg-white h-full overflow-y-auto shadow-xl border-l border-[#BEBAB7]"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="sticky top-0 bg-white border-b border-[#BEBAB7] px-5 py-3 flex items-center justify-between">
          <div className="font-semibold text-gray-900">Детали заполнения</div>
          <button
            onClick={onClose}
            className="text-gray-500 hover:text-gray-800"
            aria-label="Закрыть"
          >
            ✕
          </button>
        </div>
        <div className="p-5">
          {!detail ? (
            <div className="flex justify-center py-10">
              <LoadingSpinner />
            </div>
          ) : detail.responses.length === 0 ? (
            <div className="text-sm text-gray-600">Ответов ещё нет.</div>
          ) : (
            <SubmissionTimeline responses={detail.responses} labelByKey={labelByKey} />
          )}
        </div>
      </aside>
    </div>
  );
};

function SubmissionTimeline({
  responses,
  labelByKey,
}: {
  responses: QuestionnaireResponseItem[];
  labelByKey: Record<string, string>;
}) {
  return (
    <ul className="space-y-3">
      {responses.map((r) => (
        <li key={r.response_id} className="border border-[#BEBAB7] rounded-sm p-3">
          <div className="text-sm font-medium text-gray-900">
            {labelByKey[r.field_key] || r.field_key}
          </div>
          <div className="mt-1 text-sm text-gray-700 whitespace-pre-wrap">{r.value}</div>
          <div className="mt-1 text-xs text-gray-500">{formatTime(r.created_at)}</div>
        </li>
      ))}
    </ul>
  );
}
