/** Paginated list of distinct end users (admin stats drill-down). */

"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useTranslations } from "next-intl";
import { api, ApiError } from "@/lib/api";
import { LoadingSpinner } from "@/components/shared/LoadingSpinner";
import type { EndUserRow } from "@/lib/types/stats";

const PAGE_SIZE = 50;

function formatSeen(iso: string | null): string {
  if (!iso) return "—";
  try {
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return iso;
    return d.toLocaleString();
  } catch {
    return iso;
  }
}

export default function StatsEndUsersPage() {
  const t = useTranslations("Stats");
  const [offset, setOffset] = useState(0);
  const [total, setTotal] = useState(0);
  const [items, setItems] = useState<EndUserRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await api.getAdminStatsEndUsers({ limit: PAGE_SIZE, offset });
      setTotal(data.total);
      setItems(data.items);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t("endUsersLoadError"));
    } finally {
      setLoading(false);
    }
  }, [offset, t]);

  useEffect(() => {
    void load();
  }, [load]);

  const from = total === 0 ? 0 : offset + 1;
  const to = offset + items.length;
  const canPrev = offset > 0;
  const canNext = offset + items.length < total;

  return (
    <div>
      <div className="mb-6 flex flex-wrap items-center justify-between gap-3">
        <div>
          <Link
            href="/admin/stats"
            className="text-sm text-[#6B6560] hover:text-[#251D1C] mb-1 inline-block"
          >
            ← {t("endUsersBack")}
          </Link>
          <h1 className="text-2xl font-bold text-gray-900">{t("endUsersTitle")}</h1>
          <p className="text-sm text-gray-500 mt-1">{t("uniqueEndUsersHint")}</p>
        </div>
      </div>

      {loading && (
        <div className="flex justify-center py-16">
          <LoadingSpinner size="lg" />
        </div>
      )}

      {!loading && error && (
        <div className="bg-red-50 border-l-4 border-red-500 p-4">
          <p className="text-sm text-red-700">{error}</p>
        </div>
      )}

      {!loading && !error && items.length === 0 && (
        <p className="text-sm text-gray-600">{t("endUsersEmpty")}</p>
      )}

      {!loading && !error && items.length > 0 && (
        <>
          <div className="overflow-x-auto rounded-sm border border-gray-200 bg-white">
            <table className="min-w-full text-sm">
              <thead className="bg-gray-50 text-left text-xs font-semibold uppercase tracking-wide text-gray-600">
                <tr>
                  <th className="px-4 py-3">{t("colAgent")}</th>
                  <th className="px-4 py-3">{t("colChannel")}</th>
                  <th className="px-4 py-3">{t("colExternalId")}</th>
                  <th className="px-4 py-3">{t("colDisplayName")}</th>
                  <th className="px-4 py-3">{t("colUsername")}</th>
                  <th className="px-4 py-3">{t("colLastSeen")}</th>
                  <th className="px-4 py-3 text-right">{t("colConversations")}</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {items.map((row) => (
                  <tr key={`${row.agent_id}:${row.channel}:${row.external_user_id}`} className="hover:bg-gray-50">
                    <td className="px-4 py-2 text-gray-900">
                      {row.agent_display_name || row.agent_id}
                    </td>
                    <td className="px-4 py-2 text-gray-700">{row.channel}</td>
                    <td className="px-4 py-2 font-mono text-xs text-gray-800 break-all max-w-[180px]">
                      {row.external_user_id}
                    </td>
                    <td className="px-4 py-2 text-gray-700">{row.display_name || "—"}</td>
                    <td className="px-4 py-2 text-gray-700">{row.username || "—"}</td>
                    <td className="px-4 py-2 text-gray-600 whitespace-nowrap">
                      {formatSeen(row.last_seen_at)}
                    </td>
                    <td className="px-4 py-2 text-right tabular-nums">{row.conversation_count}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="mt-4 flex flex-wrap items-center justify-between gap-3 text-sm text-gray-600">
            <span>{t("pageRange", { from, to, total })}</span>
            <div className="flex gap-2">
              <button
                type="button"
                disabled={!canPrev}
                onClick={() => setOffset((o) => Math.max(0, o - PAGE_SIZE))}
                className="rounded border border-gray-300 px-3 py-1.5 font-medium text-gray-800 hover:bg-gray-50 disabled:opacity-40 disabled:cursor-not-allowed"
              >
                {t("prevPage")}
              </button>
              <button
                type="button"
                disabled={!canNext}
                onClick={() => setOffset((o) => o + PAGE_SIZE)}
                className="rounded border border-gray-300 px-3 py-1.5 font-medium text-gray-800 hover:bg-gray-50 disabled:opacity-40 disabled:cursor-not-allowed"
              >
                {t("nextPage")}
              </button>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
