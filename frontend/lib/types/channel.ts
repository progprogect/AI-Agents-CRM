/** Types for channel bindings. */

export type ChannelType = "web_chat" | "instagram" | "telegram" | "whatsapp";

export interface ChannelConfig {
  app_url: string;
  instagram_webhook_url: string;
  instagram_verify_token: string;
  instagram_app_secret_configured: boolean;
  telegram_webhook_base: string;
  whatsapp_webhook_url: string;
  whatsapp_verify_token: string;
  whatsapp_app_secret_configured: boolean;
}

export interface ChannelBinding {
  binding_id: string;
  agent_id: string;
  channel_type: ChannelType;
  channel_account_id: string;
  channel_username?: string;
  is_active: boolean;
  is_verified: boolean;
  created_at: string;
  updated_at: string;
  created_by?: string;
  metadata: Record<string, any>;
}

export interface CreateChannelBindingRequest {
  channel_type: ChannelType;
  channel_account_id: string;
  access_token: string;
  channel_username?: string;
  metadata?: Record<string, any>;
}

export interface UpdateChannelBindingRequest {
  is_active?: boolean;
  access_token?: string;
  metadata?: Record<string, any>;
}

