/** Step 6: Review and Create. */

"use client";

import React, { useState, useMemo, useEffect } from "react";
import { Button } from "@/components/shared/Button";
import { LoadingSpinner } from "@/components/shared/LoadingSpinner";
import { YAMLEditor } from "@/components/shared/YAMLEditor";
import { Textarea } from "@/components/shared/Textarea";
import { api, ApiError } from "@/lib/api";
import type { AgentConfigFormData } from "@/lib/utils/agentConfig";
import { formDataToAgentConfig, generateAgentId } from "@/lib/utils/agentConfig";

interface ReviewStepProps {
  config: Partial<AgentConfigFormData>;
  isSubmitting?: boolean;
  onSubmit: () => Promise<void> | void;
  onStartOver?: () => void;
  onBack?: () => void;
  hasDraft?: boolean;
}

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
  const [editedConfig, setEditedConfig] = useState<Record<string, any> | null>(
    null
  );
  const [jsonError, setJsonError] = useState<string | null>(null);
  const [systemPersona, setSystemPersona] = useState<string>("");
  const [isMounted, setIsMounted] = useState(false);
  
  // Check if we're editing an existing agent
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

  // Initialize system persona from config or generate default
  useEffect(() => {
    if (config.system_persona) {
      setSystemPersona(config.system_persona);
    } else if (config.agent_display_name && config.clinic_display_name) {
      const specialtyPart = config.specialty ? `\nТвоя специализация: {specialty}.` : "";
      setSystemPersona(
        `Ты общаешься от лица агента {agent_display_name} из компании {clinic_display_name}.${specialtyPart}\nТвой стиль — дружелюбный и профессиональный. Ты помогаешь с информацией и записью.\nТы НЕ ведёшь медицинскую консультацию в чате.`
      );
    }
  }, [config.system_persona, config.agent_display_name, config.clinic_display_name, config.specialty]);

  // Mark component as mounted to avoid SSR hydration issues
  useEffect(() => {
    setIsMounted(true);
  }, []);

  // Generate YAML preview
  const agentConfig = useMemo(() => {
    const baseConfig = editedConfig || formDataToAgentConfig(config as AgentConfigFormData);
    // Update system persona if edited
    if (systemPersona && baseConfig.prompts?.system) {
      baseConfig.prompts.system.persona = systemPersona;
    }
    return baseConfig;
  }, [config, editedConfig, systemPersona]);

  // Generate YAML preview only on client side
  const yamlPreview = useMemo(() => {
    if (!isMounted) {
      return ""; // Return empty string during SSR
    }
    try {
      // Convert to YAML-like format (JSON with proper indentation)
      return JSON.stringify(agentConfig, null, 2);
    } catch {
      return "Error generating preview";
    }
  }, [agentConfig, isMounted]);

  const handleCreate = async () => {
    // In edit mode, use the existing agent_id
    let agentId = isEditMode ? editingAgentId : config.agent_id;
    
    // For new agents, ensure agent_id is generated if missing
    if (!isEditMode && !agentId && config.clinic_display_name) {
      agentId = generateAgentId(
        config.clinic_display_name,
        config.agent_display_name
      );
    }
    
    if (!agentId) {
      setError("Agent ID is required. Please fill in the company name.");
      return;
    }

    // Validate JSON if in YAML edit mode
    if (editMode === "yaml") {
      if (!editedConfig || jsonError) {
        setError(`Invalid JSON configuration. Please fix the errors before ${isEditMode ? "updating" : "creating"} the agent.`);
        return;
      }
    }

    setIsSubmitting(true);
    setError(null);

    try {
      // Use edited config if in YAML mode, otherwise use form data
      const finalConfig =
        editMode === "yaml" && editedConfig
          ? editedConfig
          : formDataToAgentConfig({ ...config, agent_id: agentId } as AgentConfigFormData);

      // Update system persona if edited
      if (systemPersona && finalConfig.prompts?.system) {
        finalConfig.prompts.system.persona = systemPersona;
      }

      // Ensure agent_id is set in config
      finalConfig.agent_id = agentId;

      if (isEditMode) {
        // Update existing agent
        await api.updateAgent(agentId, finalConfig);
      } else {
        // Create new agent, handle ID conflicts by adding suffix
        let finalAgentId = agentId;
        let attempts = 0;
        const maxAttempts = 10;

        while (attempts < maxAttempts) {
          try {
            finalConfig.agent_id = finalAgentId;
            await api.createAgent(finalAgentId, finalConfig);
            break; // Success, exit loop
          } catch (err) {
            // Check if it's a conflict error (409) and we can retry with suffix
            const isConflictError =
              err instanceof ApiError &&
              (err.code === "409" || err.message.includes("already exists"));
            
            if (isConflictError && attempts < maxAttempts - 1) {
              // Agent ID already exists, try with suffix
              attempts++;
              // Keep base ID shorter to leave room for suffix (max 3 chars for _10)
              // Agent ID max length is 50, so we keep base at 45 to allow _10
              const baseId = finalAgentId.length > 45 ? finalAgentId.substring(0, 45) : finalAgentId;
              finalAgentId = `${baseId}_${attempts + 1}`;
              continue; // Retry with new ID
            } else {
              // Other error or max attempts reached
              if (err instanceof ApiError) {
                if (isConflictError && attempts >= maxAttempts - 1) {
                  setError(
                    `Agent ID "${finalAgentId}" already exists. Please edit the Agent ID manually in the JSON Editor to make it unique.`
                  );
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
      
      // Success - call onSubmit to trigger success handler in parent
      await onSubmit();
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
    } catch (e) {
      // Invalid JSON - keep the value but show error
      setEditedConfig(null);
      setJsonError("Invalid JSON syntax");
    }
  };

  const submitting = isSubmitting || externalIsSubmitting;

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
          <div className="flex justify-between">
            <span className="text-gray-600">Agent ID:</span>
            <span className="font-medium text-gray-900">
              {config.agent_id || "Not set"}
            </span>
          </div>
          <div className="flex justify-between">
            <span className="text-gray-600">Company:</span>
            <span className="font-medium text-gray-900">
              {config.clinic_display_name || "Not set"}
            </span>
          </div>
          <div className="flex justify-between">
            <span className="text-gray-600">Agent:</span>
            <span className="font-medium text-gray-900">
              {config.agent_display_name || "Not set"}
            </span>
          </div>
          <div className="flex justify-between">
            <span className="text-gray-600">Specialty:</span>
            <span className="font-medium text-gray-900">
              {config.specialty || "Not set"}
            </span>
          </div>
          <div className="flex justify-between">
            <span className="text-gray-600">RAG Enabled:</span>
            <span className="font-medium text-gray-900">
              {config.rag_enabled ? "Yes" : "No"}
            </span>
          </div>
          {config.rag_enabled && (
            <div className="flex justify-between">
              <span className="text-gray-600">RAG Documents:</span>
              <span className="font-medium text-gray-900">
                {config.rag_documents?.length || 0}
              </span>
            </div>
          )}
          <div className="flex justify-between">
            <span className="text-gray-600">Examples:</span>
            <span className="font-medium text-gray-900">
              {config.examples?.length || 0}
            </span>
          </div>
        </div>
      </div>

      {/* YAML/JSON Editor */}
      <div>
        <div className="flex items-center justify-between mb-2">
          <h4 className="text-md font-medium text-gray-900">
            Configuration Preview
          </h4>
          <div className="flex gap-2">
            <Button
              variant={editMode === "form" ? "primary" : "secondary"}
              size="sm"
              onClick={() => {
                setEditMode("form");
                setEditedConfig(null);
                setJsonError(null);
              }}
            >
              Summary
            </Button>
            <Button
              variant={editMode === "prompt" ? "primary" : "secondary"}
              size="sm"
              onClick={() => {
                setEditMode("prompt");
                setJsonError(null);
              }}
            >
              Edit Prompt
            </Button>
            <Button
              variant={editMode === "yaml" ? "primary" : "secondary"}
              size="sm"
              onClick={() => {
                setEditMode("yaml");
                setJsonError(null);
              }}
            >
              JSON Editor
            </Button>
          </div>
        </div>
        {editMode === "yaml" ? (
          <YAMLEditor
            value={yamlPreview}
            onChange={handleYAMLChange}
            readOnly={false}
            height="500px"
            language="json"
            error={jsonError || undefined}
          />
        ) : editMode === "prompt" ? (
          <div className="space-y-4">
            <Textarea
              label="System Persona Prompt"
              value={systemPersona}
              onChange={(e) => setSystemPersona(e.target.value)}
              rows={10}
              placeholder="Enter the system persona prompt that defines how the agent communicates..."
              helperText="This prompt defines the agent's personality and communication style. Use {agent_display_name} and {clinic_display_name} (company name) as placeholders."
            />
            <div className="p-4 bg-blue-50 border border-blue-200 rounded-sm">
              <p className="text-sm text-blue-800">
                <strong>Tip:</strong> The prompt will be used to set the agent's personality. Make sure to include placeholders for agent and company names if needed.
              </p>
            </div>
          </div>
        ) : (
          <div className="border border-gray-300 rounded-sm p-4 bg-gray-50 max-h-[500px] overflow-auto">
            <pre className="text-xs font-mono text-gray-700 whitespace-pre-wrap">
              {yamlPreview}
            </pre>
          </div>
        )}
        {editMode === "yaml" && (
          <p className="mt-2 text-xs text-gray-500">
            You can edit the JSON configuration directly. Changes will be applied when you create the agent.
          </p>
        )}
      </div>

      {/* Error Message */}
      {error && (
        <div className="p-4 bg-red-50 border border-red-200 rounded-sm">
          <p className="text-sm text-red-600">{error}</p>
        </div>
      )}

      {/* Loading State */}
      {submitting && (
        <div className="flex items-center justify-center py-8">
          <LoadingSpinner size="lg" />
          <span className="ml-3 text-gray-600">
            {isEditMode ? "Updating agent and indexing documents..." : "Creating agent and indexing documents..."}
          </span>
        </div>
      )}

      {/* Action Buttons */}
      {!submitting && (
        <div className="flex items-center justify-between pt-6 border-t border-gray-200">
          <div className="flex items-center gap-2">
            {onBack && (
              <Button
                variant="secondary"
                onClick={onBack}
                disabled={submitting}
              >
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
          <div>
            <Button variant="primary" onClick={handleCreate} size="lg">
              {isEditMode ? "Update Agent" : "Create Agent"}
            </Button>
          </div>
        </div>
      )}
    </div>
  );
};

