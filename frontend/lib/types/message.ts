/** Types for messages. */

export type MessageRole = "user" | "agent" | "admin";

export interface Message {
  message_id: string;
  conversation_id: string;
  agent_id: string;
  role: MessageRole;
  content: string;
  timestamp: string;
  metadata?: Record<string, any>;
  ttl?: number;
  media_url?: string | null;
  media_type?: string | null;  // "image" | "video" | "audio" | "document"
  media_filename?: string | null;
}

export interface SendMessageRequest {
  content: string;
}

export interface SendMessageResponse {
  message_id: string;
  role: string;
  content: string;
  timestamp: string;
}

export interface WebSocketMessage {
  type: "message" | "ping" | "pong" | "status" | "handoff" | "error" | "typing";
  message_id?: string;
  role?: MessageRole;
  content?: string;
  timestamp?: string;
  conversation_id?: string;
  status?: string;
  reason?: string;
  message?: string;
  media_url?: string | null;
  media_type?: string | null;
}








