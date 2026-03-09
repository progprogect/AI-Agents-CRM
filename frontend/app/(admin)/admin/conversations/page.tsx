/** Conversations monitoring page with real-time updates and improved UX. */

"use client";

import { useState, useEffect, useMemo } from "react";
import { useRouter } from "next/navigation";
import { useConversationsList, type ConversationFilter } from "@/lib/hooks/useConversationsList";
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
}: {
  stages: CRMStage[];
  currentStageId?: string | null;
  conversationId: string;
  onChanged: () => void;
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
            className="text-xs border border-[#BEBAB7] rounded px-1.5 py-0.5 text-[#443C3C] bg-white outline-none focus:border-[#251D1C] max-w-[130px]"
          >
            {!currentStageId && (
              <option value="" disabled>
                — No stage —
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
  const [filter, setFilter] = useState<ConversationFilter>("all");
  const [crmStageFilter, setCrmStageFilter] = useState<string>("all");
  const [searchQuery, setSearchQuery] = useState("");
  const [takeOverConversationId, setTakeOverConversationId] = useState<string | null>(null);
  const [isTakingOver, setIsTakingOver] = useState(false);
  const [agents, setAgents] = useState<Map<string, Agent>>(new Map());
  const [isLoadingAgents, setIsLoadingAgents] = useState(true);
  const [crmStages, setCrmStages] = useState<CRMStage[]>([]);

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

  const isNeedsHuman = (status: ConversationStatus) => status === "NEEDS_HUMAN";

  if (isLoading && conversations.length === 0) {
    return (
      <div className="flex items-center justify-center h-64">
        <LoadingSpinner size="lg" />
      </div>
    );
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Conversations</h1>
          <p className="text-sm text-gray-600 mt-1">
            {needsHumanCount > 0 && (
              <span className="text-[#F59E0B] font-medium">
                {needsHumanCount} conversation{needsHumanCount !== 1 ? "s" : ""} require{needsHumanCount === 1 ? "s" : ""} attention
              </span>
            )}
            {!needsHumanCount && filteredConversations.length > 0 && (
              <span>{filteredConversations.length} conversation{filteredConversations.length !== 1 ? "s" : ""}</span>
            )}
          </p>
        </div>
        {/* Controls — wrap to next line on mobile */}
        <div className="flex flex-wrap items-center gap-2 sm:gap-3 mt-2 sm:mt-0">
          {/* Connection status indicator */}
          <div className="flex items-center gap-1.5">
            <div
              className={`w-2 h-2 rounded-full ${
                isConnected ? "bg-green-500" : "bg-gray-400"
              }`}
              aria-label={isConnected ? "Live connection" : "Polling mode"}
            />
            <span className="text-sm text-gray-600">
              {isConnected ? "Live" : "Polling"}
            </span>
          </div>

          {/* Filter dropdowns */}
          <Select
            value={filter}
            onChange={(e) => setFilter(e.target.value as ConversationFilter)}
            options={[
              { value: "all", label: "All Conversations" },
              { value: "needs_attention", label: "Requires Attention" },
              { value: "active", label: "Active" },
              { value: "closed", label: "Closed" },
            ]}
          />
          <Select
            value={crmStageFilter}
            onChange={(e) => setCrmStageFilter(e.target.value)}
            options={[
              { value: "all", label: "All CRM Stages" },
              ...crmStages.map((s) => ({ value: s.id, label: s.name })),
            ]}
          />
        </div>
      </div>

      {/* Search bar */}
      <div className="mb-4">
        <Input
          type="text"
          placeholder="Search by agent name or conversation ID..."
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          className="w-full max-w-md"
        />
      </div>

      {error && (
        <div className="bg-red-50 border-l-4 border-red-500 p-4 mb-4 rounded-sm" role="alert">
          <p className="text-sm text-red-700">{error}</p>
        </div>
      )}

      {filteredConversations.length === 0 ? (
        <EmptyState
          icon="💬"
          title={searchQuery ? "No conversations found" : "No conversations yet"}
          description={
            searchQuery
              ? "Try adjusting your search query or filters."
              : "Conversations will appear here once users start chatting."
          }
        />
      ) : (
        <div className="bg-white rounded-sm shadow border border-[#251D1C]/20 overflow-hidden">
          <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-gray-200">
            <thead className="bg-[#EEEAE7]/10">
              <tr>
                <th className="px-6 py-3 text-left text-xs font-medium text-[#443C3C] uppercase tracking-wider">
                  Conversation
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-[#443C3C] uppercase tracking-wider">
                  Agent
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-[#443C3C] uppercase tracking-wider">
                  Channel
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-[#443C3C] uppercase tracking-wider">
                  Status
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-[#443C3C] uppercase tracking-wider">
                  CRM Stage
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-[#443C3C] uppercase tracking-wider">
                  Created
                </th>
                {(filter === "all" || filter === "needs_attention") && (
                  <th className="px-6 py-3 text-left text-xs font-medium text-[#443C3C] uppercase tracking-wider">
                    Waiting
                  </th>
                )}
                <th className="px-6 py-3 text-left text-xs font-medium text-[#443C3C] uppercase tracking-wider">
                  Actions
                </th>
              </tr>
            </thead>
            <tbody className="bg-white divide-y divide-gray-200">
              {filteredConversations.map((conv) => {
                const needsAttention = isNeedsHuman(conv.status);
                const agent = agents.get(conv.agent_id);
                const agentName = agent
                  ? (agent.config?.profile?.agent_display_name || agent.config?.profile?.doctor_display_name || conv.agent_id)
                  : conv.agent_id;
                const agentCompany = agent?.config?.profile?.company_display_name || null;

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
                          <span className="text-lg" aria-label="Requires attention">
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
                        <span className="text-sm text-gray-400">Loading...</span>
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
                            Take Over
                          </Button>
                        )}
                        <Tooltip content={`View conversation ${conv.conversation_id}`}>
                          <Link
                            href={`/admin/conversations/${conv.conversation_id}`}
                            className="inline-flex items-center justify-center w-8 h-8 text-[#251D1C] hover:text-[#443C3C] hover:bg-[#EEEAE7]/10 rounded-sm transition-all duration-200"
                            aria-label="View conversation"
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
      )}

      {/* Take Over Confirmation Modal */}
      <ConfirmModal
        isOpen={!!takeOverConversationId}
        onClose={() => setTakeOverConversationId(null)}
        onConfirm={() => takeOverConversationId && handleTakeOver(takeOverConversationId)}
        title="Take Over Conversation"
        message="Are you sure you want to take over this conversation? You will be able to respond to the user directly."
        confirmText="Take Over"
        cancelText="Cancel"
        isLoading={isTakingOver}
        variant="warning"
      />
    </div>
  );
}
