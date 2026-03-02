/** Hook for managing conversations list with real-time updates. */

import { useEffect, useState, useCallback, useRef } from "react";
import { api, ApiError } from "@/lib/api";
import { useAdminWebSocket } from "./useAdminWebSocket";
import { showEscalationNotification } from "@/lib/notifications";
import type { Conversation } from "@/lib/types/conversation";

export type ConversationFilter = "all" | "needs_attention" | "active" | "closed";

interface UseConversationsListOptions {
  filter?: ConversationFilter;
  agentId?: string;
  marketingStatus?: string;
  crmStageId?: string;
  limit?: number;
  enablePolling?: boolean; // Fallback if WebSocket is not available
  pollingInterval?: number; // Polling interval in ms (default: 5000)
}

export function useConversationsList(options: UseConversationsListOptions = {}) {
  const {
    filter = "all",
    agentId,
    marketingStatus,
    crmStageId,
    limit = 100,
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

  const loadConversations = useCallback(async () => {
    try {
      setIsLoading(true);
      setError(null);
      
      const params: {
        agent_id?: string;
        status?: string;
        marketing_status?: string;
        crm_stage_id?: string;
        limit?: number;
      } = {
        limit,
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

      // Apply filter
      if (filter === "needs_attention") {
        params.status = "NEEDS_HUMAN";
      } else if (filter === "active") {
        // For active, we'll filter on frontend since API doesn't support multiple statuses
      } else if (filter === "closed") {
        params.status = "CLOSED";
      }

      const data = await api.listConversations(params);
      
      // Apply frontend filtering for "active" filter
      let filteredData = data;
      if (filter === "active") {
        filteredData = data.filter(
          (c) => c.status === "AI_ACTIVE" || c.status === "HUMAN_ACTIVE"
        );
      }

      // Sort conversations: NEEDS_HUMAN first, then HUMAN_ACTIVE, then others
      filteredData.sort((a, b) => {
        if (a.status === "NEEDS_HUMAN" && b.status !== "NEEDS_HUMAN") return -1;
        if (a.status !== "NEEDS_HUMAN" && b.status === "NEEDS_HUMAN") return 1;
        if (a.status === "HUMAN_ACTIVE" && b.status !== "HUMAN_ACTIVE") return -1;
        if (a.status !== "HUMAN_ACTIVE" && b.status === "HUMAN_ACTIVE") return 1;
        // Sort by updated_at descending
        return (
          new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime()
        );
      });

      setConversations(filteredData);
      
      // Update needs_human count
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
  }, [filter, agentId, marketingStatus, crmStageId, limit]);

  // Initial load
  useEffect(() => {
    loadConversations();
  }, [loadConversations]);

  // Set up WebSocket listeners
  useEffect(() => {
    // Handle conversation updates
    const unsubscribeUpdate = onConversationUpdate((updatedConversation) => {
      setConversations((prev) => {
        // Check if conversation matches current filter
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
          return true; // "all"
        };

        // Find and update existing conversation
        const index = prev.findIndex(
          (c) => c.conversation_id === updatedConversation.conversation_id
        );

        // Track status change for counter update (outside setState)
        const oldConversation = index >= 0 ? prev[index] : null;
        const wasNeedsHuman = oldConversation?.status === "NEEDS_HUMAN";
        const isNeedsHuman = updatedConversation.status === "NEEDS_HUMAN";

        // Update needs_human count based on status change (outside setState)
        if (oldConversation) {
          if (!wasNeedsHuman && isNeedsHuman) {
            // Status changed to NEEDS_HUMAN - increment
            setNeedsHumanCount((count) => count + 1);
          } else if (wasNeedsHuman && !isNeedsHuman) {
            // Status changed from NEEDS_HUMAN - decrement
            setNeedsHumanCount((count) => Math.max(0, count - 1));
          }
        } else if (isNeedsHuman) {
          // New conversation with NEEDS_HUMAN status
          setNeedsHumanCount((count) => count + 1);
        }

        if (index === -1) {
          // New conversation - add if matches filter
          if (matchesFilter(updatedConversation)) {
            const newList = [...prev, updatedConversation];
            // Re-sort
            newList.sort((a, b) => {
              if (a.status === "NEEDS_HUMAN" && b.status !== "NEEDS_HUMAN")
                return -1;
              if (a.status !== "NEEDS_HUMAN" && b.status === "NEEDS_HUMAN")
                return 1;
              if (a.status === "HUMAN_ACTIVE" && b.status !== "HUMAN_ACTIVE")
                return -1;
              if (a.status !== "HUMAN_ACTIVE" && b.status === "HUMAN_ACTIVE")
                return 1;
              return (
                new Date(b.updated_at).getTime() -
                new Date(a.updated_at).getTime()
              );
            });
            return newList;
          }
          return prev;
        }

        // Update existing conversation
        const updated = [...prev];
        updated[index] = updatedConversation;

        // Remove if no longer matches filter
        if (!matchesFilter(updatedConversation)) {
          updated.splice(index, 1);
        } else {
          // Re-sort
          updated.sort((a, b) => {
            if (a.status === "NEEDS_HUMAN" && b.status !== "NEEDS_HUMAN")
              return -1;
            if (a.status !== "NEEDS_HUMAN" && b.status === "NEEDS_HUMAN")
              return 1;
            if (a.status === "HUMAN_ACTIVE" && b.status !== "HUMAN_ACTIVE")
              return -1;
            if (a.status !== "HUMAN_ACTIVE" && b.status === "HUMAN_ACTIVE")
              return 1;
            return (
              new Date(b.updated_at).getTime() -
              new Date(a.updated_at).getTime()
            );
          });
        }

        return updated;
      });
    });

    // Handle new escalations
    const unsubscribeEscalation = onNewEscalation((conversation, reason) => {
      // Show notification for new escalation
      showEscalationNotification(conversation.conversation_id, reason).catch(
        (err) => {
          console.error("Failed to show escalation notification:", err);
        }
      );
      // Reload conversations to ensure we have the latest data
      loadConversations();
    });

    // Handle stats updates
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
  }, [onConversationUpdate, onNewEscalation, onStatsUpdate, filter, loadConversations]);

  // Fallback polling if WebSocket is not connected
  useEffect(() => {
    if (!isConnected && enablePolling) {
      // Start polling
      pollingIntervalRef.current = setInterval(() => {
        loadConversations();
      }, pollingInterval);

      return () => {
        if (pollingIntervalRef.current) {
          clearInterval(pollingIntervalRef.current);
        }
      };
    } else {
      // Stop polling if WebSocket is connected
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

