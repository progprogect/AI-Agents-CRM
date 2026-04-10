/** Right-side panel for editing the selected step node or transition edge. */

"use client";

import type { Edge } from "@xyflow/react";
import { Clock, Trash2, X } from "lucide-react";
import type { WorkflowFormStep, WorkflowTimerTrigger } from "@/lib/utils/agentConfig";
import { Input } from "@/components/shared/Input";
import { Textarea } from "@/components/shared/Textarea";
import { Toggle } from "@/components/shared/Toggle";

// ── Types ─────────────────────────────────────────────────────────────────────

interface StepPanelProps {
  /** Selected step for editing (null when an edge is selected) */
  selectedStep: WorkflowFormStep | null;
  /** Selected edge for editing (null when a step is selected) */
  selectedEdge: Edge | null;
  /** All steps (for showing step name dropdown on edges) */
  steps: WorkflowFormStep[];
  onUpdateStep: (stepId: string, patch: Partial<WorkflowFormStep>) => void;
  onDeleteStep: (stepId: string) => void;
  onUpdateEdge: (edgeId: string, data: { condition: string; is_forced: boolean }) => void;
  onDeleteEdge: (edgeId: string) => void;
  onClose: () => void;
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

// ── Timer sub-panel ────────────────────────────────────────────────────────────

function TimerSection({
  timer,
  onUpdate,
}: {
  timer: WorkflowTimerTrigger | null | undefined;
  onUpdate: (t: WorkflowTimerTrigger | null) => void;
}) {
  const defaultTimer: WorkflowTimerTrigger = {
    delay_seconds: 3600,
    action_type: "static",
    message_template: "",
    prompt: null,
  };

  return (
    <Section title="Таймер бездействия">
      <div className="flex items-center gap-3 mb-3">
        <Toggle
          checked={!!timer}
          onChange={() => onUpdate(timer ? null : defaultTimer)}
        />
        <span className="text-sm text-[#443C3C] flex items-center gap-1">
          <Clock size={13} className="text-blue-500" />
          Автоматическое сообщение
        </span>
      </div>

      {timer && (
        <div className="space-y-3 pl-2 border-l-2 border-blue-200">
          <Input
            label="Задержка (секунды)"
            type="number"
            value={String(timer.delay_seconds)}
            onChange={(e) =>
              onUpdate({ ...timer, delay_seconds: Number(e.target.value) || 3600 })
            }
            placeholder="3600"
          />

          <div>
            <p className="text-xs font-medium text-[#443C3C] mb-1.5">Тип действия</p>
            <div className="flex rounded border border-[#BEBAB7] overflow-hidden text-xs w-fit">
              {(["static", "agent"] as const).map((type) => (
                <button
                  key={type}
                  type="button"
                  onClick={() => onUpdate({ ...timer, action_type: type })}
                  className={`px-3 py-1.5 transition-colors ${
                    (timer.action_type || "static") === type
                      ? "bg-[#251D1C] text-white"
                      : "bg-white text-[#443C3C] hover:bg-[#EEEAE7]"
                  } ${type === "agent" ? "border-l border-[#BEBAB7]" : ""}`}
                >
                  {type === "static" ? "Фиксированный текст" : "Ответ агента (AI)"}
                </button>
              ))}
            </div>
          </div>

          {(timer.action_type || "static") === "static" ? (
            <Textarea
              label="Текст сообщения"
              value={timer.message_template}
              onChange={(e) => onUpdate({ ...timer, message_template: e.target.value })}
              rows={3}
              placeholder="Привет! Могу ли я чем-то помочь?"
            />
          ) : (
            <Textarea
              label="Инструкция для агента"
              value={timer.prompt ?? ""}
              onChange={(e) => onUpdate({ ...timer, prompt: e.target.value })}
              rows={3}
              placeholder="Напомни пользователю о незавершённом вопросе, учитывая контекст разговора."
            />
          )}

          <p className="text-[10px] text-[#9A9590]">
            {(timer.action_type || "static") === "static"
              ? "Поддерживается подстановка {переменных} из собранных данных шага."
              : "Агент сформулирует сообщение по инструкции с учётом истории диалога."}
          </p>
        </div>
      )}
    </Section>
  );
}

// ── Main panel ─────────────────────────────────────────────────────────────────

export function StepPanel({
  selectedStep,
  selectedEdge,
  steps,
  onUpdateStep,
  onDeleteStep,
  onUpdateEdge,
  onDeleteEdge,
  onClose,
}: StepPanelProps) {
  if (!selectedStep && !selectedEdge) return null;

  return (
    <div className="flex flex-col h-full bg-white border-l border-[#BEBAB7] overflow-y-auto">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-[#EEEAE7] flex-shrink-0">
        <p className="text-sm font-semibold text-[#251D1C]">
          {selectedStep ? "Настройка шага" : "Настройка перехода"}
        </p>
        <button
          type="button"
          onClick={onClose}
          className="text-[#9A9590] hover:text-[#251D1C] transition-colors"
          title="Закрыть"
        >
          <X size={16} />
        </button>
      </div>

      <div className="flex-1 overflow-y-auto px-4 py-4">
        {/* ── Step editing ── */}
        {selectedStep && (
          <>
            <Section title="Основное">
              <div className="space-y-3">
                <Input
                  label="Название шага"
                  value={selectedStep.name}
                  onChange={(e) => onUpdateStep(selectedStep.id, { name: e.target.value })}
                  placeholder="Приветствие, Сбор данных, Финал…"
                />
                <Textarea
                  label="Инструкции для агента"
                  value={selectedStep.instructions}
                  onChange={(e) =>
                    onUpdateStep(selectedStep.id, { instructions: e.target.value })
                  }
                  rows={5}
                  placeholder="Что агент должен делать, спрашивать или сообщать пользователю на этом шаге"
                />
                <div className="flex items-center gap-3">
                  <Toggle
                    checked={selectedStep.required}
                    onChange={() =>
                      onUpdateStep(selectedStep.id, { required: !selectedStep.required })
                    }
                  />
                  <span className="text-sm text-[#443C3C]">
                    Обязательный шаг (нельзя пропустить)
                  </span>
                </div>
              </div>
            </Section>

            <TimerSection
              timer={selectedStep.timer_trigger}
              onUpdate={(t) =>
                onUpdateStep(selectedStep.id, { timer_trigger: t ?? undefined })
              }
            />

            <div className="pt-2">
              <button
                type="button"
                onClick={() => onDeleteStep(selectedStep.id)}
                className="flex items-center gap-2 text-sm text-red-500 hover:text-red-700 transition-colors"
              >
                <Trash2 size={14} />
                Удалить шаг
              </button>
            </div>
          </>
        )}

        {/* ── Edge editing ── */}
        {selectedEdge && !selectedStep && (
          <>
            <Section title="Условие перехода">
              <div className="space-y-3">
                <div className="text-xs text-[#9A9590] mb-2">
                  {(() => {
                    const from = steps.find((s) => s.id === selectedEdge.source);
                    const to = steps.find((s) => s.id === selectedEdge.target);
                    return from && to ? (
                      <span>
                        <span className="font-medium text-[#443C3C]">{from.name || from.id}</span>
                        {" → "}
                        <span className="font-medium text-[#443C3C]">{to.name || to.id}</span>
                      </span>
                    ) : null;
                  })()}
                </div>

                <Textarea
                  label="Условие (естественный язык)"
                  value={
                    (selectedEdge.data as { condition?: string })?.condition ??
                    (selectedEdge.label as string) ??
                    ""
                  }
                  onChange={(e) =>
                    onUpdateEdge(selectedEdge.id, {
                      condition: e.target.value,
                      is_forced:
                        (selectedEdge.data as { is_forced?: boolean })?.is_forced ?? false,
                    })
                  }
                  rows={3}
                  placeholder="Например: пользователь указал своё имя"
                />

                <div className="flex items-center gap-3">
                  <Toggle
                    checked={
                      (selectedEdge.data as { is_forced?: boolean })?.is_forced ?? false
                    }
                    onChange={() =>
                      onUpdateEdge(selectedEdge.id, {
                        condition:
                          (selectedEdge.data as { condition?: string })?.condition ?? "",
                        is_forced: !(
                          (selectedEdge.data as { is_forced?: boolean })?.is_forced ?? false
                        ),
                      })
                    }
                  />
                  <span className="text-sm text-[#443C3C]">
                    Жёсткое условие (пользователь не перейдёт дальше без выполнения)
                  </span>
                </div>
              </div>
            </Section>

            <div className="pt-2">
              <button
                type="button"
                onClick={() => onDeleteEdge(selectedEdge.id)}
                className="flex items-center gap-2 text-sm text-red-500 hover:text-red-700 transition-colors"
              >
                <Trash2 size={14} />
                Удалить переход
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
