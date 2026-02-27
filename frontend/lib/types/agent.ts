/** Types for agents and configurations. */

export interface Agent {
  agent_id: string;
  config: AgentConfig;
  created_at: string;
  updated_at: string;
  is_active: boolean;
}

export interface AgentConfig {
  version: string;
  agent_id: string;
  role: string;
  project: string;
  environment: string;
  privacy: PrivacyConfig;
  security: SecurityConfig;
  channels: ChannelsConfig;
  profile: ProfileConfig;
  style: StyleConfig;
  working_hours: WorkingHoursConfig;
  restrictions: RestrictionsConfig;
  handoff: HandoffConfig;
  escalation: EscalationConfig;
  llm: LLMConfig;
  embeddings: EmbeddingsConfig;
  moderation: ModerationConfig;
  prompts: PromptsConfig;
  rag: RAGConfig;
  monitoring: MonitoringConfig;
}

export interface PrivacyConfig {
  consent_model: string;
  purpose_limitation: string;
  message_retention: Record<string, any>;
  metadata_retention: Record<string, any>;
  training_usage: Record<string, any>;
}

export interface SecurityConfig {
  access_control: string;
  audit_log: boolean;
}

export interface ChannelsConfig {
  primary: string;
  supported: string[];
  future: string[];
}

export interface ProfileConfig {
  agent_display_name: string;
  /** @deprecated Legacy field, use agent_display_name. Kept for backward compat with pre-migration API responses. */
  doctor_display_name?: string;
  clinic_display_name: string;
  specialty: string;
  languages: string[];
  geo: string;
  audience: string;
}

export interface StyleConfig {
  tone: string;
  formality: string;
  empathy_level: number;
  depth_level: number;
  message_length: string;
  persuasion: string;
}

export interface WorkingHoursConfig {
  timezone: string;
  schedule: Record<string, string[]>;
  after_hours_behavior: Record<string, any>;
}

export interface RestrictionsConfig {
  no_diagnosis: boolean;
  no_treatment_recommendations: boolean;
  no_drug_advice: boolean;
  no_test_interpretation: boolean;
  no_pre_procedure_recommendations: boolean;
  no_slot_selection: boolean;
  no_repeat_patients: boolean;
  forbidden_claims: string[];
  content_safety: Record<string, any>;
}

export interface HandoffConfig {
  always_possible: boolean;
  immediate_takeover_supported: boolean;
  default_handoff_target: string;
  stop_ai_after_handoff: boolean;
}

export interface EscalationConfig {
  medical_question_policy: string;
  urgent_case_policy: string;
  repeat_patient_policy: string;
  pre_procedure_policy: string;
  triggers: Record<string, any>;
  actions: Record<string, any>;
}

export interface LLMConfig {
  provider: string;
  api: string;
  model: string;
  temperature: number;
  max_output_tokens: number;
  timeout?: number;
}

export interface EmbeddingsConfig {
  provider: string;
  model: string;
  dimensions: number;
  batch_size?: number;
}

export interface ModerationConfig {
  provider: string;
  enabled: boolean;
  mode: string;
  categories: string[];
  action_on_violation?: string;
}

export interface PromptsConfig {
  system: Record<string, string>;
  templates: Record<string, string>;
}

export interface RAGConfig {
  enabled: boolean;
  vector_store: Record<string, any>;
  retrieval: Record<string, any>;
  scope: string;
  sources: RAGSource[];
}

export interface RAGSource {
  id: string;
  type: string;
  title: string;
  content: string;
}

export interface MonitoringConfig {
  admin_panel_required: boolean;
  flags: Record<string, any>;
  kpi_targets_mvp: Record<string, number>;
}








