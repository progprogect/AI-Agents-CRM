/** Step 7: Workflow — configurable multi-step conversation scenarios. */

"use client";

import React, { useCallback } from "react";
import { Plus, X, ChevronDown, ChevronUp, Clock } from "lucide-react";
import { Input } from "@/components/shared/Input";
import { Textarea } from "@/components/shared/Textarea";
import { Button } from "@/components/shared/Button";
import { Toggle } from "@/components/shared/Toggle";
import type {
  AgentConfigFormData,
  WorkflowFormStep,
  WorkflowTransition,
} from "@/lib/utils/agentConfig";
import type { ValidationError } from "@/lib/utils/validation";

const MAX_STEPS = 10;
const MAX_TRANSITIONS = 5;

interface WorkflowStepProps {
  config: Partial<AgentConfigFormData>;
  errors: ValidationError[];
  onUpdate: (config: Partial<AgentConfigFormData>) => void;
}

function makeStepId(): string {
  return `step_${Date.now()}`;
}

function makeDefaultStep(index: number): WorkflowFormStep {
  return {
    id: `step_${index + 1}`,
    name: "",
    instructions: "",
    collect: [],
    required: false,
    transitions: [],
    timer_trigger: undefined,
  };
}

export const WorkflowStep: React.FC<WorkflowStepProps> = ({
  config,
  errors: _errors,
  onUpdate,
}) => {
  const workflowEnabled = config.workflow_enabled === true;
  const steps: WorkflowFormStep[] = config.workflow_steps || [];

  const [expandedStep, setExpandedStep] = React.useState<string | null>(null);

  // ---- Top-level handlers ----

  const toggleWorkflow = useCallback(() => {
    onUpdate({ workflow_enabled: !workflowEnabled });
  }, [workflowEnabled, onUpdate]);

  const handleAddStep = useCallback(() => {
    if (steps.length >= MAX_STEPS) return;
    const newStep = makeDefaultStep(steps.length);
    const newSteps = [...steps, newStep];
    onUpdate({ workflow_steps: newSteps, workflow_start_step_id: newSteps[0]?.id });
    setExpandedStep(newStep.id);
  }, [steps, onUpdate]);

  const handleRemoveStep = useCallback(
    (stepId: string) => {
      const newSteps = steps.filter((s) => s.id !== stepId);
      onUpdate({
        workflow_steps: newSteps,
        workflow_start_step_id: newSteps[0]?.id || "step_1",
      });
    },
    [steps, onUpdate]
  );

  const handleUpdateStep = useCallback(
    (stepId: string, patch: Partial<WorkflowFormStep>) => {
      onUpdate({
        workflow_steps: steps.map((s) =>
          s.id === stepId ? { ...s, ...patch } : s
        ),
      });
    },
    [steps, onUpdate]
  );

  // ---- Transition handlers ----

  const handleAddTransition = useCallback(
    (stepId: string) => {
      const step = steps.find((s) => s.id === stepId);
      if (!step || step.transitions.length >= MAX_TRANSITIONS) return;
      const newTr: WorkflowTransition = {
        condition: "",
        next_step_id: "",
        is_forced: false,
      };
      handleUpdateStep(stepId, {
        transitions: [...step.transitions, newTr],
      });
    },
    [steps, handleUpdateStep]
  );

  const handleUpdateTransition = useCallback(
    (stepId: string, trIdx: number, patch: Partial<WorkflowTransition>) => {
      const step = steps.find((s) => s.id === stepId);
      if (!step) return;
      const newTransitions = step.transitions.map((t, i) =>
        i === trIdx ? { ...t, ...patch } : t
      );
      handleUpdateStep(stepId, { transitions: newTransitions });
    },
    [steps, handleUpdateStep]
  );

  const handleRemoveTransition = useCallback(
    (stepId: string, trIdx: number) => {
      const step = steps.find((s) => s.id === stepId);
      if (!step) return;
      handleUpdateStep(stepId, {
        transitions: step.transitions.filter((_, i) => i !== trIdx),
      });
    },
    [steps, handleUpdateStep]
  );

  return (
    <div className="space-y-6">
      <div>
        <h3 className="text-lg font-semibold text-gray-900 mb-1">Сценарный Workflow</h3>
        <p className="text-sm text-gray-500 mb-4">
          Настройте многошаговый сценарий диалога. Агент будет вести пользователя по шагам, собирать информацию и переходить к следующему этапу по заданным условиям.
        </p>

        {/* Master toggle */}
        <div className="flex items-center justify-between p-4 border border-gray-200 rounded-lg bg-gray-50">
          <div>
            <p className="font-medium text-gray-900">Включить workflow</p>
            <p className="text-sm text-gray-500">Если выключено — агент работает как обычный чат без шагов</p>
          </div>
          <Toggle checked={workflowEnabled} onChange={toggleWorkflow} />
        </div>
      </div>

      {workflowEnabled && (
        <div className="space-y-4">
          {/* Steps list */}
          {steps.map((step, stepIdx) => (
            <div
              key={step.id}
              className="border border-gray-200 rounded-lg overflow-hidden"
            >
              {/* Step header */}
              <div className="flex items-center justify-between px-4 py-3 bg-gray-50">
                <button
                  type="button"
                  className="flex items-center gap-2 flex-1 text-left"
                  onClick={() =>
                    setExpandedStep(expandedStep === step.id ? null : step.id)
                  }
                >
                  <span className="text-xs font-medium text-gray-400 w-6">
                    #{stepIdx + 1}
                  </span>
                  <span className="font-medium text-gray-900 truncate">
                    {step.name || <span className="text-gray-400 italic">Без названия</span>}
                  </span>
                  {step.required && (
                    <span className="text-xs bg-amber-100 text-amber-700 px-2 py-0.5 rounded-full">
                      обязательный
                    </span>
                  )}
                  {step.timer_trigger && (
                    <Clock size={14} className="text-blue-500 ml-1 flex-shrink-0" />
                  )}
                  {expandedStep === step.id ? (
                    <ChevronUp size={16} className="ml-auto text-gray-400" />
                  ) : (
                    <ChevronDown size={16} className="ml-auto text-gray-400" />
                  )}
                </button>
                <button
                  type="button"
                  className="ml-3 text-gray-400 hover:text-red-500 flex-shrink-0"
                  onClick={() => handleRemoveStep(step.id)}
                  title="Удалить шаг"
                >
                  <X size={16} />
                </button>
              </div>

              {/* Step body */}
              {expandedStep === step.id && (
                <div className="px-4 py-4 space-y-4">
                  <Input
                    label="Название шага"
                    value={step.name}
                    onChange={(e) =>
                      handleUpdateStep(step.id, { name: e.target.value })
                    }
                    placeholder="Например: Приветствие, Сбор данных, Финал"
                  />

                  <Textarea
                    label="Инструкции для агента на этом шаге"
                    value={step.instructions}
                    onChange={(e) =>
                      handleUpdateStep(step.id, {
                        instructions: e.target.value,
                      })
                    }
                    rows={4}
                    placeholder="Что агент должен делать, спрашивать или сообщать пользователю на этом шаге"
                  />

                  <div className="flex items-center gap-3">
                    <Toggle
                      checked={step.required}
                      onChange={() =>
                        handleUpdateStep(step.id, { required: !step.required })
                      }
                    />
                    <span className="text-sm text-gray-700">
                      Обязательный шаг (нельзя пропустить)
                    </span>
                  </div>

                  {/* Transitions */}
                  <div>
                    <p className="text-sm font-medium text-gray-700 mb-2">
                      Переходы к следующим шагам
                    </p>
                    {step.transitions.length === 0 && (
                      <p className="text-xs text-gray-400 mb-2">
                        Нет переходов — агент остаётся на этом шаге.
                      </p>
                    )}
                    <div className="space-y-3">
                      {step.transitions.map((tr, trIdx) => (
                        <div
                          key={trIdx}
                          className="border border-gray-100 rounded-md p-3 space-y-2 bg-white"
                        >
                          <div className="flex items-center justify-between">
                            <span className="text-xs font-medium text-gray-500">
                              Переход #{trIdx + 1}
                            </span>
                            <button
                              type="button"
                              className="text-gray-400 hover:text-red-500"
                              onClick={() =>
                                handleRemoveTransition(step.id, trIdx)
                              }
                            >
                              <X size={14} />
                            </button>
                          </div>

                          <Textarea
                            label="Условие"
                            value={tr.condition}
                            onChange={(e) =>
                              handleUpdateTransition(step.id, trIdx, {
                                condition: e.target.value,
                              })
                            }
                            rows={2}
                            placeholder="Например: пользователь указал свой телефон"
                          />

                          <Input
                            label="Следующий шаг (ID)"
                            value={tr.next_step_id}
                            onChange={(e) =>
                              handleUpdateTransition(step.id, trIdx, {
                                next_step_id: e.target.value,
                              })
                            }
                            placeholder={
                              steps[stepIdx + 1]?.id || "step_2"
                            }
                          />

                          <div className="flex items-center gap-3">
                            <Toggle
                              checked={tr.is_forced}
                              onChange={() =>
                                handleUpdateTransition(step.id, trIdx, {
                                  is_forced: !tr.is_forced,
                                })
                              }
                            />
                            <span className="text-sm text-gray-700">
                              Жёсткое условие (пользователь не перейдёт дальше без выполнения)
                            </span>
                          </div>
                        </div>
                      ))}
                    </div>

                    {step.transitions.length < MAX_TRANSITIONS && (
                      <button
                        type="button"
                        className="mt-2 flex items-center gap-1 text-sm text-blue-600 hover:text-blue-800"
                        onClick={() => handleAddTransition(step.id)}
                      >
                        <Plus size={14} />
                        Добавить переход
                      </button>
                    )}
                  </div>

                  {/* Timer trigger */}
                  <div>
                    <div className="flex items-center gap-3 mb-3">
                      <Toggle
                        checked={!!step.timer_trigger}
                        onChange={() =>
                          handleUpdateStep(step.id, {
                            timer_trigger: step.timer_trigger
                              ? undefined
                              : { delay_seconds: 3600, message_template: "" },
                          })
                        }
                      />
                      <span className="text-sm text-gray-700 flex items-center gap-1">
                        <Clock size={14} className="text-blue-500" />
                        Таймер-триггер (автоматическое сообщение)
                      </span>
                    </div>

                    {step.timer_trigger && (
                      <div className="pl-4 space-y-2 border-l-2 border-blue-200">
                        <Input
                          label="Задержка (в секундах)"
                          type="number"
                          value={String(step.timer_trigger.delay_seconds)}
                          onChange={(e) =>
                            handleUpdateStep(step.id, {
                              timer_trigger: {
                                ...step.timer_trigger!,
                                delay_seconds: Number(e.target.value) || 3600,
                              },
                            })
                          }
                          placeholder="3600"
                        />
                        <Textarea
                          label="Текст сообщения"
                          value={step.timer_trigger.message_template}
                          onChange={(e) =>
                            handleUpdateStep(step.id, {
                              timer_trigger: {
                                ...step.timer_trigger!,
                                message_template: e.target.value,
                              },
                            })
                          }
                          rows={2}
                          placeholder="Привет! Смогли ли вы решить свой вопрос?"
                        />
                      </div>
                    )}
                  </div>
                </div>
              )}
            </div>
          ))}

          {steps.length < MAX_STEPS && (
            <Button
              variant="secondary"
              onClick={handleAddStep}
              className="w-full flex items-center justify-center gap-2"
              type="button"
            >
              <Plus size={16} />
              Добавить шаг
            </Button>
          )}

          {steps.length === 0 && (
            <p className="text-center text-sm text-gray-400 py-4">
              Нажмите «Добавить шаг», чтобы начать создание сценария
            </p>
          )}
        </div>
      )}
    </div>
  );
};
