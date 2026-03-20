/** Hook for managing conversations list with real-time updates. */

import { useEffect, useState, useCallback, useRef } from "react";
import { api, ApiError } from "@/lib/api";
import { useAdminWebSocket } from "./useAdminWebSocket";
import { showEscalationNotification } from "@/lib/notifications";
import type { Conversation } from "@/lib/types/conversation";

export type ConversationFilter = "all" | "needs_attention" | "active" | "closed";

export type ConversationSortBy = "created_at" | "updated_at";
export type ConversationSortOrder = "asc" | "desc";

function sortConversationsList(
  list: Conversation[],
  options: {
    sortBy: ConversationSortBy;
    sortOrder: ConversationSortOrder;
    attentionFirst: boolean;
  }
): Conversation[] {
  const mult = options.sortOrder === "asc" ? 1 : -1;
  const field = options.sortBy;
  const cmpTime = (a: Conversation, b: Conversation) =>
    mult *
    (new Date(a[field]).getTime() - new Date(b[field]).getTime());

  if (!options.attentionFirst) {
    return [...list].sort(cmpTime);
  }

  const rank = (c: Conversation) =>
    c.status === "NEEDS_HUMAN" ? 0 : c.status === "HUMAN_ACTIVE" ? 1 : 2;

  return [...list].sort((a, b) => {
    const ra = rank(a);
    const rb = rank(b);
    if (ra !== rb) return ra - rb;
    return cmpTime(a, b);
  });
}

interface UseConversationsListOptions {
  filter?: ConversationFilter;
  agentId?: string;
  marketingStatus?: string;
  crmStageId?: string;
  limit?: number;
  sortBy?: ConversationSortBy;
  sortOrder?: ConversationSortOrder;
  createdFrom?: string;
  createdTo?: string;
  /** When true, NEEDS_HUMAN / HUMAN_ACTIVE are shown first, then by sort field. */
  attentionFirst?: boolean;
  enablePolling?: boolean;
  pollingInterval?: number;
}

export function useConversationsList(options: UseConversationsListOptions = {}) {
  const {
    filter = "all",
    agentId,
    marketingStatus,
    crmStageId,
    limit = 100,
    sortBy = "created_at",
    sortOrder = "desc",
    createdFrom,
    createdTo,
    attentionFirst = false,
    enablePolling = true,
    pollingInterval = 5000,
  } = options;

  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [needsHumanCount, setNeedsHumanCount] = useState(0);

  const { isConnected, onConversationUpdate, onNewEscalation, onStatsUpdate } =
    useAdminWebSocket();

  const pollingIntervalRef = useRef<NodeJS.Timeout | null>(null);

  const sortOpts = { sortBy, sortOrder, attentionFirst };

  const loadConversations = useCallback(async () => {
    try {
      setIsLoading(true);
      setError(null);

      const params: Parameters<typeof api.listConversations>[0] = {
        limit,
        sort_by: sortBy,
        sort_order: sortOrder,
      };

      if (agentId) {
        params.agent_id = agentId;
      }

      if (marketingStatus) {
        params.marketing_status = marketingStatus;
      }

      if (crmStageId) {
        params.crm_stage_id = crmStageId;
      }

      if (createdFrom?.trim()) {
        params.created_from = createdFrom.trim();
      }
      if (createdTo?.trim()) {
        params.created_to = createdTo.trim();
      }

      if (filter === "needs_attention") {
        params.status = "NEEDS_HUMAN";
      } else if (filter === "closed") {
        params.status = "CLOSED";
      }

      const data = await api.listConversations(params);

      let filteredData = data;
      if (filter === "active") {
        filteredData = data.filter(
          (c) => c.status === "AI_ACTIVE" || c.status === "HUMAN_ACTIVE"
        );
      }

      const ordered = sortConversationsList(filteredData, sortOpts);
      setConversations(ordered);

      const needsHuman = data.filter((c) => c.status === "NEEDS_HUMAN").length;
      setNeedsHumanCount(needsHuman);
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err.message);
      } else {
        setError("Failed to load conversations");
      }
    } finally {
      setIsLoading(false);
    }
  }, [
    filter,
    agentId,
    marketingStatus,
    crmStageId,
    limit,
    sortBy,
    sortOrder,
    createdFrom,
    createdTo,
    attentionFirst,
  ]);

  useEffect(() => {
    loadConversations();
  }, [loadConversations]);

  useEffect(() => {
    const unsubscribeUpdate = onConversationUpdate((updatedConversation) => {
      setConversations((prev) => {
        const matchesFilter = (conv: Conversation) => {
          if (filter === "needs_attention") {
            return conv.status === "NEEDS_HUMAN";
          }
          if (filter === "active") {
            return conv.status === "AI_ACTIVE" || conv.status === "HUMAN_ACTIVE";
          }
          if (filter === "closed") {
            return conv.status === "CLOSED";
          }
          return true;
        };

        const index = prev.findIndex(
          (c) => c.conversation_id === updatedConversation.conversation_id
        );

        const oldConversation = index >= 0 ? prev[index] : null;
        const wasNeedsHuman = oldConversation?.status === "NEEDS_HUMAN";
        const isNeedsHuman = updatedConversation.status === "NEEDS_HUMAN";

        if (oldConversation) {
          if (!wasNeedsHuman && isNeedsHuman) {
            setNeedsHumanCount((count) => count + 1);
          } else if (wasNeedsHuman && !isNeedsHuman) {
            setNeedsHumanCount((count) => Math.max(0, count - 1));
          }
        } else if (isNeedsHuman) {
          setNeedsHumanCount((count) => count + 1);
        }

        if (index === -1) {
          if (matchesFilter(updatedConversation)) {
            return sortConversationsList(
              [...prev, updatedConversation],
              sortOpts
            );
          }
          return prev;
        }

        const updated = [...prev];
        updated[index] = updatedConversation;

        if (!matchesFilter(updatedConversation)) {
          updated.splice(index, 1);
          return updated;
        }

        return sortConversationsList(updated, sortOpts);
      });
    });

    const unsubscribeEscalation = onNewEscalation((conversation, reason) => {
      showEscalationNotification(conversation.conversation_id, reason).catch(
        (err) => {
          console.error("Failed to show escalation notification:", err);
        }
      );
      loadConversations();
    });

    const unsubscribeStats = onStatsUpdate((stats) => {
      if (stats.needs_human !== undefined) {
        setNeedsHumanCount(stats.needs_human);
      }
    });

    return () => {
      unsubscribeUpdate();
      unsubscribeEscalation();
      unsubscribeStats();
    };
  }, [
    onConversationUpdate,
    onNewEscalation,
    onStatsUpdate,
    filter,
    loadConversations,
    sortBy,
    sortOrder,
    attentionFirst,
  ]);

  useEffect(() => {
    if (!isConnected && enablePolling) {
      pollingIntervalRef.current = setInterval(() => {
        loadConversations();
      }, pollingInterval);

      return () => {
        if (pollingIntervalRef.current) {
          clearInterval(pollingIntervalRef.current);
        }
      };
    } else {
      if (pollingIntervalRef.current) {
        clearInterval(pollingIntervalRef.current);
        pollingIntervalRef.current = null;
      }
    }
  }, [isConnected, enablePolling, pollingInterval, loadConversations]);

  return {
    conversations,
    isLoading,
    error,
    needsHumanCount,
    isConnected,
    refresh: loadConversations,
  };
}
