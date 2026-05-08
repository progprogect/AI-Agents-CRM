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
            «При входе» — задержка от события источника. Источник — шаг на канвасе, от которого
            ведётся стрелка к этому авто: для обычного шага это переход на него; для цепочки
            auto→auto укажите в связи id предыдущего авто-шага (поле source_id).
            «При выходе» — только для связи от обычного шага workflow (не от авто); отсчёт от
            ухода с этого шага на другой.
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

        {/* Once per conversation */}
        <Section title="Частота">
          <label className="flex cursor-pointer items-start gap-2 rounded-lg border border-[#BEBAB7] bg-white p-3 text-sm text-[#443C3C] hover:border-[#7C3AED]">
            <input
              type="checkbox"
              className="mt-0.5 h-4 w-4 shrink-0 accent-[#7C3AED]"
              checked={autoStep.once_per_conversation === true}
              onChange={(e) =>
                onUpdate({ once_per_conversation: e.target.checked })
              }
            />
            <span>
              <span className="font-medium">Один раз за диалог (до рестарта чата)</span>
              <span className="mt-1 block text-[11px] text-[#9A9590]">
                После успешной отправки сообщения этот авто-шаг не будет ставиться в очередь снова в том же
                диалоге. Новый диалог после /restart — снова можно один раз.
              </span>
            </span>
          </label>
        </Section>

        {/* Telegram media (auto-step) */}
        <Section title="Медиа в Telegram (необязательно)">
          <p className="mb-3 text-[11px] leading-relaxed text-[#9A9590]">
            Работает только для диалогов в Telegram. В других каналах вложение не отправляется; если нужен
            только текст — оставьте тип «Только текст». Текст из блока ниже («Фиксированный текст» или «Ответ
            агента») <strong className="text-[#443C3C]">не заменяется</strong> медиа: к видео он идёт как
            подпись к одному сообщению; к кружочку — отдельным сообщением сразу после кружка (у кружков в
            Telegram нет подписи). Текст можно оставить пустым, если нужны только ролик или кружок.
          </p>
          <div className="flex flex-col gap-2">
            {(
              [
                ["none", "Только текст"],
                ["video_url", "Видео по ссылке"],
                ["video_note", "Видеокружок (file_id)"],
              ] as const
            ).map(([val, label]) => (
              <label
                key={val}
                className="flex cursor-pointer items-start gap-2 rounded-lg border border-[#BEBAB7] bg-white p-2.5 text-sm text-[#443C3C] hover:border-[#7C3AED]"
              >
                <input
                  type="radio"
                  name={`tg-attach-${autoStep.id}`}
                  className="mt-1 accent-[#7C3AED]"
                  checked={(autoStep.telegram_attachment_type ?? "none") === val}
                  onChange={() =>
                    onUpdate({
                      telegram_attachment_type: val,
                      telegram_video_url: val === "video_url" ? autoStep.telegram_video_url : null,
                      telegram_video_note_file_id:
                        val === "video_note" ? autoStep.telegram_video_note_file_id : null,
                    })
                  }
                />
                <span>{label}</span>
              </label>
            ))}
          </div>

          {(autoStep.telegram_attachment_type ?? "none") === "video_url" && (
            <div className="mt-3">
              <Input
                value={autoStep.telegram_video_url ?? ""}
                onChange={(e) => onUpdate({ telegram_video_url: e.target.value })}
                placeholder="https://… (прямая ссылка на mp4, доступная для серверов Telegram)"
              />
              <p className="mt-2 text-[11px] leading-relaxed text-[#9A9590]">
                Используется sendVideo: текст авто-шага уходит как подпись (caption) к этому же сообщению.
                Нужен публичный HTTPS URL; размер и формат — в рамках лимитов Telegram.
              </p>
            </div>
          )}

          {(autoStep.telegram_attachment_type ?? "none") === "video_note" && (
            <div className="mt-3 space-y-2 rounded-lg border border-[#EDE9FE] bg-[#FAF5FF] p-3 text-[11px] leading-relaxed text-[#443C3C]">
              <p className="font-medium text-[#5B21B6]">Как получить file_id для кружочка</p>
              <ol className="list-decimal space-y-1.5 pl-4">
                <li>
                  Откройте чат с <strong>тем же ботом</strong>, который обслуживает этого агента (токен из
                  привязки канала).
                </li>
                <li>
                  Отправьте боту видеокружок <strong>или</strong> квадратное видео (до ~60 сек) — так вы
                  загрузите файл на серверы Telegram.
                </li>
                <li>
                  Получите обновление с этим сообщением: через @RawDataBot / @getidsbot, свой webhook с
                  логированием, или временный эндпоинт <code className="rounded bg-white px-1">getUpdates</code>.
                </li>
                <li>
                  Скопируйте значение <code className="rounded bg-white px-1">message.video_note.file_id</code>{" "}
                  (длинная строка вроде{" "}
                  <span className="text-[#9A9590]">AwACAgIAAxkB…</span>) и вставьте ниже.
                </li>
              </ol>
              <p className="text-[#9A9590]">
                У обычного видео в чате другой file_id — для кружка нужен именно video_note. При смене токена
                бота старые file_id могут перестать работать — загрузите кружок снова. Если задан текст
                авто-шага, он отправится <strong className="text-[#443C3C]">вторым сообщением</strong> сразу
                после кружка (подпись к video note в API нет).
              </p>
              <Input
                className="mt-2"
                value={autoStep.telegram_video_note_file_id ?? ""}
                onChange={(e) => onUpdate({ telegram_video_note_file_id: e.target.value })}
                placeholder="file_id из message.video_note.file_id"
              />
            </div>
          )}
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
