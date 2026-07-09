"""Agent configuration model."""

import logging
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

logger = logging.getLogger(__name__)


class PrivacyConfig(BaseModel):
    """Privacy and data retention configuration."""

    consent_model: str = Field(default="implied_by_chat_start")
    purpose_limitation: str = Field(default="booking_and_communication_only")
    message_retention: dict[str, Any] = Field(default_factory=dict)
    metadata_retention: dict[str, Any] = Field(default_factory=dict)
    training_usage: dict[str, Any] = Field(default_factory=dict)


class SecurityConfig(BaseModel):
    """Security configuration."""

    access_control: str = Field(default="rbac")
    audit_log: bool = Field(default=True)


class ChannelsConfig(BaseModel):
    """Channel configuration."""

    primary: str = Field(default="web_chat")
    supported: list[str] = Field(default_factory=lambda: ["web_chat"])
    future: list[str] = Field(default_factory=list)


class ProfileConfig(BaseModel):
    """Agent profile configuration."""

    agent_display_name: str
    company_display_name: str
    specialty: Optional[str] = Field(default="")  # Optional — removed from UI
    languages: list[str] = Field(default_factory=lambda: ["ru", "en"])


class StyleConfig(BaseModel):
    """Communication style configuration."""

    tone: str = Field(default="friendly_professional")
    formality: str = Field(default="semi_formal")
    empathy_level: int = Field(default=7, ge=0, le=10)
    depth_level: int = Field(default=5, ge=0, le=10)
    message_length: str = Field(default="short_to_medium")
    persuasion: str = Field(default="soft")

    @field_validator("empathy_level", "depth_level")
    @classmethod
    def validate_level(cls, v: int) -> int:
        """Validate level values."""
        if not 0 <= v <= 10:
            raise ValueError("Level must be between 0 and 10")
        return v


class WorkingHoursConfig(BaseModel):
    """Working hours configuration."""

    timezone: str = Field(default="Asia/Dubai")
    schedule: dict[str, list[str]] = Field(default_factory=dict)
    after_hours_behavior: dict[str, Any] = Field(default_factory=dict)


class RestrictionsConfig(BaseModel):
    """Medical and legal restrictions."""

    no_diagnosis: bool = Field(default=True)
    no_treatment_recommendations: bool = Field(default=True)
    no_drug_advice: bool = Field(default=True)
    no_test_interpretation: bool = Field(default=True)
    no_pre_procedure_recommendations: bool = Field(default=True)
    no_slot_selection: bool = Field(default=True)
    no_repeat_patients: bool = Field(default=True)
    forbidden_claims: list[str] = Field(default_factory=list)
    content_safety: dict[str, Any] = Field(default_factory=dict)


class HandoffConfig(BaseModel):
    """Handoff configuration."""

    always_possible: bool = Field(default=True)
    immediate_takeover_supported: bool = Field(default=True)
    default_handoff_target: str = Field(default="clinic_admin")
    stop_ai_after_handoff: bool = Field(default=True)


class EscalationInstruction(BaseModel):
    """Instruction for LLM escalation detection."""

    description: str = Field(..., description="Description of escalation type")
    examples: list[str] = Field(
        default_factory=list, description="Example situations for this escalation type"
    )
    guidance: str = Field(
        ..., description="Guidance instruction for LLM on when to escalate"
    )


class EscalationConfig(BaseModel):
    """Escalation rules configuration."""

    enabled: bool = Field(
        default=True,
        description="If False, skip LLM escalation classifier entirely (no auto handoff from rules).",
    )
    detect_contact: bool = Field(
        default=True,
        description="Escalate when user shares phone number or email address",
    )
    custom_rules: list[dict] = Field(
        default_factory=list,
        description="Free-form escalation rules defined by the user",
    )
    # Legacy policy fields — fed into escalation classifier (see escalation_chain.expand_medical_question_policy_for_prompt).
    medical_question_policy: str = Field(
        default="handoff_or_book",
        description='Free text or reserved token "vet_informational" (pet-care + RAG, fixed expanded prompt).',
    )
    urgent_case_policy: str = Field(default="advise_emergency_and_handoff")
    repeat_patient_policy: str = Field(default="handoff_only")
    pre_procedure_policy: str = Field(default="handoff_only")
    policies: dict[str, str] = Field(
        default_factory=dict,
        description="Policy mappings (alternative to individual policy fields)",
    )
    instructions: dict[str, EscalationInstruction] = Field(
        default_factory=dict,
        description="LLM instructions for each escalation type",
    )
    triggers: dict[str, Any] = Field(
        default_factory=dict,
        description="Keyword triggers (used as examples/hints for LLM)",
    )
    actions: dict[str, Any] = Field(
        default_factory=dict, description="Actions to perform on escalation"
    )
    phone_detection: dict[str, Any] = Field(
        default_factory=dict,
        description="Phone number detection configuration",
    )
    fast_check: dict[str, Any] = Field(
        default_factory=dict,
        description="Fast keyword check configuration (optional)",
    )


class LLMConfig(BaseModel):
    """LLM configuration."""

    provider: str = Field(default="openai")
    api: str = Field(default="responses")
    model: str = Field(default="gpt-4o-mini")
    temperature: float = Field(default=0.2, ge=0.0, le=2.0)
    max_output_tokens: int = Field(default=600, ge=1, le=4096)
    timeout: int = Field(
        default=180,
        ge=10,
        le=600,
        description="Chat completion HTTP timeout (seconds); raise for long RAG + reasoning turns",
    )

    @field_validator("provider")
    @classmethod
    def validate_provider(cls, v: str) -> str:
        """Validate LLM provider."""
        valid_providers = ["openai", "aws_bedrock", "google_ai_studio"]
        if v not in valid_providers:
            raise ValueError(f"LLM provider must be one of: {', '.join(valid_providers)}")
        return v

    @field_validator("temperature")
    @classmethod
    def validate_temperature(cls, v: float) -> float:
        """Validate temperature value."""
        if not 0.0 <= v <= 2.0:
            raise ValueError("Temperature must be between 0.0 and 2.0")
        return v

    @field_validator("max_output_tokens")
    @classmethod
    def validate_max_tokens(cls, v: int) -> int:
        """Validate max_output_tokens value."""
        if v < 1:
            raise ValueError("max_output_tokens must be at least 1")
        if v > 4096:
            raise ValueError("max_output_tokens cannot exceed 4096")
        return v

    @field_validator("timeout")
    @classmethod
    def validate_timeout(cls, v: int) -> int:
        if v < 10:
            raise ValueError("timeout must be at least 10 seconds")
        if v > 600:
            raise ValueError("timeout cannot exceed 600 seconds")
        return v


class EmbeddingsConfig(BaseModel):
    """Embeddings configuration."""

    provider: str = Field(default="openai")
    model: str = Field(default="text-embedding-3-small")
    dimensions: int = Field(default=1536)
    batch_size: int = Field(default=100)

    @field_validator("provider")
    @classmethod
    def validate_provider(cls, v: str) -> str:
        """Validate embeddings provider."""
        valid_providers = ["openai", "aws_bedrock", "google_ai_studio"]
        if v not in valid_providers:
            raise ValueError(
                f"Embeddings provider must be one of: {', '.join(valid_providers)}"
            )
        return v

    @field_validator("dimensions")
    @classmethod
    def validate_dimensions(cls, v: int) -> int:
        """Validate embedding dimensions."""
        if v < 1:
            raise ValueError("Dimensions must be at least 1")
        if v > 8192:
            raise ValueError("Dimensions cannot exceed 8192")
        return v


class ModerationConfig(BaseModel):
    """Moderation configuration."""

    provider: str = Field(default="openai")
    model: Optional[str] = Field(
        default=None,
        description="Moderation model id (OpenAI: omni-moderation-latest; Google: gemini-*).",
    )
    enabled: bool = Field(default=True)
    mode: str = Field(default="pre_and_post")
    categories: list[str] = Field(default_factory=list)
    action_on_violation: str = Field(default="block_and_escalate")

    @field_validator("provider")
    @classmethod
    def validate_provider(cls, v: str) -> str:
        """Validate moderation provider."""
        valid_providers = ["openai", "google_ai_studio"]
        if v not in valid_providers:
            raise ValueError(
                f"Moderation provider must be one of: {', '.join(valid_providers)}"
            )
        return v

    @model_validator(mode="before")
    @classmethod
    def default_moderation_model(cls, data: Any) -> Any:
        """Set default model when omitted (legacy configs without model field)."""
        if not isinstance(data, dict):
            return data
        model = data.get("model")
        if model is not None and str(model).strip():
            return data
        provider = data.get("provider", "openai")
        data["model"] = (
            "omni-moderation-latest"
            if provider == "openai"
            else "gemini-2.0-flash"
        )
        return data

    @field_validator("mode")
    @classmethod
    def validate_mode(cls, v: str) -> str:
        """Validate moderation mode."""
        valid_modes = ["pre", "post", "pre_and_post"]
        if v not in valid_modes:
            raise ValueError(f"Moderation mode must be one of: {', '.join(valid_modes)}")
        return v


class ConversationExample(BaseModel):
    """Example conversation for few-shot learning."""

    id: str
    user_message: str = Field(..., min_length=1, max_length=500)
    agent_response: str = Field(..., min_length=1, max_length=2000)
    category: Optional[str] = Field(
        None, description="Example category: booking, info, hours, custom"
    )


class PromptsConfig(BaseModel):
    """Prompts configuration."""

    system: dict[str, str] = Field(default_factory=dict)
    templates: dict[str, str] = Field(default_factory=dict)
    examples: list[ConversationExample] = Field(
        default_factory=list,
        description="Few-shot examples for style guidance (English)",
    )


class RAGConfig(BaseModel):
    """RAG configuration."""

    enabled: bool = Field(default=True)
    vector_store: dict[str, Any] = Field(default_factory=dict)
    retrieval: dict[str, Any] = Field(default_factory=dict)
    scope: str = Field(default="agent_only")
    sources: list[dict[str, Any]] = Field(default_factory=list)
    embeddings_provider: str = Field(
        default="openai",
        description="Provider for RAG embeddings (openai, google_ai_studio)",
    )
    vision_provider: str = Field(
        default="openai",
        description="Provider for image descriptions (openai, google_ai_studio)",
    )
    vision_model: Optional[str] = Field(
        default=None,
        description=(
            "Vision model id when using multimodal image understanding "
            "(RAG documents and inbound chat images). None = gemini-3.1-pro-preview."
        ),
    )


class MonitoringConfig(BaseModel):
    """Monitoring and quality configuration."""

    admin_panel_required: bool = Field(default=True)
    flags: dict[str, Any] = Field(default_factory=dict)
    kpi_targets_mvp: dict[str, float] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Workflow configuration
# ---------------------------------------------------------------------------

class WorkflowTimerTrigger(BaseModel):
    """Timer-based trigger attached to a workflow step.

    When action_type == 'static', the agent sends ``message_template`` verbatim
    (with {variable} substitution from the step's collected fields).

    When action_type == 'agent', the LLM generates a proactive message using
    the conversation context and the ``prompt`` instruction.  ``message_template``
    is ignored in this mode.
    """

    delay_seconds: int = Field(
        ..., ge=1, description="Seconds of user inactivity before the trigger fires"
    )
    action_type: Literal["static", "agent"] = Field(
        default="static",
        description="'static' sends message_template; 'agent' asks the LLM to generate a message",
    )
    message_template: str = Field(
        default="",
        description="Message text for action_type='static'; supports {variable} substitution",
    )
    prompt: Optional[str] = Field(
        default=None,
        description="Instruction for the LLM when action_type='agent'",
    )


class WorkflowTransition(BaseModel):
    """Condition-based transition from one workflow step to another."""

    condition: str = Field(
        ..., description="Natural-language condition evaluated by the LLM transition evaluator"
    )
    next_step_id: str = Field(..., description="Step to transition to when condition is met")
    is_forced: bool = Field(
        default=False,
        description="If True, the agent must stay on the current step until this condition is satisfied",
    )
    is_fallback: bool = Field(
        default=False,
        description=(
            "If True, this is the fallback (else) branch — "
            "taken only when no prior conditional transition matched. "
            "Mutually exclusive with is_forced."
        ),
    )
    match_quick_reply: Optional[str] = Field(
        default=None,
        description=(
            "If set, transition fires when user_message exactly matches this "
            "quick-reply label (before LLM evaluator)."
        ),
    )


class WorkflowStep(BaseModel):
    """A single step in a conversation workflow."""

    id: str = Field(..., description="Unique step identifier within the workflow")
    name: str = Field(..., description="Human-readable step name")
    instructions: str = Field(
        ..., description="LLM instructions for this step (appended to base system prompt)"
    )
    collect: list[str] = Field(
        default_factory=list,
        description="Names of variables to collect from the user on this step",
    )
    required: bool = Field(
        default=False,
        description="If True, the step must be completed before the workflow can advance",
    )
    transitions: list[WorkflowTransition] = Field(
        default_factory=list,
        description="Ordered list of transitions to evaluate after the LLM responds",
    )
    timer_trigger: Optional[WorkflowTimerTrigger] = Field(
        default=None,
        description="Optional timer-based follow-up message scheduled after entering this step",
    )
    quick_replies: list[str] = Field(
        default_factory=list,
        description="Optional quick-reply button labels shown to the user after this step's message",
    )
    skip_if_questionnaire_field: Optional[str] = Field(
        default=None,
        description=(
            "If set and this questionnaire field already has a recorded value for the current user, "
            "skip this step and follow the first fallback/unconditional transition instead."
        ),
    )
    collect_to_questionnaire: bool = Field(
        default=False,
        description=(
            "When True, each value extracted via collect[] is also written to questionnaire_responses "
            "after LLM extraction (no active FSM session required)."
        ),
    )
    hard_block_until_complete: bool = Field(
        default=False,
        description=(
            "When True, the LLM is strictly forbidden from answering any off-topic questions "
            "or providing advice until this step's collect[] fields are fully satisfied. "
            "Use for consent/legal steps where partial or topic-adjacent responses are unacceptable. "
            "Replaces the soft 'collect first, then answer' wording with an absolute prohibition."
        ),
    )
    evaluate_transition_conditions_when_collect_incomplete: bool = Field(
        default=False,
        description=(
            "When True, non-fallback transitions with a non-empty condition are still evaluated "
            "via the LLM even if required collect[] fields are not all filled yet. "
            "Use when a step may advance (e.g. to give an answer) based on 'sufficient context' "
            "before every collect key is present."
        ),
    )
    static_template_key: Optional[str] = Field(
        default=None,
        description=(
            "When set, the LLM is bypassed entirely and the step's response is taken verbatim "
            "from prompts.templates[static_template_key]. Supports {user_name} placeholder. "
            "Use for mandatory static messages like share/referral prompts."
        ),
    )


class WorkflowAutoStep(BaseModel):
    """Automatically scheduled follow-up action attached to a workflow step or another auto-step.

    Unlike ``WorkflowTimerTrigger`` (which resets on every user message), an auto-step
    is scheduled once when the source step/auto-step fires and is NOT cancelled by
    subsequent user messages alone.

    By default (``cancel_on_workflow_step_change=True``) pending auto-steps are cleared
    when the workflow moves to another regular ``WorkflowStep``.  Set
    ``cancel_on_workflow_step_change=False`` to keep the job until it fires or until
    a hard reset (e.g. conversation /restart).  Explicit full cancellation still removes
    all pending auto-steps regardless of this flag.

    ``source_id`` must reference either a ``WorkflowStep.id`` or another
    ``WorkflowAutoStep.id`` within the same ``WorkflowConfig``.

    ``schedule_anchor`` controls when ``delay_seconds`` starts: on entering the
    referenced step (default) or on leaving that step (``on_step_exit`` applies only
    when ``source_id`` is a regular step id, not another auto-step).
    """

    id: str = Field(..., description="Unique auto-step identifier within the workflow")
    name: str = Field(..., description="Human-readable display name shown on the canvas")
    source_id: str = Field(
        ...,
        description=(
            "ID of the step or auto-step that directly precedes this one in the chain. "
            "For schedule_anchor=on_step_exit, must be a WorkflowStep.id (see WorkflowConfig validator). "
            "For on_step_enter, may reference another WorkflowAutoStep.id — after that auto fires, "
            "downstream autos with this source_id are scheduled (_schedule_chained_auto_steps)."
        ),
    )
    schedule_anchor: Literal["on_step_enter", "on_step_exit"] = Field(
        default="on_step_enter",
        description=(
            "on_step_enter: start delay when transitioning TO source_id (step or prior auto). "
            "on_step_exit: start delay when transitioning FROM source_id to another step "
            "(source_id must be a WorkflowStep id)."
        ),
    )
    delay_seconds: int = Field(
        ..., ge=1, description="Seconds to wait after the source event before firing"
    )
    action_type: Literal["static", "agent"] = Field(
        default="static",
        description="'static' sends message_template verbatim; 'agent' calls the LLM with prompt",
    )
    message_template: str = Field(
        default="",
        description="Message text for action_type='static'; supports {variable} substitution",
    )
    prompt: str = Field(
        default="",
        description="Instruction for the LLM when action_type='agent'",
    )
    condition: Optional[str] = Field(
        default=None,
        description="Natural-language condition evaluated by LLM (yes/no) before sending; None = always fire",
    )
    cancel_on_workflow_step_change: bool = Field(
        default=True,
        description=(
            "If True (default), remove this pending auto-step when the conversation "
            "transitions to another regular workflow step. If False, keep it until "
            "fire_at or until a full cancel (e.g. /restart)."
        ),
    )
    once_per_conversation: bool = Field(
        default=False,
        description=(
            "If True, after this auto-step successfully sends a user-visible message in this "
            "conversation, it will not be scheduled again until a new conversation (e.g. /restart). "
            "Skipped or failed sends do not count."
        ),
    )
    telegram_attachment_type: Literal["none", "video_url", "video_note"] = Field(
        default="none",
        description=(
            "Telegram-only outbound attachment for this auto-step. "
            "'video_url' uses sendVideo with a public HTTPS URL; "
            "'video_note' uses sendVideoNote with a file_id from the same bot (no URL support in Bot API)."
        ),
    )
    telegram_video_url: Optional[str] = Field(
        default=None,
        description="Public HTTPS URL passed to sendVideo when telegram_attachment_type='video_url'.",
    )
    telegram_video_note_file_id: Optional[str] = Field(
        default=None,
        description="Telegram file_id for sendVideoNote when telegram_attachment_type='video_note'.",
    )

    @model_validator(mode="after")
    def validate_telegram_auto_step_media(self) -> "WorkflowAutoStep":
        """Ensure Telegram attachment fields are consistent."""
        t = self.telegram_attachment_type
        if t == "none":
            if self.telegram_video_url or self.telegram_video_note_file_id:
                raise ValueError(
                    "workflow auto-step: telegram_attachment_type 'none' must not set "
                    "telegram_video_url or telegram_video_note_file_id"
                )
            return self
        if t == "video_url":
            if not (self.telegram_video_url or "").strip():
                raise ValueError(
                    "workflow auto-step: telegram_attachment_type 'video_url' requires "
                    "non-empty telegram_video_url"
                )
            if self.telegram_video_note_file_id:
                raise ValueError(
                    "workflow auto-step: telegram_video_url mode must not set telegram_video_note_file_id"
                )
            return self
        # video_note
        if not (self.telegram_video_note_file_id or "").strip():
            raise ValueError(
                "workflow auto-step: telegram_attachment_type 'video_note' requires "
                "non-empty telegram_video_note_file_id"
            )
        if self.telegram_video_url:
            raise ValueError(
                "workflow auto-step: video_note mode must not set telegram_video_url"
            )
        return self


class WorkflowConfig(BaseModel):
    """Conversation workflow definition for an agent."""

    enabled: bool = Field(
        default=False,
        description="If False, the workflow engine is bypassed and the agent responds as a single-step chat",
    )
    start_step_id: str = Field(
        default="default",
        description="ID of the first step to use when a conversation starts",
    )
    steps: list[WorkflowStep] = Field(
        default_factory=list,
        description="Ordered list of workflow steps",
    )
    auto_steps: list[WorkflowAutoStep] = Field(
        default_factory=list,
        description="Time-triggered follow-up actions that fire automatically regardless of user activity",
    )

    @model_validator(mode="after")
    def validate_auto_step_schedule_anchors(self) -> "WorkflowConfig":
        """on_step_exit requires source_id to be a regular workflow step, not an auto-step."""
        step_ids = {s.id for s in self.steps}
        auto_ids = {a.id for a in self.auto_steps}
        for a in self.auto_steps:
            if a.schedule_anchor != "on_step_exit":
                continue
            if a.source_id not in step_ids:
                raise ValueError(
                    f"workflow.auto_steps[{a.id!r}]: schedule_anchor 'on_step_exit' requires "
                    f"source_id to be a step id; {a.source_id!r} is not in workflow.steps"
                )
            if a.source_id in auto_ids:
                raise ValueError(
                    f"workflow.auto_steps[{a.id!r}]: schedule_anchor 'on_step_exit' cannot use "
                    f"another auto_step as source_id ({a.source_id!r})"
                )
        return self


class AgentConfig(BaseModel):
    """Complete agent configuration."""

    version: str = Field(default="1.0")
    agent_id: str
    role: str = Field(default="chat_agent")
    project: str
    environment: str = Field(default="mvp")

    privacy: PrivacyConfig = Field(default_factory=PrivacyConfig)
    security: SecurityConfig = Field(default_factory=SecurityConfig)
    channels: ChannelsConfig = Field(default_factory=ChannelsConfig)
    profile: ProfileConfig
    style: StyleConfig = Field(default_factory=StyleConfig)
    working_hours: WorkingHoursConfig = Field(default_factory=WorkingHoursConfig)
    restrictions: RestrictionsConfig = Field(default_factory=RestrictionsConfig)
    handoff: HandoffConfig = Field(default_factory=HandoffConfig)
    escalation: EscalationConfig = Field(default_factory=EscalationConfig)
    llm: LLMConfig = Field(default_factory=LLMConfig)
    embeddings: EmbeddingsConfig = Field(default_factory=EmbeddingsConfig)
    moderation: ModerationConfig = Field(default_factory=ModerationConfig)
    prompts: PromptsConfig = Field(default_factory=PromptsConfig)
    rag: RAGConfig = Field(default_factory=RAGConfig)
    monitoring: MonitoringConfig = Field(default_factory=MonitoringConfig)
    workflow: WorkflowConfig = Field(default_factory=WorkflowConfig)

    @model_validator(mode="after")
    def validate_config(self) -> "AgentConfig":
        """Cross-field validation."""
        # Ensure profile is set (required field)
        if not self.profile.agent_display_name:
            raise ValueError("agent_display_name is required in profile")
        if not self.profile.company_display_name:
            raise ValueError("company_display_name is required in profile")

        # Validate RAG configuration if enabled
        if self.rag.enabled:
            if "top_k" in self.rag.retrieval:
                top_k = self.rag.retrieval["top_k"]
                if not isinstance(top_k, int) or top_k < 1 or top_k > 50:
                    raise ValueError("RAG top_k must be an integer between 1 and 50")

            if "score_threshold" in self.rag.retrieval:
                threshold = self.rag.retrieval["score_threshold"]
                if not isinstance(threshold, (int, float)) or not 0.0 <= threshold <= 1.0:
                    raise ValueError("RAG score_threshold must be between 0.0 and 1.0")

        # Validate examples configuration
        if self.prompts.examples:
            if len(self.prompts.examples) > 7:
                raise ValueError("Maximum 7 examples allowed (3 standard + 4 custom)")

        return self

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AgentConfig":
        """Create AgentConfig from dictionary (e.g., from YAML)."""
        # Handle nested structures
        config_data = {}
        for key, value in data.items():
            if key == "privacy" and isinstance(value, dict):
                config_data[key] = PrivacyConfig(**value)
            elif key == "security" and isinstance(value, dict):
                config_data[key] = SecurityConfig(**value)
            elif key == "channels" and isinstance(value, dict):
                config_data[key] = ChannelsConfig(**value)
            elif key == "profile" and isinstance(value, dict):
                # Support legacy doctor_display_name for backward compatibility
                profile_data = dict(value)
                if "doctor_display_name" in profile_data and "agent_display_name" not in profile_data:
                    profile_data["agent_display_name"] = profile_data.pop("doctor_display_name")
                config_data[key] = ProfileConfig(**profile_data)
            elif key == "style" and isinstance(value, dict):
                config_data[key] = StyleConfig(**value)
            elif key == "working_hours" and isinstance(value, dict):
                config_data[key] = WorkingHoursConfig(**value)
            elif key == "restrictions" and isinstance(value, dict):
                config_data[key] = RestrictionsConfig(**value)
            elif key == "handoff" and isinstance(value, dict):
                config_data[key] = HandoffConfig(**value)
            elif key == "escalation" and isinstance(value, dict):
                # Handle instructions conversion if present
                escalation_data = value.copy()
                if "instructions" in escalation_data and isinstance(
                    escalation_data["instructions"], dict
                ):
                    escalation_data["instructions"] = {
                        k: EscalationInstruction(**v)
                        if isinstance(v, dict)
                        else v
                        for k, v in escalation_data["instructions"].items()
                    }
                config_data[key] = EscalationConfig(**escalation_data)
            elif key == "llm" and isinstance(value, dict):
                config_data[key] = LLMConfig(**value)
            elif key == "embeddings" and isinstance(value, dict):
                config_data[key] = EmbeddingsConfig(**value)
            elif key == "moderation" and isinstance(value, dict):
                config_data[key] = ModerationConfig(**value)
            elif key == "prompts" and isinstance(value, dict):
                # Handle examples conversion if present
                prompts_data = value.copy()
                if "examples" in prompts_data and isinstance(prompts_data["examples"], list):
                    prompts_data["examples"] = [
                        ConversationExample(**ex) if isinstance(ex, dict) else ex
                        for ex in prompts_data["examples"]
                    ]
                config_data[key] = PromptsConfig(**prompts_data)
            elif key == "rag" and isinstance(value, dict):
                config_data[key] = RAGConfig(**value)
            elif key == "workflow" and isinstance(value, dict):
                config_data[key] = WorkflowConfig(**value)
            elif key == "monitoring" and isinstance(value, dict):
                config_data[key] = MonitoringConfig(**value)
            else:
                config_data[key] = value

        return cls(**config_data)

    def to_dict(self) -> dict[str, Any]:
        """Convert AgentConfig to dictionary."""
        return self.model_dump(exclude_none=True)

