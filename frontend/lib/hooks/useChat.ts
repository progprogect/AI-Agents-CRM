/** Hook for managing chat state and messages. */

import { useState, useCallback, useEffect, useRef } from "react";
import { api, ApiError } from "@/lib/api";
import { WebSocketClient } from "@/lib/websocket";
import type { Message, WebSocketMessage } from "@/lib/types/message";

export function useChat(conversationId: string | null) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [isTyping, setIsTyping] = useState(false);
  const [isConnected, setIsConnected] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const wsClientRef = useRef<WebSocketClient | null>(null);

  // Load initial messages
  useEffect(() => {
    if (!conversationId) {
      return;
    }

    const loadMessages = async () => {
      setIsLoading(true);
      try {
        const loadedMessages = await api.getMessages(conversationId);
        setMessages(loadedMessages);
      } catch (err) {
        if (err instanceof ApiError) {
          setError(err.message);
        } else {
          setError("Failed to load messages");
        }
      } finally {
        setIsLoading(false);
      }
    };

    loadMessages();
  }, [conversationId]);

  // Handle WebSocket messages
  useEffect(() => {
    if (!conversationId) {
      return;
    }

    const client = new WebSocketClient(conversationId);
    wsClientRef.current = client;

    const unsubscribeMessage = client.onMessage((message: WebSocketMessage) => {
      if (message.type === "message" && message.content) {
        const newMessage: Message = {
          message_id: message.message_id || `temp-${Date.now()}`,
          conversation_id: conversationId,
          agent_id: "", // Will be filled from conversation
          role: message.role || "agent",
          content: message.content,
          timestamp: message.timestamp || new Date().toISOString(),
          media_url: message.media_url ?? null,
          media_type: message.media_type ?? null,
        };
        
        // If this is a user message with a real message_id, replace the optimistic one
        if (message.role === "user" && message.message_id) {
          setMessages((prev) => {
            // Remove any temporary user messages with the same content
            const filtered = prev.filter(
              (m) =>
                !(
                  m.role === "user" &&
                  m.content === message.content &&
                  m.message_id.startsWith("temp-")
                )
            );
            // Check if message already exists (avoid duplicates)
            const exists = filtered.some((m) => m.message_id === message.message_id);
            if (!exists) {
              return [...filtered, newMessage];
            }
            return filtered;
          });
        } else {
          // For agent messages, check for duplicates by message_id
          setMessages((prev) => {
            const exists = prev.some((m) => m.message_id === message.message_id);
            if (!exists) {
              return [...prev, newMessage];
            }
            return prev;
          });
        }
      } else if (message.type === "typing") {
        setIsTyping(true);
        setTimeout(() => setIsTyping(false), 3000);
      } else if (message.type === "handoff") {
        setError("This conversation has been escalated to a human agent");
      }
    });

    const unsubscribeConnection = client.onConnectionStateChange(setIsConnected);
    const unsubscribeError = client.onError((err) => {
      console.error("WebSocket error:", err);
      setError("Connection error. Please refresh the page.");
    });

    client.connect().catch((err) => {
      console.error("WebSocket connection error:", err);
      setError("Failed to connect. Using REST API fallback.");
    });

    return () => {
      unsubscribeMessage();
      unsubscribeConnection();
      unsubscribeError();
      client.disconnect();
      wsClientRef.current = null;
    };
  }, [conversationId]);

  // Auto-scroll to bottom when new messages arrive
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const sendMessage = useCallback(
    async (content: string) => {
      if (!conversationId || !content.trim()) {
        return;
      }

      // Optimistically add user message
      const userMessage: Message = {
        message_id: `temp-${Date.now()}`,
        conversation_id: conversationId,
        agent_id: "",
        role: "user",
        content: content.trim(),
        timestamp: new Date().toISOString(),
      };

      setMessages((prev) => [...prev, userMessage]);

      try {
        if (isConnected && wsClientRef.current) {
          wsClientRef.current.sendMessage(content.trim());
        } else {
          // Fallback to REST API
          await api.sendMessage(conversationId, { content: content.trim() });
          // Reload messages to get the response
          const updatedMessages = await api.getMessages(conversationId);
          setMessages(updatedMessages);
        }
      } catch (err) {
        // Remove optimistic message on error
        setMessages((prev) =>
          prev.filter((m) => m.message_id !== userMessage.message_id)
        );
        if (err instanceof ApiError) {
          setError(err.message);
        } else {
          setError("Failed to send message");
        }
      }
    },
    [conversationId, isConnected]
  );

  return {
    messages,
    isLoading,
    error,
    isTyping,
    isConnected,
    sendMessage,
    messagesEndRef,
  };
}
