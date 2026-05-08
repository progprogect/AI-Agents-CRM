/** Right-side panel for editing the selected step node or transition edge. */

"use client";

import { useState, type KeyboardEvent } from "react";
import type { Edge } from "@xyflow/react";
import { Clock, Plus, ShieldCheck, Trash2, X } from "lucide-react";
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
  /** All canvas edges (used to show outgoing transitions in the step panel) */
  edges: Edge[];
  onUpdateStep: (stepId: string, patch: Partial<WorkflowFormStep>) => void;
  onDeleteStep: (stepId: string) => void;
  onUpdateEdge: (edgeId: string, data: { condition: string; is_forced: boolean; is_fallback: boolean }) => void;
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

// ── Quick-replies sub-panel ────────────────────────────────────────────────────

const MAX_QUICK_REPLIES = 8;

function QuickRepliesSection({
  quickReplies,
  onUpdate,
}: {
  quickReplies: string[];
  onUpdate: (value: string[]) => void;
}) {
  const [inputValue, setInputValue] = useState("");

  const addReply = () => {
    const trimmed = inputValue.trim();
    if (!trimmed || quickReplies.includes(trimmed) || quickReplies.length >= MAX_QUICK_REPLIES) {
      return;
    }
    onUpdate([...quickReplies, trimmed]);
    setInputValue("");
  };

  const removeReply = (label: string) => {
    onUpdate(quickReplies.filter((r) => r !== label));
  };

  const handleKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter") {
      e.preventDefault();
      addReply();
    }
  };

  return (
    <Section title="Быстрые ответы">
      <div className="space-y-3">
        <p className="text-xs text-[#9A9590]">
          Необязательно. Кнопки отобразятся в чате и Telegram после ответа агента на этом шаге. Пользователь может нажать кнопку или написать свой ответ.
        </p>

        {quickReplies.length > 0 && (
          <div className="flex flex-wrap gap-1.5">
            {quickReplies.map((label) => (
              <span
                key={label}
                className="inline-flex items-center gap-1 px-2.5 py-1 text-xs rounded-full bg-[#251D1C]/8 border border-[#251D1C]/20 text-[#251D1C]"
              >
                {label}
                <button
                  type="button"
                  onClick={() => removeReply(label)}
                  className="hover:text-red-500 transition-colors"
                  aria-label={`Удалить кнопку "${label}"`}
                >
                  <X size={11} />
                </button>
              </span>
            ))}
          </div>
        )}

        {quickReplies.length < MAX_QUICK_REPLIES && (
          <div className="flex gap-2">
            <input
              type="text"
              value={inputValue}
              onChange={(e) => setInputValue(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Текст кнопки..."
              maxLength={40}
              className="flex-1 text-sm px-3 py-1.5 border border-[#251D1C]/30 rounded-sm focus:outline-none focus:border-[#251D1C]/60 bg-white text-[#251D1C] placeholder:text-[#9A9590]"
            />
            <button
              type="button"
              onClick={addReply}
              disabled={!inputValue.trim()}
              className="px-2.5 py-1.5 rounded-sm border border-[#251D1C]/30 hover:bg-gray-50 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
              aria-label="Добавить кнопку"
            >
              <Plus size={14} />
            </button>
          </div>
        )}

        {quickReplies.length >= MAX_QUICK_REPLIES && (
          <p className="text-xs text-[#9A9590]">Максимум {MAX_QUICK_REPLIES} кнопок.</p>
        )}
      </div>
    </Section>
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

// ── Inline transition row ──────────────────────────────────────────────────────

function TransitionRow({
  edge,
  targetStep,
  hasDuplicateFallback,
  onUpdate,
  onDelete,
}: {
  edge: Edge;
  targetStep: WorkflowFormStep | undefined;
  /** True when another edge from the same source is already marked as fallback */
  hasDuplicateFallback: boolean;
  onUpdate: (edgeId: string, data: { condition: string; is_forced: boolean; is_fallback: boolean }) => void;
  onDelete: (edgeId: string) => void;
}) {
  const condition = (edge.data as { condition?: string })?.condition ?? "";
  const is_forced = (edge.data as { is_forced?: boolean })?.is_forced ?? false;
  const is_fallback = (edge.data as { is_fallback?: boolean })?.is_fallback ?? false;

  return (
    <div className={`border rounded-md p-3 space-y-2 bg-white ${is_fallback ? "border-[#9A9590]" : "border-[#BEBAB7]"}`}>
      {targetStep && (
        <div className="flex items-center justify-between">
          <p className="text-[10px] text-[#9A9590]">
            → <span className="font-medium text-[#443C3C]">{targetStep.name || targetStep.id}</span>
          </p>
          {is_fallback && (
            <span className="text-[10px] px-1.5 py-0.5 rounded bg-[#EEEAE7] text-[#9A9590] font-medium">
              Иначе
            </span>
          )}
        </div>
      )}

      {/* Fallback toggle */}
      <div className="flex items-center gap-2">
        <Toggle
          checked={is_fallback}
          onChange={() => {
            if (!is_fallback) {
              // Enabling fallback: clear condition and disable is_forced
              onUpdate(edge.id, { condition: "", is_forced: false, is_fallback: true });
            } else {
              onUpdate(edge.id, { condition, is_forced, is_fallback: false });
            }
          }}
        />
        <span className="text-xs text-[#443C3C]">Ветка «Иначе» (если ни одно условие не выполнено)</span>
      </div>

      {/* Warning: duplicate fallback */}
      {is_fallback && hasDuplicateFallback && (
        <p className="text-[10px] text-amber-600">
          Уже есть другая ветка «Иначе» из этого шага. Сработает первая по порядку.
        </p>
      )}

      {/* Condition textarea — hidden when is_fallback */}
      {!is_fallback && (
        <Textarea
          label="Условие перехода"
          value={condition}
          onChange={(e) => onUpdate(edge.id, { condition: e.target.value, is_forced, is_fallback: false })}
          rows={2}
          placeholder="Например: пользователь указал породу питомца"
        />
      )}

      <div className="flex items-center justify-between">
        {/* is_forced — disabled when is_fallback is on */}
        <div className={`flex items-center gap-2 ${is_fallback ? "opacity-40 pointer-events-none" : ""}`}>
          <Toggle
            checked={is_forced}
            onChange={() => onUpdate(edge.id, { condition, is_forced: !is_forced, is_fallback: false })}
          />
          <span className="text-xs text-[#443C3C]">Жёсткое (нельзя пропустить)</span>
        </div>
        <button
          type="button"
          onClick={() => onDelete(edge.id)}
          className="text-[#9A9590] hover:text-red-500 transition-colors"
          title="Удалить переход"
        >
          <Trash2 size={13} />
        </button>
      </div>
    </div>
  );
}

// ── Main panel ─────────────────────────────────────────────────────────────────

export function StepPanel({
  selectedStep,
  selectedEdge,
  steps,
  edges,
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
        {selectedStep && (() => {
          const outgoing = edges.filter((e) => e.source === selectedStep.id);
          return (
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

              <QuickRepliesSection
                quickReplies={selectedStep.quick_replies ?? []}
                onUpdate={(qr) => onUpdateStep(selectedStep.id, { quick_replies: qr })}
              />

              {/* ── One-time step (questionnaire integration) ── */}
              <Section title="Одноразовый шаг">
                <div className="space-y-3">
                  <div className="flex items-start gap-2 text-xs text-[#9A9590] bg-[#EEEAE7]/50 rounded-sm p-2.5 border border-[#BEBAB7]/50">
                    <ShieldCheck size={13} className="text-emerald-500 mt-0.5 shrink-0" />
                    <span>
                      Если пользователь уже проходил этот шаг в другом диалоге — он будет пропущен.
                      Удобно для согласия с политикой конфиденциальности.
                    </span>
                  </div>
                  <Input
                    label="Ключ поля анкеты для проверки"
                    value={selectedStep.skip_if_questionnaire_field ?? ""}
                    onChange={(e) =>
                      onUpdateStep(selectedStep.id, {
                        skip_if_questionnaire_field: e.target.value.trim() || null,
                      })
                    }
                    placeholder="Например: privacy_consent"
                  />
                  {(selectedStep.skip_if_questionnaire_field ?? "").length > 0 && (
                    <p className="text-[10px] text-[#9A9590]">
                      Шаг пропускается при старте, если поле{" "}
                      <code className="bg-[#EEEAE7] px-1 rounded">{selectedStep.skip_if_questionnaire_field}</code>{" "}
                      уже заполнено. Переход — по первой ветке «Иначе» или первому переходу.
                    </p>
                  )}
                  <div className="flex items-center gap-3">
                    <Toggle
                      checked={selectedStep.collect_to_questionnaire ?? false}
                      onChange={() =>
                        onUpdateStep(selectedStep.id, {
                          collect_to_questionnaire: !(selectedStep.collect_to_questionnaire ?? false),
                        })
                      }
                    />
                    <span className="text-sm text-[#443C3C]">Записывать ответы в анкету</span>
                  </div>
                  {(selectedStep.collect_to_questionnaire ?? false) && (
                    <p className="text-[10px] text-[#9A9590]">
                      После извлечения поля из поля «Переменные для сбора» значения сохраняются
                      в анкету пользователя и видны в разделе «Анкеты».
                    </p>
                  )}
                  <div className="flex items-center gap-3">
                    <Toggle
                      checked={selectedStep.evaluate_transition_conditions_when_collect_incomplete ?? false}
                      onChange={() =>
                        onUpdateStep(selectedStep.id, {
                          evaluate_transition_conditions_when_collect_incomplete: !(
                            selectedStep.evaluate_transition_conditions_when_collect_incomplete ?? false
                          ),
                        })
                      }
                    />
                    <span className="text-sm text-[#443C3C]">
                      Условные переходы при неполном сборе
                    </span>
                  </div>
                  {(selectedStep.evaluate_transition_conditions_when_collect_incomplete ?? false) && (
                    <p className="text-[10px] text-[#9A9590]">
                      Если включено, переходы с текстовым условием оцениваются даже пока не все поля из
                      «Переменные для сбора» заполнены (например «достаточно данных для ответа»).
                    </p>
                  )}
                </div>
              </Section>

              {/* ── Outgoing transitions ── */}
              <Section title="Переходы из этого шага">
                {outgoing.length === 0 ? (
                  <p className="text-xs text-[#9A9590]">
                    Нет переходов. Соедините этот шаг со следующим на канве, затем настройте условие здесь.
                  </p>
                ) : (
                  <div className="space-y-3">
                    {(() => {
                      const fallbackCount = outgoing.filter(
                        (e) => (e.data as { is_fallback?: boolean })?.is_fallback
                      ).length;
                      return outgoing.map((edge) => {
                        const targetStep = steps.find((s) => s.id === edge.target);
                        const thisIsFallback = (edge.data as { is_fallback?: boolean })?.is_fallback ?? false;
                        return (
                          <TransitionRow
                            key={edge.id}
                            edge={edge}
                            targetStep={targetStep}
                            hasDuplicateFallback={thisIsFallback && fallbackCount > 1}
                            onUpdate={onUpdateEdge}
                            onDelete={onDeleteEdge}
                          />
                        );
                      });
                    })()}
                  </div>
                )}
              </Section>

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
          );
        })()}

        {/* ── Edge editing ── */}
        {selectedEdge && !selectedStep && (() => {
          const edgeCondition = (selectedEdge.data as { condition?: string })?.condition ?? "";
          const edgeIsForced = (selectedEdge.data as { is_forced?: boolean })?.is_forced ?? false;
          const edgeIsFallback = (selectedEdge.data as { is_fallback?: boolean })?.is_fallback ?? false;
          return (
            <>
              <Section title="Настройка перехода">
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

                  {/* Fallback toggle */}
                  <div className="flex items-center gap-2">
                    <Toggle
                      checked={edgeIsFallback}
                      onChange={() => {
                        if (!edgeIsFallback) {
                          onUpdateEdge(selectedEdge.id, { condition: "", is_forced: false, is_fallback: true });
                        } else {
                          onUpdateEdge(selectedEdge.id, { condition: edgeCondition, is_forced: edgeIsForced, is_fallback: false });
                        }
                      }}
                    />
                    <span className="text-sm text-[#443C3C]">Ветка «Иначе» (если ни одно условие не выполнено)</span>
                  </div>

                  {/* Condition — hidden when fallback */}
                  {!edgeIsFallback && (
                    <Textarea
                      label="Условие (естественный язык)"
                      value={edgeCondition}
                      onChange={(e) =>
                        onUpdateEdge(selectedEdge.id, {
                          condition: e.target.value,
                          is_forced: edgeIsForced,
                          is_fallback: false,
                        })
                      }
                      rows={3}
                      placeholder="Например: пользователь указал своё имя"
                    />
                  )}

                  {/* is_forced — disabled when fallback */}
                  <div className={`flex items-center gap-3 ${edgeIsFallback ? "opacity-40 pointer-events-none" : ""}`}>
                    <Toggle
                      checked={edgeIsForced}
                      onChange={() =>
                        onUpdateEdge(selectedEdge.id, {
                          condition: edgeCondition,
                          is_forced: !edgeIsForced,
                          is_fallback: false,
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
          );
        })()}
      </div>
    </div>
  );
}
