/** Chat page for specific agent with improved header and agent info. */

"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { ChatWindow } from "@/components/chat/ChatWindow";
import { LoadingSpinner } from "@/components/shared/LoadingSpinner";
import { Button } from "@/components/shared/Button";
import { api, ApiError } from "@/lib/api";
import { getAgentDisplayName, getAgentInitials, getAgentSpecialty } from "@/lib/utils/agentDisplay";
import { toConversationStatus } from "@/lib/utils/statusHelpers";
import type { Agent } from "@/lib/types/agent";
import type { Conversation } from "@/lib/types/conversation";

export default function ChatPage() {
  const params = useParams();
  const router = useRouter();
  const agentId = params.agentId as string;

  const [agent, setAgent] = useState<Agent | null>(null);
  const [conversation, setConversation] = useState<Conversation | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const loadAgentAndConversation = async () => {
      try {
        setIsLoading(true);

        // Load agent
        const agentData = await api.getAgent(agentId);
        setAgent(agentData);

        // Try to find existing conversation or create new one
        try {
          const conversations = await api.listConversations({
            agent_id: agentId,
            status: "AI_ACTIVE",
            limit: 1,
          });

          if (conversations.length > 0) {
            setConversation(conversations[0]);
          } else {
            // Create new conversation
            const newConversation = await api.createConversation({
              agent_id: agentId,
            });
            setConversation({
              conversation_id: newConversation.conversation_id,
              agent_id: newConversation.agent_id,
              status: toConversationStatus(newConversation.status),
              created_at: new Date().toISOString(),
              updated_at: new Date().toISOString(),
            });
          }
        } catch (err) {
          // Create new conversation if listing fails
          const newConversation = await api.createConversation({
            agent_id: agentId,
          });
          setConversation({
            conversation_id: newConversation.conversation_id,
            agent_id: newConversation.agent_id,
            status: toConversationStatus(newConversation.status),
            created_at: new Date().toISOString(),
            updated_at: new Date().toISOString(),
          });
        }
      } catch (err) {
        if (err instanceof ApiError) {
          setError(err.message);
        } else {
          setError("Failed to load chat");
        }
      } finally {
        setIsLoading(false);
      }
    };

    if (agentId) {
      loadAgentAndConversation();
    }
  }, [agentId]);

  if (isLoading) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <LoadingSpinner size="lg" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex items-center justify-center min-h-screen p-4 bg-white">
        <div className="text-center max-w-md">
          <h2 className="text-2xl font-bold text-gray-900 mb-2">Error</h2>
          <p className="text-gray-600 mb-4">{error}</p>
          <Button variant="primary" onClick={() => router.push("/")}>
            Go Back
          </Button>
        </div>
      </div>
    );
  }

  if (!conversation) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="text-center">
          <p className="text-gray-600 mb-4">Failed to create conversation</p>
          <Button variant="primary" onClick={() => router.push("/")}>
            Go Back
          </Button>
        </div>
      </div>
    );
  }

  const agentDisplayName = agent ? getAgentDisplayName(agent) : "AI Assistant";
  const agentInitials = agent ? getAgentInitials(agent) : "AI";
  const specialty = agent ? getAgentSpecialty(agent) : null;

  return (
    <div className="h-screen flex flex-col bg-white">
      <div className="border-b border-[#251D1C]/20 px-6 py-4 bg-white shadow-sm">
        <div className="flex items-center gap-4">
          <div className="flex-shrink-0 w-12 h-12 rounded-full bg-[#EEEAE7]/20 flex items-center justify-center text-lg font-medium text-[#443C3C]">
            {agentInitials}
          </div>
          <div className="flex-1">
            <h1 className="text-xl font-semibold text-gray-900">
              {agentDisplayName}
            </h1>
            {specialty && (
              <p className="text-sm text-gray-600">{specialty}</p>
            )}
          </div>
        </div>
      </div>
      <div className="flex-1 overflow-hidden">
        <ChatWindow
          conversationId={conversation.conversation_id}
          agentName={agentDisplayName}
        />
      </div>
    </div>
  );
}

