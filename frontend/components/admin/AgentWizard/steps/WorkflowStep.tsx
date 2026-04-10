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
      <div className="flex items-center justify-between p-4 border border-[#BEBAB7] rounded-lg bg-[#FAFAFA] flex-shrink-0">
        <div>
          <p className="font-medium text-[#251D1C]">Сценарный Workflow</p>
          <p className="text-sm text-[#9A9590] mt-0.5">
            Если выключено — агент работает как обычный чат без шагов
          </p>
        </div>
        <Toggle
          checked={workflowEnabled}
          onChange={() => onUpdate({ workflow_enabled: !workflowEnabled })}
        />
      </div>

      {/* Canvas */}
      {workflowEnabled && (
        <div className="flex-1 min-h-0" style={{ height: "560px" }}>
          <WorkflowCanvas config={config} errors={errors} onUpdate={onUpdate} />
        </div>
      )}
    </div>
  );
}
