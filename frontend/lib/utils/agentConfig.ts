/** Utilities for working with agent configuration. */

export interface ConversationExample {
  id: string;
  user_message: string; // English only
  agent_response: string; // English only
  category?: "booking" | "info" | "hours" | "custom";
}

export interface EscalationRule {
  id: string;
  name: string;        // short label, e.g. "Urgent request"
  description: string; // what the agent should do, e.g. "Transfer to human immediately"
}

// Standard examples (pre-filled)
export const DEFAULT_EXAMPLES: ConversationExample[] = [
  {
    id: "example_pricing",
    category: "info",
    user_message: "How much does this service cost?",
    agent_response:
      "Thank you for your question! Pricing depends on the specific service and your individual needs. To give you accurate information, I'd recommend scheduling a consultation — our team will walk you through all available options and costs. Would you like me to help you set that up? Just leave your phone number and we'll be in touch shortly.",
  },
  {
    id: "example_booking",
    category: "booking",
    user_message: "How do I book a service?",
    agent_response:
      "Booking is simple! Please share your phone number (or WhatsApp), and our team will contact you to confirm the details, check availability, and find a time that works best for you. We typically respond within a few hours during business hours.",
  },
  {
    id: "example_choice",
    category: "custom",
    user_message: "Can you help me choose the right option for me?",
    agent_response:
      "Of course, I'd be happy to help guide you! To point you in the right direction, could you tell me a bit more about what you're looking for or what your main concern is? Once I understand your situation better, I can suggest the most suitable option — or connect you with our specialist directly.",
  },
];

export interface AgentConfigFormData {
  // Basic Info
  agent_id: string;
  agent_display_name: string;
  clinic_display_name: string;
  languages?: string[]; // Languages the agent can communicate in

  // Style (Step 2)
  tone?: string;
  formality?: string;
  empathy_level?: number;
  depth_level?: number;
  message_length?: string;
  persuasion?: string;

  // RAG
  rag_enabled: boolean;
  rag_embeddings_provider?: string;
  rag_vision_provider?: string;
  rag_documents: Array<{
    id: string;
    title: string;
    content: string;
  }>;

  // Escalation - legacy policy fields (kept at defaults, not shown in UI)
  medical_question_policy?: string;
  urgent_case_policy?: string;
  repeat_patient_policy?: string;
  pre_procedure_policy?: string;

  // Escalation - free-form custom rules (Step 5)
  escalation_rules?: EscalationRule[];

  // LLM Settings (Step 6)
  llm_provider?: string;
  llm_model?: string;
  llm_temperature?: number;
  llm_max_tokens?: number;

  // Examples (Step 3)
  examples?: ConversationExample[];

  // System Prompts (Step 7)
  system_persona?: string;
  system_hard_rules?: string;
  system_goal?: string;
}

/**
 * Generate default agent configuration.
 */
export function generateDefaultConfig(): Partial<AgentConfigFormData> {
  return {
    rag_enabled: false,
    rag_embeddings_provider: "openai",
    rag_vision_provider: "openai",
    rag_documents: [],
    languages: ["ru", "en"],
    // Style defaults
    tone: "friendly_professional",
    formality: "semi_formal",
    empathy_level: 7,
    depth_level: 5,
    message_length: "short_to_medium",
    persuasion: "soft",
    // Examples defaults
    examples: [...DEFAULT_EXAMPLES],
    // Escalation legacy defaults (not shown in UI)
    medical_question_policy: "handoff_or_book",
    urgent_case_policy: "advise_emergency_and_handoff",
    repeat_patient_policy: "handoff_only",
    pre_procedure_policy: "handoff_only",
    // Escalation free-form rules
    escalation_rules: [],
    // LLM defaults
    llm_provider: "openai",
    llm_model: "gpt-4o-mini",
    llm_temperature: 0.2,
    llm_max_tokens: 600,
    // System prompt defaults (empty — user fills in)
    system_persona: "",
    system_hard_rules: "",
    system_goal: "",
  };
}

/**
 * Convert existing agent config to form data (for cloning/editing).
 */
export function agentConfigToFormData(
  agentConfig: Record<string, any>
): Partial<AgentConfigFormData> {
  const formData: Partial<AgentConfigFormData> = {
    // Basic Info
    agent_id: agentConfig.agent_id || "",
    agent_display_name: agentConfig.profile?.agent_display_name || agentConfig.profile?.doctor_display_name || "",
    clinic_display_name: agentConfig.profile?.clinic_display_name || "",

    // Style
    tone: agentConfig.style?.tone,
    formality: agentConfig.style?.formality,
    empathy_level: agentConfig.style?.empathy_level,
    depth_level: agentConfig.style?.depth_level,
    message_length: agentConfig.style?.message_length,
    persuasion: agentConfig.style?.persuasion,

    // RAG
    rag_enabled: agentConfig.rag?.enabled || false,
    rag_documents:
      agentConfig.rag?.sources?.map((source: any, index: number) => ({
        id: source.id || `doc_${index}`,
        title: source.title || "",
        content: source.content || "",
      })) || [],

    // Escalation legacy policies
    medical_question_policy: agentConfig.escalation?.medical_question_policy,
    urgent_case_policy: agentConfig.escalation?.urgent_case_policy,
    repeat_patient_policy: agentConfig.escalation?.repeat_patient_policy,
    pre_procedure_policy: agentConfig.escalation?.pre_procedure_policy,

    // Escalation free-form rules
    escalation_rules: agentConfig.escalation?.custom_rules?.map((r: any, i: number) => ({
      id: r.id || `rule_${i}`,
      name: r.name || "",
      description: r.description || "",
    })) || [],

    // Languages
    languages: agentConfig.profile?.languages || ["ru", "en"],

    // Examples
    examples:
      agentConfig.prompts?.examples && agentConfig.prompts.examples.length > 0
        ? agentConfig.prompts.examples.map((ex: any, index: number) => ({
            id: ex.id || `example_${index}_${Date.now()}`,
            user_message: ex.user_message || "",
            agent_response: ex.agent_response || "",
            category: ex.category,
          }))
        : DEFAULT_EXAMPLES,

    // System prompts
    system_persona: agentConfig.prompts?.system?.persona || "",
    system_hard_rules: agentConfig.prompts?.system?.hard_rules || "",
    system_goal: agentConfig.prompts?.system?.goal || "",

    // LLM
    llm_provider: agentConfig.llm?.provider || "openai",
    llm_model: agentConfig.llm?.model,
    llm_temperature: agentConfig.llm?.temperature,
    llm_max_tokens: agentConfig.llm?.max_output_tokens,
    // RAG providers
    rag_embeddings_provider: agentConfig.rag?.embeddings_provider || agentConfig.embeddings?.provider || "openai",
    rag_vision_provider: agentConfig.rag?.vision_provider || agentConfig.llm?.provider || "openai",
  };

  return formData;
}

/**
 * Default prompt templates used when user leaves fields empty.
 */
const DEFAULT_PERSONA = `You are an agent named {agent_display_name} representing {clinic_display_name}.
Your style is friendly and professional. You help users with information and bookings.
You do NOT conduct consultations in chat — you guide users toward scheduling an appointment.`;

const DEFAULT_HARD_RULES = `Never provide diagnoses, treatment plans, drug recommendations, or test interpretations.
For any medical questions, redirect the user to book an in-person appointment or transfer to a human.
In urgent cases, advise emergency services and stop independent communication.
Returning patients — transfer to a human agent only.
After receiving contact info: pass to administrator and end the conversation.
Do not promise outcomes. Do not claim that a specialist is personally reading messages right now.`;

const DEFAULT_GOAL = `Primary goal: quickly and politely assist, qualify the request, and guide toward booking without pressure.
If the specialty does not match — suggest another direction and offer to book.`;

/**
 * Convert form data to agent config object (for API).
 */
export function formDataToAgentConfig(
  formData: AgentConfigFormData
): Record<string, any> {
  const config: Record<string, any> = {
    agent_id: formData.agent_id,
    project: formData.clinic_display_name || "Default Project",
    profile: {
      agent_display_name: formData.agent_display_name,
      clinic_display_name: formData.clinic_display_name,
      languages: formData.languages || ["ru", "en"],
    },
    style: {
      tone: formData.tone || "friendly_professional",
      formality: formData.formality || "semi_formal",
      empathy_level: formData.empathy_level ?? 7,
      depth_level: formData.depth_level ?? 5,
      message_length: formData.message_length || "short_to_medium",
      persuasion: formData.persuasion || "soft",
    },
    llm: {
      provider: formData.llm_provider || "openai",
      api: "responses",
      model: formData.llm_model || "gpt-4o-mini",
      temperature: formData.llm_temperature ?? 0.2,
      max_output_tokens: formData.llm_max_tokens ?? 600,
      timeout: 30,
    },
    prompts: {
      system: {
        persona: formData.system_persona || DEFAULT_PERSONA,
        hard_rules: formData.system_hard_rules || DEFAULT_HARD_RULES,
        goal: formData.system_goal || DEFAULT_GOAL,
      },
      examples:
        formData.examples && formData.examples.length > 0
          ? formData.examples.map((ex, index) => ({
              id: ex.id || `example_${index}_${Date.now()}`,
              user_message: ex.user_message,
              agent_response: ex.agent_response,
              category: ex.category,
            }))
          : [],
    },
    rag: {
      enabled: formData.rag_enabled,
      embeddings_provider: formData.rag_embeddings_provider || formData.llm_provider || "openai",
      vision_provider: formData.rag_vision_provider || formData.llm_provider || "openai",
      vector_store: {
        provider: "opensearch",
        index_name: `agent_${formData.agent_id}_documents`,
      },
      retrieval: {
        top_k: 6,
        score_threshold: 0.2,
      },
      scope: "agent_only",
      sources: formData.rag_enabled
        ? formData.rag_documents.map((doc) => ({
            id: doc.id,
            type: "text",
            title: doc.title,
            content: doc.content,
          }))
        : [],
    },
    moderation: {
      provider: "openai",
      enabled: true,
      mode: "pre_and_post",
    },
    escalation: {
      medical_question_policy: formData.medical_question_policy || "handoff_or_book",
      urgent_case_policy: formData.urgent_case_policy || "advise_emergency_and_handoff",
      repeat_patient_policy: formData.repeat_patient_policy || "handoff_only",
      pre_procedure_policy: formData.pre_procedure_policy || "handoff_only",
      custom_rules: (formData.escalation_rules || []).map((rule) => ({
        id: rule.id,
        name: rule.name,
        description: rule.description,
      })),
    },
  };

  // Embeddings config (for RAG)
  const embeddingsProvider = formData.rag_embeddings_provider || formData.llm_provider || "openai";
  config.embeddings = {
    provider: embeddingsProvider,
    model: embeddingsProvider === "google_ai_studio" ? "text-embedding-004" : "text-embedding-3-small",
    dimensions: 1536,
  };

  return config;
}

/**
 * Transliterate Russian/Cyrillic characters to Latin.
 */
function transliterate(text: string): string {
  const lowercaseMap: Record<string, string> = {
    а: "a", б: "b", в: "v", г: "g", д: "d", е: "e", ё: "yo", ж: "zh",
    з: "z", и: "i", й: "y", к: "k", л: "l", м: "m", н: "n", о: "o",
    п: "p", р: "r", с: "s", т: "t", у: "u", ф: "f", х: "kh", ц: "ts",
    ч: "ch", ш: "sh", щ: "shch", ъ: "", ы: "y", ь: "", э: "e", ю: "yu",
    я: "ya",
  };
  const uppercaseMap: Record<string, string> = {
    А: "a", Б: "b", В: "v", Г: "g", Д: "d", Е: "e", Ё: "yo", Ж: "zh",
    З: "z", И: "i", Й: "y", К: "k", Л: "l", М: "m", Н: "n", О: "o",
    П: "p", Р: "r", С: "s", Т: "t", У: "u", Ф: "f", Х: "kh", Ц: "ts",
    Ч: "ch", Ш: "sh", Щ: "shch", Ъ: "", Ы: "y", Ь: "", Э: "e", Ю: "yu",
    Я: "ya",
  };
  const transliterationMap = { ...lowercaseMap, ...uppercaseMap };
  return text
    .split("")
    .map((char) => transliterationMap[char] || char)
    .join("");
}

/**
 * Generate agent ID from clinic name and agent name.
 */
export function generateAgentId(clinicName: string, doctorName?: string): string {
  let combined = clinicName.trim();
  if (doctorName && doctorName.trim()) {
    combined = `${clinicName.trim()}_${doctorName.trim()}`;
  }
  const transliterated = transliterate(combined);
  return transliterated
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "")
    .substring(0, 50);
}
