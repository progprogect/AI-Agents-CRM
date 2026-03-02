/** Types for conversations. */

export type ConversationStatus =
  | "AI_ACTIVE"
  | "NEEDS_HUMAN"
  | "HUMAN_ACTIVE"
  | "CLOSED";

export type MarketingStatus =
  | "NEW"
  | "BOOKED"
  | "NO_RESPONSE"
  | "REJECTED";

export interface CRMStage {
  id: string;
  name: string;
  color: string;
  position: number;
  is_default: boolean;
  created_at: string;
}

export interface Conversation {
  conversation_id: string;
  agent_id: string;
  channel?: string;
  external_conversation_id?: string | null;
  external_user_id?: string | null;
  status: ConversationStatus;
  created_at: string;
  updated_at: string;
  closed_at?: string | null;
  handoff_reason?: string | null;
  request_type?: string | null;
  ttl?: number;
  external_user_name?: string | null;
  external_user_username?: string | null;
  external_user_profile_pic?: string | null;
  marketing_status?: MarketingStatus | null;
  rejection_reason?: string | null;
  crm_stage_id?: string | null;
}

export interface CreateConversationRequest {
  agent_id: string;
}

export interface CreateConversationResponse {
  conversation_id: string;
  agent_id: string;
  status: string;
}








