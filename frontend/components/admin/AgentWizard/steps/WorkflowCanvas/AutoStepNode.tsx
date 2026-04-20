/** Кастомный узел для авто-шага workflow (срабатывает по таймеру, независимо от пользователя). */

"use client";

import { Handle, Position, type NodeProps } from "@xyflow/react";
import { Zap } from "lucide-react";
import type { WorkflowFormAutoStep } from "@/lib/utils/agentConfig";

interface AutoStepNodeData {
  autoStep: WorkflowFormAutoStep;
  selected?: boolean;
}

function formatDelay(seconds: number): string {
  if (seconds >= 86400 && seconds % 86400 === 0) return `${seconds / 86400} дн`;
  if (seconds >= 3600 && seconds % 3600 === 0) return `${seconds / 3600} ч`;
  if (seconds >= 60 && seconds % 60 === 0) return `${seconds / 60} мин`;
  return `${seconds} с`;
}

export function AutoStepNode({ data, selected }: NodeProps) {
  const { autoStep } = data as unknown as AutoStepNodeData;
  const delayLabel = autoStep ? formatDelay(autoStep.delay_seconds) : "";

  return (
    <div
      className={`
        relative bg-white rounded-lg shadow-sm select-none
        transition-all duration-150
        ${selected ? "border-[#7C3AED] shadow-md border-2" : "border-[#C4B5FD] hover:border-[#7C3AED] border-2"}
      `}
      style={{
        width: 220,
        minHeight: 90,
        borderStyle: "dashed",
      }}
    >
      {/* Input handle */}
      <Handle
        type="target"
        position={Position.Left}
        style={{
          background: "#C4B5FD",
          width: 10,
          height: 10,
          border: "2px solid #fff",
        }}
      />

      {/* Header */}
      <div
        className={`
          flex items-center gap-2 px-3 py-2 rounded-t-[6px] border-b
          ${selected ? "bg-[#7C3AED] border-[#7C3AED]" : "bg-[#F5F3FF] border-[#EDE9FE]"}
        `}
      >
        <Zap
          size={12}
          className={`flex-shrink-0 ${selected ? "text-yellow-300" : "text-[#7C3AED]"}`}
        />
        <span
          className={`
            text-xs font-semibold truncate flex-1
            ${selected ? "text-white" : "text-[#5B21B6]"}
          `}
          title={autoStep?.name}
        >
          {autoStep?.name || <span className="italic text-[#9A9590]">Авто-шаг</span>}
        </span>
        {delayLabel && (
          <span
            className={`
              text-[10px] font-medium flex-shrink-0 px-1.5 py-0.5 rounded
              ${selected ? "bg-purple-600 text-purple-100" : "bg-purple-100 text-purple-700"}
            `}
          >
            {delayLabel}
          </span>
        )}
      </div>

      {/* Body */}
      <div className="px-3 py-2">
        <span
          className={`
            inline-block text-[10px] font-medium px-1.5 py-0.5 rounded mb-1
            ${autoStep?.action_type === "agent"
              ? "bg-blue-50 text-blue-600"
              : "bg-gray-50 text-gray-600"}
          `}
        >
          {autoStep?.action_type === "agent" ? "Агент" : "Текст"}
        </span>
        {autoStep?.condition && (
          <p className="text-[10px] text-amber-600 truncate" title={autoStep.condition}>
            📋 {autoStep.condition}
          </p>
        )}
      </div>

      {/* Output handle */}
      <Handle
        type="source"
        position={Position.Right}
        style={{
          background: "#7C3AED",
          width: 10,
          height: 10,
          border: "2px solid #fff",
        }}
      />
    </div>
  );
}
