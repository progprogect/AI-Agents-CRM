/** Conversations monitoring page with real-time updates and improved UX. */

"use client";

import { useState, useEffect, useMemo } from "react";
import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import {
  useConversationsList,
  type ConversationFilter,
  type ConversationSortBy,
  type ConversationSortOrder,
} from "@/lib/hooks/useConversationsList";
import { LoadingSpinner } from "@/components/shared/LoadingSpinner";
import { Button } from "@/components/shared/Button";
import { Select } from "@/components/shared/Select";
import { Input } from "@/components/shared/Input";
import { ConfirmModal } from "@/components/shared/ConfirmModal";
import { StatusBadge } from "@/components/shared/StatusBadge";
import { EmptyState } from "@/components/shared/EmptyState";
import { Tooltip } from "@/components/shared/Tooltip";
import { UserAvatar } from "@/components/shared/UserAvatar";
import { api } from "@/lib/api";
import Link from "next/link";
import type { Conversation, CRMStage } from "@/lib/types/conversation";
import type { Agent } from "@/lib/types/agent";
import { getChannelDisplay } from "@/lib/utils/channelDisplay";
import { getConversationDisplayId } from "@/lib/utils/conversationDisplay";
import { getAgentDisplayName } from "@/lib/utils/agentDisplay";
import { getWaitingTime, formatDate } from "@/lib/utils/timeFormat";
import { toConversationStatus } from "@/lib/utils/statusHelpers";
import type { ConversationStatus } from "@/lib/types/conversation";

// ── CRM Stage inline selector ──────────────────────────────────────────────────

function CRMStageSelector({
  stages,
  currentStageId,
  conversationId,
  onChanged,
  noStageLabel,
  selectClassName,
}: {
  stages: CRMStage[];
  currentStageId?: string | null;
  conversationId: string;
  onChanged: () => void;
  noStageLabel: string;
  /** Override default max width (e.g. w-full on mobile cards). */
  selectClassName?: string;
}) {
  const [loading, setLoading] = useState(false);

  const handleChange = async (e: React.ChangeEvent<HTMLSelectElement>) => {
    const stageId = e.target.value;
    setLoading(true);
    try {
      await api.updateConversationCrmStage(conversationId, stageId);
      onChanged();
    } catch {
      // silently ignore
    } finally {
      setLoading(false);
    }
  };

  const current = stages.find((s) => s.id === currentStageId);

  return (
    <div className="flex items-center gap-2">
      {loading ? (
        <LoadingSpinner size="sm" />
      ) : (
        <>
          {current && (
            <span
              className="inline-block w-2.5 h-2.5 rounded-full flex-shrink-0"
              style={{ backgroundColor: current.color }}
            />
          )}
          <select
            value={currentStageId ?? ""}
            onChange={handleChange}
            className={
              selectClassName ??
              "text-xs border border-[#BEBAB7] rounded px-1.5 py-0.5 text-[#443C3C] bg-white outline-none focus:border-[#251D1C] max-w-[130px]"
            }
          >
            {!currentStageId && (
              <option value="" disabled>
                {noStageLabel}
              </option>
            )}
            {stages.map((s) => (
              <option key={s.id} value={s.id}>
                {s.name}
              </option>
            ))}
          </select>
        </>
      )}
    </div>
  );
}

type SortPreset = "created_desc" | "created_asc" | "updated_desc" | "updated_asc";

const SORT_PRESET_MAP: Record<
  SortPreset,
  { sortBy: ConversationSortBy; sortOrder: ConversationSortOrder }
> = {
  created_desc: { sortBy: "created_at", sortOrder: "desc" },
  created_asc: { sortBy: "created_at", sortOrder: "asc" },
  updated_desc: { sortBy: "updated_at", sortOrder: "desc" },
  updated_asc: { sortBy: "updated_at", sortOrder: "asc" },
};

function isNeedsHumanStatus(status: ConversationStatus): boolean {
  return status === "NEEDS_HUMAN";
}

function getConversationListDerived(conv: Conversation, agents: Map<string, Agent>) {
  const needsAttention = isNeedsHumanStatus(conv.status);
  const agent = agents.get(conv.agent_id);
  const agentName = agent
    ? agent.config?.profile?.agent_display_name ||
      agent.config?.profile?.doctor_display_name ||
      conv.agent_id
    : conv.agent_id;
  const agentCompany = agent?.config?.profile?.company_display_name ?? null;
  return { needsAttention, agentName, agentCompany };
}

const ViewIcon = () => (
  <svg
    xmlns="http://www.w3.org/2000/svg"
    fill="none"
    viewBox="0 0 24 24"
    strokeWidth={2}
    stroke="currentColor"
    className="h-4 w-4"
  >
    <path
      strokeLinecap="round"
      strokeLinejoin="round"
      d="M2.036 12.322a1.012 1.012 0 010-.639C3.423 7.51 7.36 4.5 12 4.5c4.638 0 8.573 3.007 9.963 7.178.07.207.07.431 0 .639C20.577 16.49 16.64 19.5 12 19.5c-4.638 0-8.573-3.007-9.963-7.178z"
    />
    <path
      strokeLinecap="round"
      strokeLinejoin="round"
      d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"
    />
  </svg>
);

export default function ConversationsPage() {
  const router = useRouter();
  const t = useTranslations("Conversations");
  const tCommon = useTranslations("Common");
  const [filter, setFilter] = useState<ConversationFilter>("all");
  const [crmStageFilter, setCrmStageFilter] = useState<string>("all");
  const [searchQuery, setSearchQuery] = useState("");
  const [takeOverConversationId, setTakeOverConversationId] = useState<string | null>(null);
  const [isTakingOver, setIsTakingOver] = useState(false);
  const [agents, setAgents] = useState<Map<string, Agent>>(new Map());
  const [isLoadingAgents, setIsLoadingAgents] = useState(true);
  const [crmStages, setCrmStages] = useState<CRMStage[]>([]);
  const [sortPreset, setSortPreset] = useState<SortPreset>("created_desc");
  const [attentionFirst, setAttentionFirst] = useState(false);
  const [createdFrom, setCreatedFrom] = useState("");
  const [createdTo, setCreatedTo] = useState("");

  const sortCfg = SORT_PRESET_MAP[sortPreset];

  const {
    conversations,
    isLoading,
    error,
    needsHumanCount,
    isConnected,
    refresh,
  } = useConversationsList({
    filter,
    crmStageId: crmStageFilter !== "all" ? crmStageFilter : undefined,
    limit: 100,
    enablePolling: true,
    sortBy: sortCfg.sortBy,
    sortOrder: sortCfg.sortOrder,
    createdFrom: createdFrom || undefined,
    createdTo: createdTo || undefined,
    attentionFirst,
  });

  // Load agents and CRM stages
  useEffect(() => {
    const loadData = async () => {
      try {
        setIsLoadingAgents(true);
        const [agentsList, stagesList] = await Promise.all([
          api.listAgents(false),
          api.listCrmStages().catch(() => []),
        ]);
        const agentsMap = new Map<string, Agent>();
        agentsList.forEach((agent) => agentsMap.set(agent.agent_id, agent));
        setAgents(agentsMap);
        setCrmStages(stagesList);
      } catch (err) {
        console.error("Failed to load data:", err);
      } finally {
        setIsLoadingAgents(false);
      }
    };
    loadData();
  }, []);

  // Filter and search conversations
  const filteredConversations = useMemo(() => {
    let filtered = [...conversations];

    // Apply search filter
    if (searchQuery.trim()) {
      const query = searchQuery.toLowerCase();
      filtered = filtered.filter((conv) => {
        const agent = agents.get(conv.agent_id);
        const agentName = agent ? getAgentDisplayName(agent).toLowerCase() : "";
        const convId = conv.conversation_id.toLowerCase();
        return agentName.includes(query) || convId.includes(query);
      });
    }

    return filtered;
  }, [conversations, searchQuery, agents]);

  const handleTakeOver = async (conversationId: string) => {
    try {
      setIsTakingOver(true);
      await api.handoffConversation(conversationId, "admin_user", "Quick takeover");
      setTakeOverConversationId(null);
      await refresh();
      router.push(`/admin/conversations/${conversationId}`);
    } catch (err) {
      console.error("Failed to take over conversation:", err);
      alert("Failed to take over conversation. Please try again.");
    } finally {
      setIsTakingOver(false);
    }
  };

  if (isLoading && conversations.length === 0) {
    return (
      <div className="flex items-center justify-center h-64">
        <LoadingSpinner size="lg" />
      </div>
    );
  }

  return (
    <div className="w-full min-w-0 max-w-full">
      <header className="mb-4 min-w-0 sm:mb-5">
        <h1 className="min-w-0 break-words text-xl font-bold text-gray-900 sm:text-2xl">
          {t("title")}
        </h1>
        <p className="text-xs sm:text-sm text-gray-600 mt-1">
          {needsHumanCount > 0 && (
            <span className="text-[#F59E0B] font-medium">
              {t("requireAttentionCount", { count: needsHumanCount })}
            </span>
          )}
          {!needsHumanCount && filteredConversations.length > 0 && (
            <span>{t("conversationCount", { count: filteredConversations.length })}</span>
          )}
        </p>
      </header>

      <section
        className="mb-6 min-w-0 rounded-sm border border-[#251D1C]/15 bg-[#FAF9F8] p-3 shadow-sm sm:p-5"
        aria-label={t("filtersPanelAria")}
      >
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between border-b border-[#251D1C]/10 pb-4 mb-5">
          <h2 className="text-xs font-semibold uppercase tracking-wider text-[#443C3C]">
            {t("filtersPanelTitle")}
          </h2>
          <div
            className={`inline-flex w-fit items-center gap-2 rounded-full border px-3 py-1.5 text-xs font-medium ${
              isConnected
                ? "border-emerald-200/80 bg-white text-emerald-900 shadow-sm"
                : "border-gray-200 bg-white text-gray-600"
            }`}
            title={isConnected ? t("liveConnection") : t("pollingMode")}
          >
            <span
              className={`h-2 w-2 shrink-0 rounded-full ${
                isConnected ? "bg-emerald-500" : "bg-gray-400"
              }`}
              aria-hidden
            />
            <span>{isConnected ? t("live") : t("polling")}</span>
          </div>
        </div>

        <div className="mb-5">
          <Input
            label={t("searchLabel")}
            type="text"
            placeholder={t("searchPlaceholder")}
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full"
            autoComplete="off"
          />
        </div>

        <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3 mb-5">
          <Select
            label={t("status")}
            value={filter}
            onChange={(e) => setFilter(e.target.value as ConversationFilter)}
            options={[
              { value: "all", label: t("allConversations") },
              { value: "needs_attention", label: t("requiresAttention") },
              { value: "active", label: t("active") },
              { value: "closed", label: t("closed") },
            ]}
          />
          <Select
            label={t("crmStage")}
            value={crmStageFilter}
            onChange={(e) => setCrmStageFilter(e.target.value)}
            options={[
              { value: "all", label: t("allCrmStages") },
              ...crmStages.map((s) => ({ value: s.id, label: s.name })),
            ]}
          />
          <div className="min-w-0 md:col-span-2 xl:col-span-1">
            <Select
              label={t("fieldSort")}
              value={sortPreset}
              onChange={(e) => setSortPreset(e.target.value as SortPreset)}
              options={[
                { value: "created_desc", label: t("sortCreatedNewest") },
                { value: "created_asc", label: t("sortCreatedOldest") },
                { value: "updated_desc", label: t("sortUpdatedNewest") },
                { value: "updated_asc", label: t("sortUpdatedOldest") },
              ]}
            />
          </div>
        </div>

        <div className="border-t border-[#251D1C]/10 pt-5">
          <p className="text-xs font-semibold uppercase tracking-wider text-[#443C3C] mb-3">
            {t("dateRangeSection")}
          </p>
          <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between lg:gap-6">
            <div className="flex min-w-0 flex-1 flex-col gap-4 sm:flex-row sm:flex-wrap sm:items-end">
              <div className="w-full min-w-0 sm:max-w-[200px] sm:flex-1">
                <Input
                  type="date"
                  label={t("createdFromLabel")}
                  value={createdFrom}
                  onChange={(e) => setCreatedFrom(e.target.value)}
                  className="w-full"
                />
              </div>
              <span
                className="hidden shrink-0 self-center pb-2 text-sm text-gray-400 sm:block"
                aria-hidden
              >
                —
              </span>
              <div className="w-full min-w-0 sm:max-w-[200px] sm:flex-1">
                <Input
                  type="date"
                  label={t("createdToLabel")}
                  value={createdTo}
                  onChange={(e) => setCreatedTo(e.target.value)}
                  className="w-full"
                />
              </div>
              <Button
                type="button"
                variant="secondary"
                size="sm"
                className="h-[42px] w-full shrink-0 sm:w-auto"
                onClick={() => {
                  setCreatedFrom("");
                  setCreatedTo("");
                }}
              >
                {t("resetDateFilter")}
              </Button>
            </div>

            <div className="lg:border-l lg:border-[#251D1C]/10 lg:pl-6">
              <span className="mb-1 block text-sm font-medium text-gray-700">
                {t("fieldOptions")}
              </span>
              <label className="flex min-h-[42px] cursor-pointer items-center gap-3 rounded-sm border border-gray-300 bg-white px-3 py-2 shadow-sm transition-colors hover:border-gray-400">
                <input
                  type="checkbox"
                  checked={attentionFirst}
                  onChange={(e) => setAttentionFirst(e.target.checked)}
                  className="h-4 w-4 shrink-0 rounded border-gray-300 text-[#251D1C] focus:ring-[#251D1C]"
                />
                <span className="text-sm text-gray-800 select-none">{t("attentionFirst")}</span>
              </label>
            </div>
          </div>
        </div>
      </section>

      {error && (
        <div className="bg-red-50 border-l-4 border-red-500 p-4 mb-4 rounded-sm" role="alert">
          <p className="text-sm text-red-700">{error}</p>
        </div>
      )}

      {filteredConversations.length === 0 ? (
        <EmptyState
          icon="💬"
          title={searchQuery ? t("noConversationsFound") : t("noConversationsYet")}
          description={
            searchQuery ? t("adjustSearch") : t("conversationsWillAppear")
          }
        />
      ) : (
        <>
          {/* Mobile: stacked cards */}
          <div className="flex flex-col gap-3 md:hidden">
            {filteredConversations.map((conv) => {
              const { needsAttention, agentName, agentCompany } = getConversationListDerived(
                conv,
                agents,
              );
              const showWaitingCol = filter === "all" || filter === "needs_attention";

              return (
                <article
                  key={conv.conversation_id}
                  className={`min-w-0 rounded-sm border border-[#251D1C]/20 bg-white p-4 shadow-sm ${
                    needsAttention
                      ? "border-l-4 border-l-[#F59E0B] bg-[#F59E0B]/[0.07]"
                      : ""
                  }`}
                >
                  <div className="flex min-w-0 items-start justify-between gap-3">
                    <div className="flex min-w-0 flex-1 items-center gap-2">
                      {needsAttention && (
                        <span className="shrink-0 text-lg" aria-label={t("requiresAttentionAria")}>
                          ⚠️
                        </span>
                      )}
                      {(conv.external_user_name || conv.external_user_profile_pic) && (
                        <UserAvatar
                          src={conv.external_user_profile_pic}
                          name={conv.external_user_name}
                          size="sm"
                        />
                      )}
                      <div className="flex min-w-0 flex-1 flex-col">
                        <p
                          className={`truncate text-sm ${
                            needsAttention ? "font-bold text-gray-900" : "font-medium text-gray-900"
                          }`}
                        >
                          {conv.external_user_name
                            ? conv.external_user_name
                            : getConversationDisplayId(conv, "list")}
                        </p>
                        {conv.external_user_username && (
                          <p className="truncate text-xs text-gray-500">@{conv.external_user_username}</p>
                        )}
                        {!conv.external_user_username &&
                          conv.external_user_id &&
                          (conv.channel === "whatsapp" || conv.channel === "telegram") && (
                            <p className="truncate text-xs text-gray-500">📞 +{conv.external_user_id}</p>
                          )}
                        {!conv.external_user_name && (
                          <p className="truncate font-mono text-xs text-gray-500">
                            {conv.conversation_id.substring(0, 8)}…
                          </p>
                        )}
                      </div>
                    </div>
                    <Tooltip content={`${t("viewConversation")} ${conv.conversation_id}`}>
                      <Link
                        href={`/admin/conversations/${conv.conversation_id}`}
                        className="inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-sm text-[#251D1C] transition-colors hover:bg-[#EEEAE7]/40"
                        aria-label={t("viewConversation")}
                      >
                        <ViewIcon />
                      </Link>
                    </Tooltip>
                  </div>

                  <dl className="mt-4 grid grid-cols-1 gap-3 border-t border-gray-100 pt-4 text-sm">
                    <div className="min-w-0">
                      <dt className="text-xs font-semibold uppercase tracking-wide text-[#443C3C]/80">
                        {t("agent")}
                      </dt>
                      <dd className="mt-0.5 min-w-0 break-words text-gray-900">
                        {isLoadingAgents ? (
                          <span className="text-gray-400">{tCommon("loading")}</span>
                        ) : (
                          <>
                            <span className="font-medium">{agentName}</span>
                            {agentCompany && (
                              <span className="mt-0.5 block text-xs text-gray-500">{agentCompany}</span>
                            )}
                          </>
                        )}
                      </dd>
                    </div>
                    <div className="flex flex-wrap gap-x-6 gap-y-2">
                      <div>
                        <dt className="text-xs font-semibold uppercase tracking-wide text-[#443C3C]/80">
                          {t("channel")}
                        </dt>
                        <dd className="mt-0.5 text-gray-700">{getChannelDisplay(conv.channel)}</dd>
                      </div>
                      <div>
                        <dt className="text-xs font-semibold uppercase tracking-wide text-[#443C3C]/80">
                          {t("status")}
                        </dt>
                        <dd className="mt-0.5">
                          <StatusBadge status={toConversationStatus(conv.status)} size="sm" />
                        </dd>
                      </div>
                    </div>
                    <div className="min-w-0">
                      <dt className="text-xs font-semibold uppercase tracking-wide text-[#443C3C]/80">
                        {t("crmStage")}
                      </dt>
                      <dd className="mt-1 min-w-0">
                        {crmStages.length > 0 ? (
                          <CRMStageSelector
                            stages={crmStages}
                            currentStageId={conv.crm_stage_id}
                            conversationId={conv.conversation_id}
                            onChanged={refresh}
                            noStageLabel={tCommon("noStage")}
                            selectClassName="w-full max-w-full min-w-0 text-xs border border-[#BEBAB7] rounded px-1.5 py-0.5 text-[#443C3C] bg-white outline-none focus:border-[#251D1C]"
                          />
                        ) : (
                          <span className="text-xs text-gray-400">—</span>
                        )}
                      </dd>
                    </div>
                    <div className="flex flex-wrap gap-x-6 gap-y-2">
                      <div>
                        <dt className="text-xs font-semibold uppercase tracking-wide text-[#443C3C]/80">
                          {t("created")}
                        </dt>
                        <dd className="mt-0.5 text-gray-600">{formatDate(conv.created_at)}</dd>
                      </div>
                      {showWaitingCol && (
                        <div>
                          <dt className="text-xs font-semibold uppercase tracking-wide text-[#443C3C]/80">
                            {t("waiting")}
                          </dt>
                          <dd className="mt-0.5">
                            {needsAttention ? (
                              <span className="font-medium text-[#F59E0B]">
                                {getWaitingTime(conv.updated_at)}
                              </span>
                            ) : (
                              <span className="text-gray-400">-</span>
                            )}
                          </dd>
                        </div>
                      )}
                    </div>
                  </dl>

                  {needsAttention && (
                    <div className="mt-4 border-t border-gray-100 pt-4">
                      <Button
                        variant="primary"
                        size="sm"
                        className="w-full sm:w-auto"
                        onClick={() => setTakeOverConversationId(conv.conversation_id)}
                        disabled={isTakingOver}
                      >
                        {t("takeOver")}
                      </Button>
                    </div>
                  )}
                </article>
              );
            })}
          </div>

          {/* Tablet/desktop: table */}
          <div className="hidden min-w-0 overflow-hidden rounded-sm border border-[#251D1C]/20 bg-white shadow-sm md:block">
          <div className="overflow-x-auto">
          <table className="min-w-[640px] w-full divide-y divide-gray-200">
            <thead className="bg-[#EEEAE7]/10">
              <tr>
                <th className="px-6 py-3 text-left text-xs font-medium text-[#443C3C] uppercase tracking-wider">
                  {t("conversation")}
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-[#443C3C] uppercase tracking-wider">
                  {t("agent")}
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-[#443C3C] uppercase tracking-wider">
                  {t("channel")}
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-[#443C3C] uppercase tracking-wider">
                  {t("status")}
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-[#443C3C] uppercase tracking-wider">
                  {t("crmStage")}
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-[#443C3C] uppercase tracking-wider">
                  {t("created")}
                </th>
                {(filter === "all" || filter === "needs_attention") && (
                  <th className="px-6 py-3 text-left text-xs font-medium text-[#443C3C] uppercase tracking-wider">
                    {t("waiting")}
                  </th>
                )}
                <th className="px-6 py-3 text-left text-xs font-medium text-[#443C3C] uppercase tracking-wider">
                  {tCommon("actions")}
                </th>
              </tr>
            </thead>
            <tbody className="bg-white divide-y divide-gray-200">
              {filteredConversations.map((conv) => {
                const { needsAttention, agentName, agentCompany } = getConversationListDerived(
                  conv,
                  agents,
                );

                return (
                  <tr
                    key={conv.conversation_id}
                    className={`transition-colors duration-150 ${
                      needsAttention
                        ? "bg-[#F59E0B]/10 hover:bg-[#F59E0B]/15 border-l-4 border-[#F59E0B]"
                        : "hover:bg-[#EEEAE7]/5"
                    }`}
                  >
                    <td className="px-6 py-4">
                      <div className="flex items-center gap-2">
                        {needsAttention && (
                          <span className="text-lg" aria-label={t("requiresAttentionAria")}>
                            ⚠️
                          </span>
                        )}
                        {/* Show avatar when user profile is available (any channel) */}
                        {(conv.external_user_name || conv.external_user_profile_pic) && (
                          <UserAvatar
                            src={conv.external_user_profile_pic}
                            name={conv.external_user_name}
                            size="sm"
                          />
                        )}
                        <div className="flex flex-col">
                          <span
                            className={`text-sm ${
                              needsAttention ? "font-bold text-gray-900" : "font-medium text-gray-900"
                            }`}
                          >
                            {conv.external_user_name
                              ? conv.external_user_name
                              : getConversationDisplayId(conv, "list")}
                          </span>
                          {conv.external_user_username && (
                            <span className="text-xs text-gray-500">
                              @{conv.external_user_username}
                            </span>
                          )}
                          {/* Show phone for WhatsApp/Telegram */}
                          {!conv.external_user_username && conv.external_user_id &&
                            (conv.channel === "whatsapp" || conv.channel === "telegram") && (
                            <span className="text-xs text-gray-500">
                              📞 +{conv.external_user_id}
                            </span>
                          )}
                          {!conv.external_user_name && (
                            <span className="text-xs text-gray-500 font-mono">
                              {conv.conversation_id.substring(0, 8)}...
                            </span>
                          )}
                        </div>
                      </div>
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap">
                      {isLoadingAgents ? (
                        <span className="text-sm text-gray-400">{tCommon("loading")}</span>
                      ) : (
                        <div className="flex flex-col">
                          <span className="text-sm text-gray-900 font-medium" title={conv.agent_id}>
                            {agentName}
                          </span>
                          {agentCompany && (
                            <span className="text-xs text-gray-500">{agentCompany}</span>
                          )}
                        </div>
                      )}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-600">
                      {getChannelDisplay(conv.channel)}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap">
                      <StatusBadge status={toConversationStatus(conv.status)} size="sm" />
                    </td>
                    <td className="px-6 py-4">
                      <div className="min-w-[150px]">
                        {crmStages.length > 0 ? (
                          <CRMStageSelector
                            stages={crmStages}
                            currentStageId={conv.crm_stage_id}
                            conversationId={conv.conversation_id}
                            onChanged={refresh}
                            noStageLabel={tCommon("noStage")}
                          />
                        ) : (
                          <span className="text-xs text-gray-400">—</span>
                        )}
                      </div>
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                      {formatDate(conv.created_at)}
                    </td>
                    {(filter === "all" || filter === "needs_attention") && (
                      <td className="px-6 py-4 whitespace-nowrap">
                        {needsAttention ? (
                          <span className="text-[#F59E0B] font-medium">
                            {getWaitingTime(conv.updated_at)}
                          </span>
                        ) : (
                          <span className="text-gray-400">-</span>
                        )}
                      </td>
                    )}
                    <td className="px-6 py-4 whitespace-nowrap">
                      <div className="flex items-center gap-3">
                        {needsAttention && (
                          <Button
                            variant="primary"
                            size="sm"
                            onClick={() => setTakeOverConversationId(conv.conversation_id)}
                            disabled={isTakingOver}
                          >
                            {t("takeOver")}
                          </Button>
                        )}
                        <Tooltip content={`${t("viewConversation")} ${conv.conversation_id}`}>
                          <Link
                            href={`/admin/conversations/${conv.conversation_id}`}
                            className="inline-flex items-center justify-center w-8 h-8 text-[#251D1C] hover:text-[#443C3C] hover:bg-[#EEEAE7]/10 rounded-sm transition-all duration-200"
                            aria-label={t("viewConversation")}
                          >
                            <ViewIcon />
                          </Link>
                        </Tooltip>
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          </div>
        </div>
        </>
      )}

      {/* Take Over Confirmation Modal */}
      <ConfirmModal
        isOpen={!!takeOverConversationId}
        onClose={() => setTakeOverConversationId(null)}
        onConfirm={() => takeOverConversationId && handleTakeOver(takeOverConversationId)}
        title={t("takeOverTitle")}
        message={t("takeOverMessage")}
        confirmText={t("takeOver")}
        cancelText={tCommon("cancel")}
        isLoading={isTakingOver}
        variant="warning"
      />
    </div>
  );
}
