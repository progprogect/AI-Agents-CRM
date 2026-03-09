/** Conversation detail page with improved layout and human-readable labels. */

"use client";

import { useEffect, useRef, useState } from "react";
import { useParams } from "next/navigation";
import { api, ApiError } from "@/lib/api";
import { LoadingSpinner } from "@/components/shared/LoadingSpinner";
import { Button } from "@/components/shared/Button";
import { StatusBadge } from "@/components/shared/StatusBadge";
import { MarketingStatusBadge } from "@/components/shared/MarketingStatusBadge";
import { MarketingStatusSelect } from "@/components/shared/MarketingStatusSelect";
import { MessageBubble } from "@/components/chat/MessageBubble";
import { MessageInput } from "@/components/chat/MessageInput";
import { EmptyState } from "@/components/shared/EmptyState";
import { UserAvatar } from "@/components/shared/UserAvatar";
import { useAdminConversation } from "@/lib/hooks/useAdminConversation";
import { useMessages } from "@/lib/hooks/useMessages";
import { useAdminWebSocket } from "@/lib/hooks/useAdminWebSocket";
import { handleApiError, getUserFriendlyMessage } from "@/lib/errorHandler";
import type { Conversation, MarketingStatus } from "@/lib/types/conversation";
import type { Message } from "@/lib/types/message";
import type { Agent } from "@/lib/types/agent";
import { getChannelDisplay, isInstagramChannel } from "@/lib/utils/channelDisplay";
import { getConversationDisplayId } from "@/lib/utils/conversationDisplay";
import { getAgentDisplayName, getAgentSpecialty, getClinicDisplayName, getAgentProfileDisplayName } from "@/lib/utils/agentDisplay";
import { formatDateTime } from "@/lib/utils/timeFormat";
import { toConversationStatus } from "@/lib/utils/statusHelpers";

export default function ConversationDetailPage() {
  const params = useParams();
  const conversationId = params.id as string;

  const {
    conversation,
    isLoading: conversationLoading,
    isRefreshing: conversationRefreshing,
    error: conversationError,
    refresh: refreshConversation,
  } = useAdminConversation(conversationId);

  const {
    messages,
    isLoading: messagesLoading,
    isRefreshing: messagesRefreshing,
    error: messagesError,
    refresh: refreshMessages,
    setMessages: setMessagesState,
  } = useMessages(conversationId, true);

  const { onConversationUpdate } = useAdminWebSocket();
  const [actionError, setActionError] = useState<string | null>(null);
  const [agent, setAgent] = useState<Agent | null>(null);
  const [isLoadingAgent, setIsLoadingAgent] = useState(false);
  const [isRefreshingProfile, setIsRefreshingProfile] = useState(false);
  const [isUpdatingMarketingStatus, setIsUpdatingMarketingStatus] = useState(false);
  const [pendingMedia, setPendingMedia] = useState<{ url: string; type: string; name: string } | null>(null);
  const [isUploadingMedia, setIsUploadingMedia] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const isLoading = conversationLoading || messagesLoading;
  const isRefreshing = conversationRefreshing || messagesRefreshing;
  const error = conversationError || messagesError || actionError;

  // Load agent data
  useEffect(() => {
    if (conversation?.agent_id) {
      const loadAgent = async () => {
        try {
          setIsLoadingAgent(true);
          const agentData = await api.getAgent(conversation.agent_id);
          setAgent(agentData);
        } catch (err) {
          console.error("Failed to load agent:", err);
        } finally {
          setIsLoadingAgent(false);
        }
      };
      loadAgent();
    }
  }, [conversation?.agent_id]);

  // Listen for WebSocket updates for this conversation
  useEffect(() => {
    const unsubscribe = onConversationUpdate((updatedConversation: Conversation) => {
      if (updatedConversation.conversation_id === conversationId) {
        refreshConversation();
        refreshMessages();
      }
    });

    return unsubscribe;
  }, [conversationId, onConversationUpdate, refreshConversation, refreshMessages]);

  const handleHandoff = async () => {
    try {
      setActionError(null);
      await api.handoffConversation(conversationId, "admin_user", "Manual handoff");
      await refreshConversation();
      await refreshMessages();
    } catch (err) {
      const errorInfo = handleApiError(err);
      setActionError(getUserFriendlyMessage(errorInfo));
    }
  };

  const handleReturnToAI = async () => {
    try {
      setActionError(null);
      await api.returnToAI(conversationId, "admin_user");
      await refreshConversation();
      await refreshMessages();
    } catch (err) {
      const errorInfo = handleApiError(err);
      setActionError(getUserFriendlyMessage(errorInfo));
    }
  };

  const handleFileSelect = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setIsUploadingMedia(true);
    setActionError(null);
    try {
      const result = await api.uploadChatMedia(file);
      setPendingMedia({ url: result.url, type: result.media_type, name: file.name });
    } catch (err) {
      const errorInfo = handleApiError(err);
      setActionError(getUserFriendlyMessage(errorInfo));
    } finally {
      setIsUploadingMedia(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  };

  const handleSendAdminMessage = async (content: string) => {
    if (!content.trim() && !pendingMedia) return;
    try {
      setActionError(null);
      const media = pendingMedia;
      setPendingMedia(null);

      // Optimistic UI update
      const tempMessageId = `temp-${Date.now()}`;
      const optimisticMessage: Message = {
        message_id: tempMessageId,
        conversation_id: conversationId,
        agent_id: conversation?.agent_id || "",
        role: "admin",
        content: content,
        timestamp: new Date().toISOString(),
        media_url: media?.url,
        media_type: media?.type,
      };
      setMessagesState([...(messages || []), optimisticMessage]);

      await api.sendAdminMessage(
        conversationId,
        "admin_user",
        content,
        media?.url,
        media?.type,
      );

      setTimeout(async () => { await refreshMessages(); }, 500);
    } catch (err) {
      const errorInfo = handleApiError(err);
      setActionError(getUserFriendlyMessage(errorInfo));
      await refreshMessages();
    }
  };

  const canSendAdminMessage =
    conversation?.status === "NEEDS_HUMAN" ||
    conversation?.status === "HUMAN_ACTIVE";

  const handleRefreshProfile = async () => {
    if (!conversation || !isInstagramChannel(conversation.channel)) {
      return;
    }

    try {
      setIsRefreshingProfile(true);
      setActionError(null);
      const profileData = await api.refreshInstagramProfile(conversationId);
      
      if (profileData.error) {
        setActionError(profileData.error);
      } else {
        // Refresh conversation to get updated profile data
        await refreshConversation();
      }
    } catch (err) {
      const errorInfo = handleApiError(err);
      setActionError(getUserFriendlyMessage(errorInfo));
    } finally {
      setIsRefreshingProfile(false);
    }
  };

  const handleMarketingStatusChange = async (
    status: MarketingStatus,
    rejectionReason?: string
  ) => {
    try {
      setIsUpdatingMarketingStatus(true);
      setActionError(null);
      await api.updateMarketingStatus(
        conversationId,
        status,
        "admin_user",
        rejectionReason
      );
      await refreshConversation();
    } catch (err) {
      const errorInfo = handleApiError(err);
      setActionError(getUserFriendlyMessage(errorInfo));
    } finally {
      setIsUpdatingMarketingStatus(false);
    }
  };

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <LoadingSpinner size="lg" />
      </div>
    );
  }

  if (error || !conversation) {
    return (
      <div className="bg-red-50 border-l-4 border-red-500 p-4 rounded-sm" role="alert">
        <p className="text-sm text-red-700">{error || "Conversation not found"}</p>
      </div>
    );
  }

  const agentDisplayName = agent ? getAgentDisplayName(agent) : conversation.agent_id;
  const clinicName = agent ? getClinicDisplayName(agent) : null;
  const agentProfileName = agent ? getAgentProfileDisplayName(agent) : null;
  const specialty = agent ? getAgentSpecialty(agent) : null;

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Conversation Details</h1>
          <p className="text-sm text-gray-500 mt-1 font-mono">
            {getConversationDisplayId(conversation, "detail")}
          </p>
        </div>
        <div className="flex gap-2">
          {conversation.status === "AI_ACTIVE" && (
            <Button variant="primary" onClick={handleHandoff}>
              Handoff to Human
            </Button>
          )}
          {conversation.status === "HUMAN_ACTIVE" && (
            <Button variant="secondary" onClick={handleReturnToAI}>
              Return to AI
            </Button>
          )}
        </div>
      </div>

      {actionError && (
        <div className="bg-red-50 border-l-4 border-red-500 p-4 mb-4 rounded-sm" role="alert">
          <p className="text-sm text-red-700">{actionError}</p>
        </div>
      )}

      {/* Info Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-6">
        {/* Agent Info Card */}
        <div className="bg-white rounded-sm shadow border border-[#251D1C]/20 p-6">
          <h3 className="text-sm font-medium text-gray-500 mb-3">Agent Information</h3>
          {isLoadingAgent ? (
            <LoadingSpinner size="sm" />
          ) : (
            <div className="space-y-2">
              <div>
                <p className="text-xs text-gray-500">Agent Name</p>
                <p className="text-sm font-medium text-gray-900">{agentDisplayName}</p>
              </div>
              {clinicName && (
                <div>
                  <p className="text-xs text-gray-500">Company</p>
                  <p className="text-sm font-medium text-gray-900">{clinicName}</p>
                </div>
              )}
              {agentProfileName && (
                <div>
                  <p className="text-xs text-gray-500">Agent</p>
                  <p className="text-sm font-medium text-gray-900">{agentProfileName}</p>
                </div>
              )}
              {specialty && (
                <div>
                  <p className="text-xs text-gray-500">Specialty</p>
                  <p className="text-sm font-medium text-gray-900">{specialty}</p>
                </div>
              )}
              <div className="pt-2 border-t border-gray-200">
                <p className="text-xs text-gray-500">Agent ID</p>
                <p className="text-xs font-mono text-gray-600">{conversation.agent_id}</p>
              </div>
            </div>
          )}
        </div>

        {/* Conversation Info Card */}
        <div className="bg-white rounded-sm shadow border border-[#251D1C]/20 p-6">
          <h3 className="text-sm font-medium text-gray-500 mb-3">Conversation Information</h3>
          <div className="space-y-2">
            <div>
              <p className="text-xs text-gray-500">Status</p>
              <div className="mt-1">
                <StatusBadge status={toConversationStatus(conversation.status)} />
              </div>
            </div>
            <div>
              <p className="text-xs text-gray-500">Channel</p>
              <p className="text-sm font-medium text-gray-900">
                {getChannelDisplay(conversation.channel)}
              </p>
            </div>
            <div>
              <p className="text-xs text-gray-500">Created</p>
              <p className="text-sm font-medium text-gray-900">
                {formatDateTime(conversation.created_at)}
              </p>
            </div>
            {conversation.closed_at && (
              <div>
                <p className="text-xs text-gray-500">Closed</p>
                <p className="text-sm font-medium text-gray-900">
                  {formatDateTime(conversation.closed_at)}
                </p>
              </div>
            )}
            {conversation.handoff_reason && (
              <div>
                <p className="text-xs text-gray-500">Handoff Reason</p>
                <p className="text-sm font-medium text-gray-900">
                  {conversation.handoff_reason}
                </p>
              </div>
            )}
            <div className="pt-2 border-t border-gray-200">
              <p className="text-xs text-gray-500 mb-2">Marketing Status</p>
              {isUpdatingMarketingStatus ? (
                <div className="flex items-center gap-2">
                  <LoadingSpinner size="sm" />
                  <span className="text-xs text-gray-500">Updating...</span>
                </div>
              ) : (
                <div className="space-y-3">
                  {conversation.marketing_status && (
                    <div>
                      <MarketingStatusBadge
                        status={conversation.marketing_status}
                        size="md"
                      />
                    </div>
                  )}
                  <MarketingStatusSelect
                    value={conversation.marketing_status || "NEW"}
                    onChange={handleMarketingStatusChange}
                    disabled={isUpdatingMarketingStatus}
                    showRejectionReason={true}
                    currentRejectionReason={conversation.rejection_reason}
                  />
                  {conversation.rejection_reason && conversation.marketing_status === "REJECTED" && (
                    <div className="mt-2 p-2 bg-red-50 border border-red-200 rounded-sm">
                      <p className="text-xs text-gray-500 mb-1">Rejection Reason:</p>
                      <p className="text-sm text-gray-900">{conversation.rejection_reason}</p>
                    </div>
                  )}
                </div>
              )}
            </div>
            {/* User Info — shown for all channels with external data */}
            {(conversation.external_user_id || conversation.external_user_name) && (
              <div className="pt-2 border-t border-gray-200">
                <div className="flex items-center justify-between mb-2">
                  <p className="text-xs text-gray-500">
                    {isInstagramChannel(conversation.channel) ? "Instagram User" :
                     conversation.channel === "telegram" ? "Telegram User" :
                     conversation.channel === "whatsapp" ? "WhatsApp Contact" :
                     "Contact"}
                  </p>
                  {isInstagramChannel(conversation.channel) && (
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={handleRefreshProfile}
                      disabled={isRefreshingProfile}
                      isLoading={isRefreshingProfile}
                    >
                      {isRefreshingProfile ? "Refreshing..." : "Refresh"}
                    </Button>
                  )}
                </div>
                <div className="flex items-center gap-3">
                  {(conversation.external_user_name || conversation.external_user_profile_pic) && (
                    <UserAvatar
                      src={conversation.external_user_profile_pic}
                      name={conversation.external_user_name}
                      size="lg"
                    />
                  )}
                  <div className="flex flex-col">
                    {conversation.external_user_name && (
                      <p className="text-sm font-medium text-gray-900">
                        {conversation.external_user_name}
                      </p>
                    )}
                    {conversation.external_user_username && (
                      <p className="text-xs text-gray-500">
                        @{conversation.external_user_username}
                      </p>
                    )}
                    {conversation.external_user_id && (
                      <p className="text-xs text-gray-400 font-mono mt-0.5">
                        {(conversation.channel === "whatsapp" || conversation.channel === "telegram")
                          ? `📞 +${conversation.external_user_id}`
                          : `ID: ${conversation.external_user_id}`}
                      </p>
                    )}
                  </div>
                </div>
                {isInstagramChannel(conversation.channel) && !conversation.external_user_name && (
                  <p className="text-xs text-gray-500 mt-1">
                    Click "Refresh" to fetch Instagram profile info.
                  </p>
                )}
                {conversation.external_conversation_id && (
                  <div className="mt-2">
                    <p className="text-xs text-gray-400 font-mono truncate">
                      Thread: {conversation.external_conversation_id}
                    </p>
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Messages Section */}
      <div className="bg-white rounded-sm shadow border border-[#251D1C]/20 p-6">
        <h2 className="text-lg font-semibold text-gray-900 mb-4">Messages</h2>
        <div className="space-y-4 mb-4 min-h-[200px]">
          {messages.length === 0 ? (
            <EmptyState
              icon="💬"
              title="No messages yet"
              description="Messages will appear here once the conversation starts."
            />
          ) : (
            messages.map((message) => (
              <MessageBubble key={message.message_id} message={message} />
            ))
          )}
        </div>

        {canSendAdminMessage && (
          <div className="border-t border-gray-200 pt-4 mt-4">
            {/* Pending media preview */}
            {pendingMedia && (
              <div className="flex items-center gap-3 mb-3 p-3 bg-[#EEEAE7]/60 border border-[#BEBAB7] rounded-sm">
                {pendingMedia.type === "image" ? (
                  <img src={pendingMedia.url} alt="attachment" className="w-14 h-14 object-cover rounded-sm flex-shrink-0" />
                ) : (
                  <span className="text-2xl flex-shrink-0">📎</span>
                )}
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium text-[#251D1C] truncate">{pendingMedia.name}</p>
                  <p className="text-xs text-gray-500">{pendingMedia.type}</p>
                </div>
                <button
                  onClick={() => setPendingMedia(null)}
                  className="text-gray-400 hover:text-red-500 transition-colors text-lg leading-none"
                  title="Remove attachment"
                >
                  ×
                </button>
              </div>
            )}

            <div className="flex items-center gap-2 mb-2">
              {/* File attachment button */}
              <input
                ref={fileInputRef}
                type="file"
                className="hidden"
                accept="image/*,video/*,audio/*,.pdf,.doc,.docx"
                onChange={handleFileSelect}
              />
              <button
                onClick={() => fileInputRef.current?.click()}
                disabled={isUploadingMedia}
                title="Attach file"
                className="flex-shrink-0 p-2 text-gray-400 hover:text-[#251D1C] hover:bg-[#EEEAE7] rounded-sm transition-colors disabled:opacity-50"
              >
                {isUploadingMedia ? (
                  <span className="inline-block w-5 h-5 border-2 border-[#251D1C] border-t-transparent rounded-full animate-spin" />
                ) : (
                  <svg xmlns="http://www.w3.org/2000/svg" className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M15.172 7l-6.586 6.586a2 2 0 102.828 2.828l6.414-6.586a4 4 0 00-5.656-5.656l-6.415 6.585a6 6 0 108.486 8.486L20.5 13" />
                  </svg>
                )}
              </button>
            </div>

            <MessageInput
              onSend={handleSendAdminMessage}
              placeholder={pendingMedia ? "Add a caption (optional)..." : "Type your message as admin..."}
              disabled={isUploadingMedia}
              allowEmpty={!!pendingMedia}
            />
          </div>
        )}
      </div>
    </div>
  );
}
