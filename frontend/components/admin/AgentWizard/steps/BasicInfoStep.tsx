/** Step 1: Basic Information. */

"use client";

import React, { useEffect } from "react";
import { useTranslations } from "next-intl";
import { Input } from "@/components/shared/Input";
import { Checkbox } from "@/components/shared/Checkbox";
import type { AgentConfigFormData } from "@/lib/utils/agentConfig";
import type { ValidationError } from "@/lib/utils/validation";
import { getFieldError } from "@/lib/utils/validation";
import { generateAgentId } from "@/lib/utils/agentConfig";

interface BasicInfoStepProps {
  config: Partial<AgentConfigFormData>;
  errors: ValidationError[];
  onUpdate: (config: Partial<AgentConfigFormData>) => void;
}

export const BasicInfoStep: React.FC<BasicInfoStepProps> = ({
  config,
  errors,
  onUpdate,
}) => {
  const t = useTranslations("Wizard");
  // Auto-generate agent_id when company_display_name or agent_display_name changes
  useEffect(() => {
    if (config.company_display_name && config.company_display_name.trim() !== "") {
      const generatedId = generateAgentId(
        config.company_display_name,
        config.agent_display_name
      );
      if (!config.agent_id || generatedId !== config.agent_id) {
        onUpdate({ agent_id: generatedId });
      }
    }
  }, [config.company_display_name, config.agent_display_name, config.agent_id, onUpdate]);

  const languageOptions = [
    { value: "ru", label: "Русский" },
    { value: "en", label: "English" },
    { value: "ar", label: "العربية" },
    { value: "fr", label: "Français" },
    { value: "de", label: "Deutsch" },
    { value: "es", label: "Español" },
  ];

  const handleLanguageToggle = (languageValue: string, checked: boolean) => {
    const currentLanguages = config.languages || ["ru", "en"];
    if (checked) {
      if (!currentLanguages.includes(languageValue)) {
        onUpdate({ languages: [...currentLanguages, languageValue] });
      }
    } else {
      const filtered = currentLanguages.filter((lang) => lang !== languageValue);
      if (filtered.length > 0) {
        onUpdate({ languages: filtered });
      }
    }
  };

  return (
    <div className="space-y-6">
      <div>
        <h3 className="text-lg font-semibold text-gray-900 mb-4">
          {t("basicInfoTitle")}
        </h3>
        <p className="text-sm text-gray-600 mb-6">
          {t("basicInfoDesc")}
        </p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <div className="md:col-span-2">
          <Input
            label={t("companyDisplayName")}
            value={config.company_display_name || ""}
            onChange={(e) => onUpdate({ company_display_name: e.target.value })}
            error={getFieldError(errors, "company_display_name")}
            placeholder="Acme Corp"
            required
          />
        </div>

        <div className="md:col-span-2">
          <Input
            label={t("agentDisplayName")}
            value={config.agent_display_name || ""}
            onChange={(e) => onUpdate({ agent_display_name: e.target.value })}
            error={getFieldError(errors, "agent_display_name")}
            placeholder="Support Agent"
            required
          />
        </div>

        <div className="md:col-span-2">
          <label className="block text-sm font-medium text-gray-700 mb-2">
            {t("languages")} <span className="text-red-500">*</span>
          </label>
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-2 p-4 border border-gray-300 rounded-sm bg-white">
            {languageOptions.map((option) => (
              <Checkbox
                key={option.value}
                label={option.label}
                checked={(config.languages || ["ru", "en"]).includes(option.value)}
                onChange={(checked) => handleLanguageToggle(option.value, checked)}
              />
            ))}
          </div>
          <p className="mt-1 text-xs text-gray-500">
            {t("languagesHint")}
          </p>
          {getFieldError(errors, "languages") && (
            <p className="mt-1 text-sm text-red-600">
              {getFieldError(errors, "languages")}
            </p>
          )}
        </div>
      </div>

      {/* Preview Card */}
      {(config.company_display_name || config.agent_display_name) && (
        <div className="mt-8 p-6 bg-[#EEEAE7]/10 border border-[#251D1C]/20 rounded-sm">
          <h4 className="text-sm font-medium text-gray-700 mb-4">{t("preview")}</h4>
          <div className="bg-white p-4 rounded-sm border border-[#251D1C]/20">
            <div className="flex items-start justify-between mb-2">
              <div className="flex-1 min-w-0">
                <h5 className="text-lg font-semibold text-gray-900 truncate">
                  {config.company_display_name || t("companyName")}
                </h5>
                {config.agent_display_name && (
                  <p className="text-sm text-gray-600 truncate">
                    {config.agent_display_name}
                  </p>
                )}
              </div>
            </div>
            {config.languages && config.languages.length > 0 && (
              <p className="text-xs text-gray-500 mt-2">
                Languages: {config.languages.join(", ")}
              </p>
            )}
            {config.agent_id && (
              <p className="text-xs text-gray-400 mt-1 font-mono break-all">
                ID: {config.agent_id}
              </p>
            )}
            <div className="mt-3">
              <span className="px-3 py-1 rounded-sm text-xs font-medium bg-[#EEEAE7]/20 text-[#443C3C] border border-[#251D1C]/30">
                {t("active")}
              </span>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
