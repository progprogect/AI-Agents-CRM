/** Step 5: Escalation Rules — free-form custom rules. */

"use client";

import React, { useCallback } from "react";
import { Plus, X } from "lucide-react";
import { Input } from "@/components/shared/Input";
import { Textarea } from "@/components/shared/Textarea";
import { Button } from "@/components/shared/Button";
import type { AgentConfigFormData, EscalationRule } from "@/lib/utils/agentConfig";
import type { ValidationError } from "@/lib/utils/validation";

const MAX_RULES = 5;

interface EscalationStepProps {
  config: Partial<AgentConfigFormData>;
  errors: ValidationError[];
  onUpdate: (config: Partial<AgentConfigFormData>) => void;
}

export const EscalationStep: React.FC<EscalationStepProps> = ({
  config,
  onUpdate,
}) => {
  const rules: EscalationRule[] = config.escalation_rules || [];

  const handleAddRule = useCallback(() => {
    if (rules.length >= MAX_RULES) return;
    const newRule: EscalationRule = {
      id: `rule_${Date.now()}`,
      name: "",
      description: "",
    };
    onUpdate({ escalation_rules: [...rules, newRule] });
  }, [rules, onUpdate]);

  const handleDeleteRule = useCallback(
    (id: string) => {
      onUpdate({ escalation_rules: rules.filter((r) => r.id !== id) });
    },
    [rules, onUpdate]
  );

  const handleUpdateRule = useCallback(
    (id: string, field: keyof EscalationRule, value: string) => {
      onUpdate({
        escalation_rules: rules.map((r) =>
          r.id === id ? { ...r, [field]: value } : r
        ),
      });
    },
    [rules, onUpdate]
  );

  return (
    <div className="space-y-6">
      <div>
        <h3 className="text-lg font-semibold text-gray-900 mb-2">
          Escalation Rules
        </h3>
        <p className="text-sm text-gray-600">
          Define custom rules for when the agent should escalate to a human. All rules are optional — the AI will still detect urgent or sensitive situations automatically.
        </p>
      </div>

      {/* Rules list */}
      <div className="space-y-4">
        {rules.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-10 border border-dashed border-gray-300 rounded-sm bg-gray-50 text-center px-4">
            <p className="text-sm text-gray-500 mb-1">No escalation rules added.</p>
            <p className="text-xs text-gray-400">
              Add rules to define when the agent should escalate to a human operator.
            </p>
          </div>
        ) : (
          rules.map((rule, index) => (
            <div
              key={rule.id}
              className="relative p-4 border border-[#BEBAB7] rounded-sm bg-white space-y-3"
            >
              <div className="flex items-center justify-between mb-1">
                <span className="text-xs font-semibold text-[#9A9590] uppercase tracking-wider">
                  Rule {index + 1}
                </span>
                <button
                  type="button"
                  onClick={() => handleDeleteRule(rule.id)}
                  className="flex items-center justify-center w-7 h-7 rounded-sm text-gray-400 hover:text-red-500 hover:bg-red-50 transition-colors duration-150"
                  aria-label={`Delete rule ${index + 1}`}
                >
                  <X size={16} />
                </button>
              </div>

              <Input
                label="Rule Name"
                value={rule.name}
                onChange={(e) => handleUpdateRule(rule.id, "name", e.target.value)}
                placeholder="e.g. Urgent health situation"
              />

              <Textarea
                label="Description"
                value={rule.description}
                onChange={(e) => handleUpdateRule(rule.id, "description", e.target.value)}
                placeholder="e.g. When the user mentions pain, emergency, or urgent symptoms — immediately transfer to a human and stop the conversation."
                rows={3}
                helperText="Describe the situation and what the agent should do."
              />
            </div>
          ))
        )}
      </div>

      {/* Add rule button */}
      <Button
        type="button"
        variant="secondary"
        size="sm"
        onClick={handleAddRule}
        disabled={rules.length >= MAX_RULES}
        icon={<Plus size={16} />}
      >
        Add Rule
        {rules.length > 0 && (
          <span className="ml-1 text-gray-400 font-normal">
            ({rules.length}/{MAX_RULES})
          </span>
        )}
      </Button>

      {rules.length >= MAX_RULES && (
        <p className="text-xs text-gray-500">
          Maximum of {MAX_RULES} escalation rules reached.
        </p>
      )}

      <div className="p-4 bg-[#EEEAE7] border border-[#D0CBC8] rounded-sm">
        <p className="text-sm text-[#443C3C]">
          <strong>Note:</strong> The AI automatically detects escalation triggers such as medical questions, urgent cases, and booking intents — no keywords needed. Custom rules let you add domain-specific escalation behaviour on top of that.
        </p>
      </div>
    </div>
  );
};
