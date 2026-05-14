/** Statistics types. */

export interface CRMStageStat {
  id: string;
  name: string;
  color: string;
  position: number;
  count: number;
}

export interface Stats {
  total_conversations: number;
  ai_active: number;
  needs_human: number;
  human_active: number;
  closed: number;
  marketing_new: number;
  marketing_booked: number;
  marketing_no_response: number;
  marketing_rejected: number;
  period: string;
  /** Distinct end users (agent + channel + external_user_id), all time; excludes chats without external id. */
  unique_end_users?: number;
  crm_stage_stats?: CRMStageStat[];
  comparison?: StatsComparison;
}

export interface StatsComparison {
  total_conversations: number;
  ai_active: number;
  needs_human: number;
  human_active: number;
  closed: number;
  marketing_new: number;
  marketing_booked: number;
  marketing_no_response: number;
  marketing_rejected: number;
}

export type Period = "today" | "last_7_days" | "last_30_days";

/** One row from GET /admin/stats/end-users */
export interface EndUserRow {
  agent_id: string;
  agent_display_name: string | null;
  channel: string;
  external_user_id: string;
  display_name: string | null;
  username: string | null;
  last_seen_at: string | null;
  conversation_count: number;
}

export interface EndUsersPage {
  total: number;
  items: EndUserRow[];
}
