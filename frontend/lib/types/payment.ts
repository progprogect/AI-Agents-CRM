/** Payment integration types. */

export type PaymentProvider = "telegram_native" | "external_link";
export type SubscriptionStatus = "free" | "active" | "expired" | "manual";
export type TransactionStatus = "pending" | "completed" | "failed" | "refunded";

export interface PaymentSettings {
  setting_id?: string;
  binding_id: string;
  enabled: boolean;
  provider: PaymentProvider;
  free_messages: number;
  grace_messages: number;
  sandbox_mode: boolean;
  has_live_token: boolean;
  has_sandbox_token: boolean;
  payment_title: string;
  payment_description: string;
  invoice_resend_hours: number;
  support_contact?: string | null;
  created_at?: string;
  updated_at?: string;
}

export interface UpsertPaymentSettingsRequest {
  enabled: boolean;
  provider: PaymentProvider;
  free_messages: number;
  grace_messages: number;
  sandbox_mode: boolean;
  payment_title?: string;
  payment_description?: string;
  invoice_resend_hours: number;
  support_contact?: string;
}

export interface PaymentPlan {
  plan_id: string;
  binding_id: string;
  name: string;
  duration_days: number;
  price_amount: number;
  currency: string;
  messages_limit: number | null;
  is_active: boolean;
  sort_order: number;
  created_at: string;
}

export interface CreatePlanRequest {
  name: string;
  duration_days: number;
  price_amount: number;
  currency: string;
  messages_limit?: number | null;
  sort_order?: number;
}

export interface UserSubscription {
  sub_id: string;
  binding_id: string;
  external_user_id: string;
  status: SubscriptionStatus;
  plan_id: string | null;
  expires_at: string | null;
  messages_used: number;
  messages_limit: number | null;
  period_started_at: string | null;
  invoice_sent_at: string | null;
  grace_messages_used: number;
  manual_override: boolean;
  notes: string | null;
  created_at: string;
  updated_at: string;
}

export interface UpdateSubscriptionRequest {
  status?: SubscriptionStatus | string;
  expires_at?: string | null;
  messages_limit?: number | null;
  messages_used?: number;
  manual_override?: boolean;
  notes?: string;
}

export interface PaymentTransaction {
  txn_id: string;
  sub_id: string;
  binding_id: string;
  external_user_id: string;
  provider: PaymentProvider;
  provider_charge_id: string | null;
  plan_id: string | null;
  amount: number | null;
  currency: string | null;
  status: TransactionStatus;
  created_at: string;
}
