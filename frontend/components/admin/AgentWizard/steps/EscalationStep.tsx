/** Step 5: Escalation Rules — contact detection toggle + free-form custom rules. */

"use client";

import React, { useCallback } from "react";
import { Plus, X } from "lucide-react";
import { useTranslations } from "next-intl";
import { Input } from "@/components/shared/Input";
import { Textarea } from "@/components/shared/Textarea";
import { Button } from "@/components/shared/Button";
import { Toggle } from "@/components/shared/Toggle";
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
  const t = useTranslations("Wizard");
  const rules: EscalationRule[] = config.escalation_rules || [];
  const detectContact = config.escalation_detect_contact ?? true;

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
          {t("escalationTitle")}
        </h3>
        <p className="text-sm text-gray-600">
          {t("escalationDesc")}
        </p>
      </div>

      {/* Built-in: contact detection */}
      <div className="p-4 border border-[#BEBAB7] rounded-sm bg-white space-y-3">
        <div className="flex items-start justify-between gap-4">
          <div>
            <p className="text-sm font-medium text-gray-900">{t("contactDetection")}</p>
            <p className="text-xs text-gray-500 mt-0.5">
              {t("contactDetectionHint")}
            </p>
          </div>
          <div className="flex-shrink-0">
            <Toggle
              checked={detectContact}
              onChange={(v) => onUpdate({ escalation_detect_contact: v })}
            />
          </div>
        </div>
      </div>

      {/* Divider */}
      <div className="relative">
        <div className="absolute inset-0 flex items-center">
          <div className="w-full border-t border-gray-200" />
        </div>
        <div className="relative flex justify-center">
          <span className="bg-white px-3 text-xs text-gray-400 uppercase tracking-wider">
            {t("customRules")}
          </span>
        </div>
      </div>

      {/* Custom rules list */}
      <div className="space-y-4">
        {rules.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-8 border border-dashed border-gray-300 rounded-sm bg-gray-50 text-center px-4">
            <p className="text-sm text-gray-500 mb-1">{t("noCustomRules")}</p>
            <p className="text-xs text-gray-400">
              {t("addRuleHint")}
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
                  {t("ruleN", { n: index + 1 })}
                </span>
                <button
                  type="button"
                  onClick={() => handleDeleteRule(rule.id)}
                  className="flex items-center justify-center w-7 h-7 rounded-sm text-gray-400 hover:text-red-500 hover:bg-red-50 transition-colors duration-150"
                  aria-label={t("ruleN", { n: index + 1 })}
                >
                  <X size={16} />
                </button>
              </div>

              <Input
                label={t("ruleName")}
                value={rule.name}
                onChange={(e) => handleUpdateRule(rule.id, "name", e.target.value)}
                placeholder={t("ruleNamePlaceholder")}
              />

              <Textarea
                label={t("description")}
                value={rule.description}
                onChange={(e) => handleUpdateRule(rule.id, "description", e.target.value)}
                placeholder={t("descriptionPlaceholder")}
                rows={3}
                helperText={t("descriptionHelper")}
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
        {t("addRule")}
        {rules.length > 0 && (
          <span className="ml-1 text-gray-400 font-normal">
            ({rules.length}/{MAX_RULES})
          </span>
        )}
      </Button>

      {rules.length >= MAX_RULES && (
        <p className="text-xs text-gray-500">
          {t("maxRulesReached", { max: MAX_RULES })}
        </p>
      )}
    </div>
  );
};
