/** Right-side panel for editing a selected AutoStepNode. */

"use client";

import { Trash2, X, Zap } from "lucide-react";
import { useState } from "react";
import type { WorkflowFormAutoStep } from "@/lib/utils/agentConfig";
import { Input } from "@/components/shared/Input";
import { Textarea } from "@/components/shared/Textarea";

// ── Types ──────────────────────────────────────────────────────────────────────

interface AutoStepPanelProps {
  autoStep: WorkflowFormAutoStep;
  onUpdate: (patch: Partial<WorkflowFormAutoStep>) => void;
  onDelete: () => void;
  onClose: () => void;
}

type DelayUnit = "seconds" | "minutes" | "hours" | "days";

const UNIT_LABELS: Record<DelayUnit, string> = {
  seconds: "сек",
  minutes: "мин",
  hours: "ч",
  days: "дн",
};

const UNIT_MULTIPLIERS: Record<DelayUnit, number> = {
  seconds: 1,
  minutes: 60,
  hours: 3600,
  days: 86400,
};

function detectUnit(seconds: number): DelayUnit {
  if (seconds >= 86400 && seconds % 86400 === 0) return "days";
  if (seconds >= 3600 && seconds % 3600 === 0) return "hours";
  if (seconds >= 60 && seconds % 60 === 0) return "minutes";
  return "seconds";
}

// ── Section wrapper ────────────────────────────────────────────────────────────

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="border-b border-[#EEEAE7] pb-4 mb-4">
      <p className="text-[10px] font-semibold uppercase tracking-wider text-[#9A9590] mb-3">
        {title}
      </p>
      {children}
    </div>
  );
}

// ── Panel component ────────────────────────────────────────────────────────────

export function AutoStepPanel({ autoStep, onUpdate, onDelete, onClose }: AutoStepPanelProps) {
  const [unit, setUnit] = useState<DelayUnit>(
    autoStep._delay_unit ?? detectUnit(autoStep.delay_seconds)
  );
  const [delayValue, setDelayValue] = useState<number>(
    Math.round(autoStep.delay_seconds / UNIT_MULTIPLIERS[unit]) || 1
  );

  function handleDelayChange(value: number, newUnit?: DelayUnit) {
    const u = newUnit ?? unit;
    const clamped = Math.max(1, Math.round(value));
    setDelayValue(clamped);
    if (newUnit) setUnit(newUnit);
    onUpdate({ delay_seconds: clamped * UNIT_MULTIPLIERS[u], _delay_unit: u });
  }

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="flex items-center gap-2 px-4 py-3 border-b border-[#EEEAE7] bg-[#F5F3FF]">
        <Zap size={14} className="text-[#7C3AED] flex-shrink-0" />
        <span className="text-sm font-semibold text-[#5B21B6] flex-1">Авто-шаг</span>
        <button
          onClick={onClose}
          className="p-1 rounded hover:bg-[#EDE9FE] text-[#9A9590] hover:text-[#5B21B6] transition-colors"
          aria-label="Закрыть"
        >
          <X size={14} />
        </button>
      </div>

      {/* Scrollable body */}
      <div className="flex-1 overflow-y-auto px-4 py-4 space-y-0">
        {/* Name */}
        <Section title="Название">
          <Input
            value={autoStep.name}
            onChange={(e) => onUpdate({ name: e.target.value })}
            placeholder="Название авто-шага"
          />
        </Section>

        {/* Delay */}
        <Section title="Задержка">
          <div className="flex gap-2">
            <Input
              type="number"
              min={1}
              value={delayValue}
              onChange={(e) => handleDelayChange(Number(e.target.value))}
              className="flex-1"
              placeholder="1"
            />
            <select
              value={unit}
              onChange={(e) => handleDelayChange(delayValue, e.target.value as DelayUnit)}
              className="
                rounded-lg border border-[#BEBAB7] bg-white px-3 py-2
                text-sm text-[#251D1C] focus:outline-none focus:ring-2
                focus:ring-[#7C3AED] focus:border-[#7C3AED]
              "
            >
              {(Object.keys(UNIT_LABELS) as DelayUnit[]).map((u) => (
                <option key={u} value={u}>{UNIT_LABELS[u]}</option>
              ))}
            </select>
          </div>
          <p className="mt-1 text-[11px] text-[#9A9590]">
            Итого: {autoStep.delay_seconds} сек
          </p>
        </Section>

        {/* When delay starts (source_id must be a workflow step id for on_step_exit) */}
        <Section title="Когда начинать отсчёт">
          <div className="flex gap-2">
            {(["on_step_enter", "on_step_exit"] as const).map((anchor) => (
              <button
                key={anchor}
                type="button"
                onClick={() => onUpdate({ schedule_anchor: anchor })}
                className={`
                  flex-1 py-2 text-xs rounded-lg border font-medium transition-all leading-tight
                  ${(autoStep.schedule_anchor ?? "on_step_enter") === anchor
                    ? "bg-[#7C3AED] text-white border-[#7C3AED]"
                    : "bg-white text-[#443C3C] border-[#BEBAB7] hover:border-[#7C3AED]"}
                `}
              >
                {anchor === "on_step_enter"
                  ? "При входе на шаг"
                  : "При выходе с шага"}
              </button>
            ))}
          </div>
          <p className="mt-1 text-[11px] text-[#9A9590]">
            «При входе» — задержка от перехода на шаг, указанный связью на канвасе (как раньше).
            «При выходе» — от перехода с этого шага на другой; для цепочек auto→auto оставьте «При входе».
          </p>
        </Section>

        {/* Cancel policy on workflow step change */}
        <Section title="Отмена при смене шага">
          <label className="flex cursor-pointer items-start gap-2 rounded-lg border border-[#BEBAB7] bg-white p-3 text-sm text-[#443C3C] hover:border-[#7C3AED]">
            <input
              type="checkbox"
              className="mt-0.5 h-4 w-4 shrink-0 accent-[#7C3AED]"
              checked={autoStep.cancel_on_workflow_step_change !== false}
              onChange={(e) =>
                onUpdate({ cancel_on_workflow_step_change: e.target.checked })
              }
            />
            <span>
              <span className="font-medium">Отменять, если пользователь перешёл на другой шаг workflow</span>
              <span className="mt-1 block text-[11px] text-[#9A9590]">
                Снимите галочку, чтобы таймер дождался срабатывания даже после смены шага (сброс при /restart и закрытии чата по-прежнему полный).
              </span>
            </span>
          </label>
        </Section>

        {/* Action type */}
        <Section title="Тип действия">
          <div className="flex gap-2">
            {(["static", "agent"] as const).map((t) => (
              <button
                key={t}
                onClick={() => onUpdate({ action_type: t })}
                className={`
                  flex-1 py-2 text-sm rounded-lg border font-medium transition-all
                  ${autoStep.action_type === t
                    ? "bg-[#7C3AED] text-white border-[#7C3AED]"
                    : "bg-white text-[#443C3C] border-[#BEBAB7] hover:border-[#7C3AED]"}
                `}
              >
                {t === "static" ? "Фиксированный текст" : "Ответ агента"}
              </button>
            ))}
          </div>
        </Section>

        {/* Message / Prompt */}
        {autoStep.action_type === "static" ? (
          <Section title="Текст сообщения">
            <Textarea
              value={autoStep.message_template}
              onChange={(e) => onUpdate({ message_template: e.target.value })}
              placeholder="Текст, который отправит агент. Поддерживаются переменные: {имя}, {телефон}…"
              rows={4}
            />
          </Section>
        ) : (
          <Section title="Задача для агента">
            <Textarea
              value={autoStep.prompt}
              onChange={(e) => onUpdate({ prompt: e.target.value })}
              placeholder="Что должен спросить или сделать агент? Например: «Уточни, как прошёл визит»"
              rows={4}
            />
          </Section>
        )}

        {/* Condition */}
        <Section title="Условие (необязательно)">
          <Textarea
            value={autoStep.condition ?? ""}
            onChange={(e) =>
              onUpdate({ condition: e.target.value || null })
            }
            placeholder="Отправить только если… (например: «пользователь не ответил на последний вопрос»)"
            rows={3}
          />
          <p className="mt-1 text-[11px] text-[#9A9590]">
            Условие оценивается LLM. Оставьте пустым — авто-шаг сработает всегда.
          </p>
        </Section>
      </div>

      {/* Footer — delete button */}
      <div className="px-4 py-3 border-t border-[#EEEAE7]">
        <button
          onClick={onDelete}
          className="
            w-full flex items-center justify-center gap-2 py-2 rounded-lg
            text-sm font-medium text-red-600 border border-red-200
            hover:bg-red-50 transition-colors
          "
        >
          <Trash2 size={14} />
          Удалить авто-шаг
        </button>
      </div>
    </div>
  );
}
