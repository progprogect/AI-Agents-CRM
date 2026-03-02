/** Main chat window component with welcome message and improved error display. */

"use client";

import React from "react";
import { useChat } from "@/lib/hooks/useChat";
import { MessageList } from "./MessageList";
import { MessageInput } from "./MessageInput";
import { TypingIndicator } from "./TypingIndicator";
import { LoadingSpinner } from "@/components/shared/LoadingSpinner";
import { EmptyState } from "@/components/shared/EmptyState";

interface ChatWindowProps {
  conversationId: string;
  agentName?: string;
}

export const ChatWindow: React.FC<ChatWindowProps> = ({
  conversationId,
  agentName,
}) => {
  const {
    messages,
    isLoading,
    error,
    isTyping,
    isConnected,
    sendMessage,
    messagesEndRef,
  } = useChat(conversationId);

  if (isLoading && messages.length === 0) {
    return (
      <div className="flex items-center justify-center h-full">
        <LoadingSpinner size="lg" />
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full">
      {/* Connection status */}
      <div className="border-b border-[#251D1C]/20 px-4 py-2.5 bg-white">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <div
              className={`w-2 h-2 rounded-full transition-colors duration-200 ${
                isConnected ? "bg-green-500" : "bg-red-500"
              }`}
              aria-label={isConnected ? "Connected" : "Disconnected"}
            />
            <span className="text-sm text-gray-600">
              {isConnected ? "Connected" : "Disconnected"}
            </span>
          </div>
          {agentName && (
            <span className="text-xs text-gray-500">Chatting with {agentName}</span>
          )}
        </div>
      </div>

      {/* Error message */}
      {error && (
        <div
          className="bg-red-50 border-l-4 border-red-500 p-4 m-4 rounded-sm"
          role="alert"
        >
          <div className="flex items-start gap-2">
            <span className="text-red-500" aria-hidden="true">
              ⚠️
            </span>
            <div>
              <p className="text-sm font-medium text-red-800">Connection Error</p>
              <p className="text-sm text-red-700 mt-1">{error}</p>
            </div>
          </div>
        </div>
      )}

      {/* Messages */}
      {messages.length === 0 && !isLoading ? (
        <EmptyState
          icon="💬"
          title="Start the conversation"
          description={
            agentName
              ? `Send a message to ${agentName} to get started.`
              : "Send a message to get started."
          }
        />
      ) : (
        <MessageList messages={messages} messagesEndRef={messagesEndRef} />
      )}

      {/* Typing indicator */}
      <TypingIndicator isTyping={isTyping} agentName={agentName} />

      {/* Input */}
      <MessageInput
        onSend={sendMessage}
        disabled={!isConnected || isLoading}
        placeholder={
          agentName
            ? `Type your message to ${agentName}...`
            : "Type your message..."
        }
      />
    </div>
  );
};

