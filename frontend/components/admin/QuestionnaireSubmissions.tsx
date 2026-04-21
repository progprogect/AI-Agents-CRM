/** Submissions tab: table of fill/edit sessions and per-submission timeline. */

"use client";

import React, { useEffect, useMemo, useState } from "react";
import { api, ApiError } from "@/lib/api";
import { Input } from "@/components/shared/Input";
import { LoadingSpinner } from "@/components/shared/LoadingSpinner";
import { Select } from "@/components/shared/Select";
import { SegmentedControl } from "@/components/shared/SegmentedControl";
import type {
  QuestionnaireTemplate,
  QuestionnaireSubmissionListItem,
  QuestionnaireSubmissionDetail,
  QuestionnaireResponseItem,
  QuestionnaireSubmissionSort,
} from "@/lib/types/questionnaire";

const DEFAULT_SORT: QuestionnaireSubmissionSort = "started_at_desc";

const SORT_OPTIONS: { value: QuestionnaireSubmissionSort; label: string }[] = [
  { value: "started_at_desc", label: "Начало: сначала новые" },
  { value: "started_at_asc", label: "Начало: сначала старые" },
  { value: "completed_at_desc", label: "Завершение: сначала новые" },
  { value: "completed_at_asc", label: "Завершение: сначала старые" },
];

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

type SubmissionsViewMode = "compact" | "table";

const VIEW_MODE_SEGMENTS: { value: SubmissionsViewMode; label: string }[] = [
  { value: "compact", label: "Компактный список" },
  { value: "table", label: "Таблица с ответами" },
];

const CONTROL_BORDER = "border-[#BEBAB7]";

/** Column keys: template order first, then orphan keys from snapshots (sorted). */
function tableColumnKeys(
  fields: QuestionnaireTemplate["fields"],
  items: QuestionnaireSubmissionListItem[]
): string[] {
  const ordered = [...fields].sort((a, b) => a.order - b.order).map((f) => f.key);
  const known = new Set(ordered);
  const extras = new Set<string>();
  for (const row of items) {
    const snap = row.field_snapshot ?? {};
    for (const k of Object.keys(snap)) {
      if (!known.has(k)) extras.add(k);
    }
  }
  return [...ordered, ...Array.from(extras).sort((a, b) => a.localeCompare(b))];
}

export const QuestionnaireSubmissions: React.FC<Props> = ({ agentId, template }) => {
  const [items, setItems] = useState<QuestionnaireSubmissionListItem[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState<string>("");
  const [fieldKeyFilter, setFieldKeyFilter] = useState<string>("");
  const [valueSearchDraft, setValueSearchDraft] = useState("");
  const [valueSearch, setValueSearch] = useState("");
  const [sort, setSort] = useState<QuestionnaireSubmissionSort>(DEFAULT_SORT);
  const [historicFieldKeys, setHistoricFieldKeys] = useState<string[]>([]);
  const [viewMode, setViewMode] = useState<SubmissionsViewMode>("compact");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [selectedDetail, setSelectedDetail] = useState<QuestionnaireSubmissionDetail | null>(null);

  const labelByKey = useMemo(() => {
    const acc: Record<string, string> = {};
    for (const f of template.fields) acc[f.key] = f.label;
    return acc;
  }, [template.fields]);

  const fieldKeySelectOptions = useMemo(() => {
    const s = new Set<string>();
    for (const f of template.fields) s.add(f.key);
    for (const k of historicFieldKeys) s.add(k);
    return Array.from(s).sort((a, b) => a.localeCompare(b));
  }, [template.fields, historicFieldKeys]);

  const statusSelectOptions = useMemo(
    () => [
      { value: "", label: "Все" },
      { value: "in_progress", label: STATUS_LABEL.in_progress },
      { value: "completed", label: STATUS_LABEL.completed },
      { value: "cancelled", label: STATUS_LABEL.cancelled },
    ],
    []
  );

  const fieldFilterSelectOptions = useMemo(() => {
    const rows = [{ value: "", label: "Все поля" }];
    for (const key of fieldKeySelectOptions) {
      const lab = labelByKey[key];
      rows.push({
        value: key,
        label: lab ? `${key} — ${lab}` : `${key} (нет в шаблоне)`,
      });
    }
    return rows;
  }, [fieldKeySelectOptions, labelByKey]);

  const sortSelectOptions = useMemo(
    () => SORT_OPTIONS.map((o) => ({ value: o.value, label: o.label })),
    []
  );

  useEffect(() => {
    let cancelled = false;
    void api
      .listQuestionnaireResponseFieldKeys(agentId)
      .then((keys) => {
        if (!cancelled) setHistoricFieldKeys(keys);
      })
      .catch(() => {
        if (!cancelled) setHistoricFieldKeys([]);
      });
    return () => {
      cancelled = true;
    };
  }, [agentId]);

  useEffect(() => {
    const t = setTimeout(() => setValueSearch(valueSearchDraft.trim()), 400);
    return () => clearTimeout(t);
  }, [valueSearchDraft]);

  useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [agentId, statusFilter, fieldKeyFilter, valueSearch, sort, viewMode]);

  const hasResponseFilters = Boolean(fieldKeyFilter || valueSearch);

  const tableColumns = useMemo(
    () => tableColumnKeys(template.fields, items),
    [template.fields, items]
  );

  const load = async () => {
    try {
      setIsLoading(true);
      setError(null);
      const params: Parameters<typeof api.listQuestionnaireSubmissions>[1] = {
        limit: 100,
        sort,
        include_field_snapshot: viewMode === "table",
      };
      if (statusFilter) {
        params.status = statusFilter as typeof params.status;
      }
      if (fieldKeyFilter) params.field_key = fieldKeyFilter;
      if (valueSearch) params.value_search = valueSearch;
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
      <div className="flex flex-col gap-4 bg-white border border-[#BEBAB7] rounded-sm p-4 shadow-sm">
        <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-3">
          <Select
            label="Статус"
            options={statusSelectOptions}
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            className={CONTROL_BORDER}
          />
          <Select
            label="Поле"
            options={fieldFilterSelectOptions}
            value={fieldKeyFilter}
            onChange={(e) => setFieldKeyFilter(e.target.value)}
            className={CONTROL_BORDER}
          />
          <Input
            label="Поиск по значению"
            type="search"
            value={valueSearchDraft}
            onChange={(e) => setValueSearchDraft(e.target.value)}
            placeholder="Подстрока в последнем ответе…"
            className={CONTROL_BORDER}
          />
          <Select
            label="Сортировка"
            options={sortSelectOptions}
            value={sort}
            onChange={(e) => setSort(e.target.value as QuestionnaireSubmissionSort)}
            className={CONTROL_BORDER}
          />
        </div>
        <SegmentedControl
          label="Вид данных"
          options={VIEW_MODE_SEGMENTS}
          value={viewMode}
          onChange={(v) => setViewMode(v as SubmissionsViewMode)}
          aria-label="Вид отображения списка заполнений"
        />
        <details className="group text-sm text-gray-600 border-t border-[#EEEAE7] pt-3">
          <summary className="cursor-pointer text-[#443C3C] font-medium list-none flex items-center gap-1 [&::-webkit-details-marker]:hidden">
            <span className="select-none">Как устроены фильтры</span>
            <span className="text-xs text-gray-500 group-open:hidden">(раскрыть)</span>
          </summary>
          <p className="mt-2 text-xs leading-relaxed text-gray-600 pl-0.5">
            Фильтр по значению смотрит на последний ответ в сессии для каждого поля. Ключи, которых уже нет в текущей
            анкете, подтягиваются из сохранённых ответов — их можно выбрать в списке «Поле» для поиска по архиву.
          </p>
        </details>
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
          {statusFilter || hasResponseFilters
            ? "Нет сессий, подходящих под выбранные фильтры."
            : "Пока никто не заполнял эту анкету."}
        </div>
      ) : viewMode === "compact" ? (
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
      ) : (
        <div className="rounded-sm border border-[#BEBAB7] bg-white overflow-x-auto">
          <table className="text-sm min-w-max w-full border-collapse">
            <thead className="bg-[#EEEAE7]/50 text-left text-[#443C3C]">
              <tr>
                <th className="sticky left-0 z-30 px-3 py-3 font-medium min-w-[9rem] max-w-[9rem] bg-[#EEEAE7]/95 shadow-[2px_0_4px_rgba(0,0,0,0.06)]">
                  Пользователь
                </th>
                <th className="sticky left-[9rem] z-20 px-3 py-3 font-medium min-w-[10rem] bg-[#EEEAE7]/95 shadow-[2px_0_4px_rgba(0,0,0,0.04)]">
                  Начало
                </th>
                <th className="sticky left-[19rem] z-10 px-3 py-3 font-medium min-w-[10rem] bg-[#EEEAE7]/95 shadow-[2px_0_4px_rgba(0,0,0,0.04)]">
                  Завершение
                </th>
                <th className="px-3 py-3 font-medium whitespace-nowrap">Канал</th>
                <th className="px-3 py-3 font-medium whitespace-nowrap">Тип</th>
                <th className="px-3 py-3 font-medium whitespace-nowrap">Статус</th>
                <th className="px-3 py-3 font-medium whitespace-nowrap">Ответов</th>
                {tableColumns.map((key) => (
                  <th
                    key={key}
                    className="px-3 py-3 font-medium min-w-[8rem] max-w-[14rem] align-top whitespace-normal"
                    title={labelByKey[key] ? `${key} — ${labelByKey[key]}` : key}
                  >
                    <span className="line-clamp-2">{labelByKey[key] || `${key} (архив)`}</span>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {items.map(({ submission, answers_count, field_snapshot }) => {
                const snap = field_snapshot ?? {};
                return (
                  <tr
                    key={submission.submission_id}
                    className="border-t border-[#BEBAB7]/60 hover:bg-[#EEEAE7]/30 cursor-pointer align-top"
                    onClick={() => openDetail(submission.submission_id)}
                  >
                    <td className="sticky left-0 z-20 px-3 py-2.5 font-mono text-xs text-gray-800 min-w-[9rem] max-w-[9rem] bg-white shadow-[2px_0_4px_rgba(0,0,0,0.06)]">
                      {submission.external_user_id}
                    </td>
                    <td className="sticky left-[9rem] z-10 px-3 py-2.5 text-gray-600 text-xs bg-white whitespace-nowrap">
                      {formatTime(submission.started_at)}
                    </td>
                    <td className="sticky left-[19rem] z-10 px-3 py-2.5 text-gray-600 text-xs bg-white whitespace-nowrap">
                      {submission.completed_at
                        ? formatTime(submission.completed_at)
                        : submission.cancelled_at
                        ? formatTime(submission.cancelled_at)
                        : "—"}
                    </td>
                    <td className="px-3 py-2.5 whitespace-nowrap">{submission.channel}</td>
                    <td className="px-3 py-2.5 whitespace-nowrap">
                      {SOURCE_LABEL[submission.source] || submission.source}
                    </td>
                    <td className="px-3 py-2.5 whitespace-nowrap">
                      <StatusBadge status={submission.status} />
                    </td>
                    <td className="px-3 py-2.5 whitespace-nowrap">{answers_count}</td>
                    {tableColumns.map((key) => {
                      const raw = snap[key] ?? "";
                      return (
                        <td
                          key={key}
                          className="px-3 py-2.5 text-gray-800 max-w-[14rem] align-top"
                          title={raw || undefined}
                        >
                          <span className="line-clamp-3 break-words">{raw || "—"}</span>
                        </td>
                      );
                    })}
                  </tr>
                );
              })}
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
