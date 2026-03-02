/** Step 7: Review and Create. */

"use client";

import React, { useState, useMemo, useEffect } from "react";
import { Button } from "@/components/shared/Button";
import { LoadingSpinner } from "@/components/shared/LoadingSpinner";
import { YAMLEditor } from "@/components/shared/YAMLEditor";
import { Textarea } from "@/components/shared/Textarea";
import { api, ApiError } from "@/lib/api";
import type { AgentConfigFormData } from "@/lib/utils/agentConfig";
import { formDataToAgentConfig, generateAgentId } from "@/lib/utils/agentConfig";

export interface AgentWizardSuccessResult {
  agentId: string;
  isCreate: boolean;
  ragEnabled: boolean;
}

interface ReviewStepProps {
  config: Partial<AgentConfigFormData>;
  isSubmitting?: boolean;
  onSubmit: (result?: AgentWizardSuccessResult) => Promise<void> | void;
  onStartOver?: () => void;
  onBack?: () => void;
  hasDraft?: boolean;
}

const DEFAULT_PERSONA = `You are an agent named {agent_display_name} representing {company_display_name}.
Your style is friendly and professional. You help users with information and bookings.
You do NOT conduct consultations in chat — you guide users toward scheduling an appointment.`;

const DEFAULT_HARD_RULES = `Never provide diagnoses, treatment plans, drug recommendations, or test interpretations.
For any medical questions, redirect the user to book an in-person appointment or transfer to a human.
In urgent cases, advise emergency services and stop independent communication.
Returning patients — transfer to a human agent only.
After receiving contact info: pass to administrator and end the conversation.
Do not promise outcomes. Do not claim that a specialist is personally reading messages right now.`;

const DEFAULT_GOAL = `Primary goal: quickly and politely assist, qualify the request, and guide toward booking without pressure.
If the service does not match the user's needs — suggest another direction and offer to book.`;

export const ReviewStep: React.FC<ReviewStepProps> = ({
  config,
  isSubmitting: externalIsSubmitting,
  onSubmit,
  onStartOver,
  onBack,
  hasDraft = false,
}) => {
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [editMode, setEditMode] = useState<"form" | "yaml" | "prompt">("form");
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const [editedConfig, setEditedConfig] = useState<Record<string, any> | null>(null);
  const [jsonError, setJsonError] = useState<string | null>(null);

  // Prompt fields local state
  const [systemPersona, setSystemPersona] = useState<string>("");
  const [systemHardRules, setSystemHardRules] = useState<string>("");
  const [systemGoal, setSystemGoal] = useState<string>("");

  const [isMounted, setIsMounted] = useState(false);

  const isEditMode = useMemo(() => {
    if (typeof window === "undefined") return false;
    try {
      const draft = localStorage.getItem("agent_wizard_draft");
      if (draft) {
        const parsed = JSON.parse(draft);
        return parsed.isEdit === true && !!parsed.editingAgentId;
      }
    } catch {
      return false;
    }
    return false;
  }, []);

  const editingAgentId = useMemo(() => {
    if (typeof window === "undefined") return null;
    try {
      const draft = localStorage.getItem("agent_wizard_draft");
      if (draft) {
        const parsed = JSON.parse(draft);
        return parsed.isEdit ? parsed.editingAgentId : null;
      }
    } catch {
      return null;
    }
    return null;
  }, []);

  // Initialize prompt fields from config or defaults
  useEffect(() => {
    setSystemPersona(config.system_persona || DEFAULT_PERSONA);
    setSystemHardRules(config.system_hard_rules || DEFAULT_HARD_RULES);
    setSystemGoal(config.system_goal || DEFAULT_GOAL);
  }, [config.system_persona, config.system_hard_rules, config.system_goal]);

  useEffect(() => {
    setIsMounted(true);
  }, []);

  const agentConfig = useMemo(() => {
    const baseConfig = editedConfig || formDataToAgentConfig(config as AgentConfigFormData);
    if (baseConfig.prompts?.system) {
      baseConfig.prompts.system.persona = systemPersona || DEFAULT_PERSONA;
      baseConfig.prompts.system.hard_rules = systemHardRules || DEFAULT_HARD_RULES;
      baseConfig.prompts.system.goal = systemGoal || DEFAULT_GOAL;
    }
    return baseConfig;
  }, [config, editedConfig, systemPersona, systemHardRules, systemGoal]);

  const yamlPreview = useMemo(() => {
    if (!isMounted) return "";
    try {
      return JSON.stringify(agentConfig, null, 2);
    } catch {
      return "Error generating preview";
    }
  }, [agentConfig, isMounted]);

  const handleCreate = async () => {
    let agentId = isEditMode ? editingAgentId : config.agent_id;

    if (!isEditMode && !agentId && config.company_display_name) {
      agentId = generateAgentId(config.company_display_name, config.agent_display_name);
    }

    if (!agentId) {
      setError("Agent ID is required. Please fill in the company name.");
      return;
    }

    if (editMode === "yaml") {
      if (!editedConfig || jsonError) {
        setError(`Invalid JSON configuration. Please fix the errors before ${isEditMode ? "updating" : "creating"} the agent.`);
        return;
      }
    }

    setIsSubmitting(true);
    setError(null);

    try {
      const finalConfig =
        editMode === "yaml" && editedConfig
          ? editedConfig
          : formDataToAgentConfig({ ...config, agent_id: agentId } as AgentConfigFormData);

      // Apply prompt edits
      if (finalConfig.prompts?.system) {
        finalConfig.prompts.system.persona = systemPersona || DEFAULT_PERSONA;
        finalConfig.prompts.system.hard_rules = systemHardRules || DEFAULT_HARD_RULES;
        finalConfig.prompts.system.goal = systemGoal || DEFAULT_GOAL;
      }

      finalConfig.agent_id = agentId;

      let successAgentId = agentId;

      if (isEditMode) {
        await api.updateAgent(agentId, finalConfig);
      } else {
        let finalAgentId = agentId;
        let attempts = 0;
        const maxAttempts = 10;

        while (attempts < maxAttempts) {
          try {
            finalConfig.agent_id = finalAgentId;
            await api.createAgent(finalAgentId, finalConfig);
            successAgentId = finalAgentId;
            break;
          } catch (err) {
            const isConflictError =
              err instanceof ApiError &&
              (err.code === "409" || err.message.includes("already exists"));

            if (isConflictError && attempts < maxAttempts - 1) {
              attempts++;
              const baseId = finalAgentId.length > 45 ? finalAgentId.substring(0, 45) : finalAgentId;
              finalAgentId = `${baseId}_${attempts + 1}`;
              continue;
            } else {
              if (err instanceof ApiError) {
                if (isConflictError && attempts >= maxAttempts - 1) {
                  setError(`Agent ID "${finalAgentId}" already exists. Please edit the Agent ID manually in the JSON Editor.`);
                } else {
                  setError(err.message);
                }
              } else {
                setError("Failed to create agent. Please try again.");
              }
              return;
            }
          }
        }
      }

      const result: AgentWizardSuccessResult = {
        agentId: successAgentId,
        isCreate: !isEditMode,
        ragEnabled: !!finalConfig.rag?.enabled,
      };
      await onSubmit(result);
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err.message);
      } else {
        setError(`Failed to ${isEditMode ? "update" : "create"} agent. Please try again.`);
      }
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleYAMLChange = (value: string) => {
    try {
      const parsed = JSON.parse(value);
      setEditedConfig(parsed);
      setJsonError(null);
      setError(null);
    } catch {
      setEditedConfig(null);
      setJsonError("Invalid JSON syntax");
    }
  };

  const submitting = isSubmitting || externalIsSubmitting;

  const tabButton = (mode: typeof editMode, label: string) => (
    <Button
      variant={editMode === mode ? "primary" : "secondary"}
      size="sm"
      onClick={() => {
        setEditMode(mode);
        if (mode !== "yaml") {
          setEditedConfig(null);
          setJsonError(null);
        }
      }}
    >
      {label}
    </Button>
  );

  return (
    <div className="space-y-6">
      <div>
        <h3 className="text-lg font-semibold text-gray-900 mb-4">
          {isEditMode ? "Review and Update Configuration" : "Review Configuration"}
        </h3>
        <p className="text-sm text-gray-600 mb-6">
          {isEditMode
            ? "Review your agent configuration before updating."
            : "Review your agent configuration before creating."}
        </p>
      </div>

      {/* Summary */}
      <div className="bg-gray-50 rounded-sm border border-gray-200 p-6">
        <h4 className="text-md font-medium text-gray-900 mb-4">Summary</h4>
        <div className="space-y-2 text-sm">
          <div className="flex justify-between gap-4">
            <span className="text-gray-600 shrink-0">Agent ID:</span>
            <span className="font-medium text-gray-900 text-right break-all">
              {config.agent_id || "Not set"}
            </span>
          </div>
          <div className="flex justify-between gap-4">
            <span className="text-gray-600 shrink-0">Company:</span>
            <span className="font-medium text-gray-900 text-right">
              {config.company_display_name || "Not set"}
            </span>
          </div>
          <div className="flex justify-between gap-4">
            <span className="text-gray-600 shrink-0">Agent:</span>
            <span className="font-medium text-gray-900 text-right">
              {config.agent_display_name || "Not set"}
            </span>
          </div>
          <div className="flex justify-between gap-4">
            <span className="text-gray-600 shrink-0">RAG Enabled:</span>
            <span className="font-medium text-gray-900">
              {config.rag_enabled ? "Yes" : "No"}
            </span>
          </div>
          <div className="flex justify-between gap-4">
            <span className="text-gray-600 shrink-0">Examples:</span>
            <span className="font-medium text-gray-900">
              {config.examples?.length || 0}
            </span>
          </div>
          <div className="flex justify-between gap-4">
            <span className="text-gray-600 shrink-0">Escalation Rules:</span>
            <span className="font-medium text-gray-900">
              {config.escalation_rules?.length || 0} custom
            </span>
          </div>
          <div className="flex justify-between gap-4">
            <span className="text-gray-600 shrink-0">Model:</span>
            <span className="font-medium text-gray-900">
              {config.llm_model || "gpt-4o-mini"}
            </span>
          </div>
        </div>
      </div>

      {/* Configuration views */}
      <div>
        <div className="flex flex-wrap items-center justify-between gap-2 mb-3">
          <h4 className="text-md font-medium text-gray-900">
            Configuration
          </h4>
          <div className="flex flex-wrap gap-2">
            {tabButton("form", "Summary")}
            {tabButton("prompt", "Edit Prompts")}
            {tabButton("yaml", "JSON Editor")}
          </div>
        </div>

        {editMode === "yaml" ? (
          <>
            <YAMLEditor
              value={yamlPreview}
              onChange={handleYAMLChange}
              readOnly={false}
              height="500px"
              language="json"
              error={jsonError || undefined}
            />
            <p className="mt-2 text-xs text-gray-500">
              You can edit the JSON configuration directly. Changes will be applied when you create the agent.
            </p>
          </>
        ) : editMode === "prompt" ? (
          <div className="space-y-5">
            <div className="p-3 bg-[#EEEAE7] border border-[#D0CBC8] rounded-sm">
              <p className="text-xs text-[#443C3C]">
                Customize the system prompts that guide the agent&apos;s behaviour. Leave blank to use the default templates. Available placeholders: <code className="bg-white px-1 rounded">{"{agent_display_name}"}</code>, <code className="bg-white px-1 rounded">{"{company_display_name}"}</code>.
              </p>
            </div>

            <Textarea
              label="Persona"
              value={systemPersona}
              onChange={(e) => setSystemPersona(e.target.value)}
              rows={6}
              placeholder={DEFAULT_PERSONA}
              helperText="How the agent presents itself — its identity, tone, and role."
            />

            <Textarea
              label="Hard Rules"
              value={systemHardRules}
              onChange={(e) => setSystemHardRules(e.target.value)}
              rows={7}
              placeholder={DEFAULT_HARD_RULES}
              helperText="Absolute boundaries — what the agent must never do, regardless of context."
            />

            <Textarea
              label="Goal"
              value={systemGoal}
              onChange={(e) => setSystemGoal(e.target.value)}
              rows={4}
              placeholder={DEFAULT_GOAL}
              helperText="The agent's primary objective — what success looks like in each conversation."
            />
          </div>
        ) : (
          <div className="border border-gray-300 rounded-sm p-4 bg-gray-50 max-h-[500px] overflow-auto">
            <pre className="text-xs font-mono text-gray-700 whitespace-pre-wrap">
              {yamlPreview}
            </pre>
          </div>
        )}
      </div>

      {/* Error */}
      {error && (
        <div className="p-4 bg-red-50 border border-red-200 rounded-sm">
          <p className="text-sm text-red-600">{error}</p>
        </div>
      )}

      {/* Loading */}
      {submitting && (
        <div className="flex items-center justify-center py-8">
          <LoadingSpinner size="lg" />
          <span className="ml-3 text-gray-600">
            {isEditMode ? "Updating agent..." : "Creating agent..."}
          </span>
        </div>
      )}

      {/* Actions */}
      {!submitting && (
        <div className="flex flex-wrap items-center justify-between gap-3 pt-6 border-t border-gray-200">
          <div className="flex items-center gap-2">
            {onBack && (
              <Button variant="secondary" onClick={onBack} disabled={submitting}>
                Back
              </Button>
            )}
            {(hasDraft || onStartOver) && (
              <Button
                variant="ghost"
                onClick={onStartOver}
                disabled={submitting}
                className="text-gray-600 hover:text-gray-900"
              >
                Start Over
              </Button>
            )}
          </div>
          <Button variant="primary" onClick={handleCreate} size="lg">
            {isEditMode ? "Update Agent" : "Create Agent"}
          </Button>
        </div>
      )}
    </div>
  );
};
