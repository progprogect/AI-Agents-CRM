/** Кастомный узел для шага workflow. */

"use client";

import { Handle, Position, type NodeProps } from "@xyflow/react";
import { Clock, Lock, ShieldCheck } from "lucide-react";
import type { WorkflowFormStep } from "@/lib/utils/agentConfig";

interface StepNodeData {
  step: WorkflowFormStep;
  selected?: boolean;
}

export function StepNode({ data, selected }: NodeProps) {
  const { step } = data as unknown as StepNodeData;

  const preview = step.instructions
    ? step.instructions.length > 72
      ? step.instructions.slice(0, 70) + "…"
      : step.instructions
    : "Нет инструкций";

  return (
    <div
      className={`
        relative bg-white rounded-lg border-2 shadow-sm select-none
        transition-all duration-150
        ${selected ? "border-[#251D1C] shadow-md" : "border-[#BEBAB7] hover:border-[#443C3C]"}
      `}
      style={{ width: 240, minHeight: 110 }}
    >
      {/* Input handle */}
      <Handle
        type="target"
        position={Position.Left}
        style={{
          background: "#BEBAB7",
          width: 10,
          height: 10,
          border: "2px solid #fff",
        }}
      />

      {/* Header */}
      <div
        className={`
          flex items-center gap-2 px-3 py-2 rounded-t-[6px] border-b border-[#EEEAE7]
          ${selected ? "bg-[#251D1C]" : "bg-[#FAFAFA]"}
        `}
      >
        <span
          className={`
            text-xs font-semibold truncate flex-1
            ${selected ? "text-white" : "text-[#251D1C]"}
          `}
          title={step.name}
        >
          {step.name || <span className="italic text-[#9A9590]">Без названия</span>}
        </span>

        <div className="flex items-center gap-1 flex-shrink-0">
          {step.required && (
            <span title="Обязательный шаг">
              <Lock size={11} className={selected ? "text-amber-300" : "text-amber-500"} />
            </span>
          )}
          {step.timer_trigger && (
            <span title={`Таймер: ${step.timer_trigger.delay_seconds}с`}>
              <Clock size={11} className={selected ? "text-blue-300" : "text-blue-500"} />
            </span>
          )}
          {step.skip_if_questionnaire_field && (
            <span title={`Одноразовый: пропускается если «${step.skip_if_questionnaire_field}» уже заполнено`}>
              <ShieldCheck size={11} className={selected ? "text-emerald-300" : "text-emerald-500"} />
            </span>
          )}
        </div>
      </div>

      {/* Body */}
      <div className="px-3 py-2">
        <p className="text-[11px] text-[#9A9590] leading-relaxed line-clamp-2">{preview}</p>
        {step.transitions.length > 0 && (
          <p className="mt-1 text-[10px] text-[#443C3C] font-medium">
            {step.transitions.length} переход{step.transitions.length === 1 ? "" : "а"}
          </p>
        )}
      </div>

      {/* Output handle */}
      <Handle
        type="source"
        position={Position.Right}
        style={{
          background: "#251D1C",
          width: 10,
          height: 10,
          border: "2px solid #fff",
        }}
      />
    </div>
  );
}
