/** Step 7: Workflow — visual canvas editor for multi-step conversation scenarios. */

"use client";

import { Toggle } from "@/components/shared/Toggle";
import type { AgentConfigFormData } from "@/lib/utils/agentConfig";
import type { ValidationError } from "@/lib/utils/validation";
import { WorkflowCanvas } from "./WorkflowCanvas";

interface WorkflowStepProps {
  config: Partial<AgentConfigFormData>;
  errors: ValidationError[];
  onUpdate: (config: Partial<AgentConfigFormData>) => void;
}

export function WorkflowStep({ config, errors, onUpdate }: WorkflowStepProps) {
  const workflowEnabled = config.workflow_enabled === true;

  return (
    <div className="flex flex-col h-full space-y-4">
      {/* Master toggle */}
      <div className="flex items-start justify-between gap-4 p-4 border border-[#BEBAB7] rounded-lg bg-[#FAFAFA] flex-shrink-0">
        <div className="min-w-0">
          <p className="font-medium text-[#251D1C]">Сценарный Workflow</p>
          <p className="text-sm text-[#9A9590] mt-0.5">
            Если выключено — агент работает как обычный чат без шагов. Чтобы открыть
            редактор сценария, включите переключатель.
          </p>
        </div>
        <div className="flex-shrink-0">
          <Toggle
            checked={workflowEnabled}
            onChange={() => onUpdate({ workflow_enabled: !workflowEnabled })}
          />
        </div>
      </div>

      {/* Canvas — fixed height avoids flex % height quirks (Chrome vs WebKit); matches XYFlow parent-size requirement */}
      {workflowEnabled && (
        <div className="h-[min(560px,70vh)] w-full min-h-[320px] shrink-0">
          <WorkflowCanvas config={config} errors={errors} onUpdate={onUpdate} />
        </div>
      )}
    </div>
  );
}
