/** Template editor: welcome message + ordered list of fields with quick-replies. */

"use client";

import React, { useState } from "react";
import { Trash2, Plus, ArrowUp, ArrowDown, X } from "lucide-react";
import { Input } from "@/components/shared/Input";
import { Textarea } from "@/components/shared/Textarea";
import { Button } from "@/components/shared/Button";
import { Toggle } from "@/components/shared/Toggle";
import type { QuestionnaireField, QuestionnaireTemplate } from "@/lib/types/questionnaire";

interface Props {
  template: QuestionnaireTemplate;
  onSave: (welcome_message: string, fields: QuestionnaireField[]) => Promise<void>;
  isSaving: boolean;
}

const FIELD_KEY_RE = /^[a-z][a-z0-9_]{0,29}$/;

function defaultField(order: number): QuestionnaireField {
  return {
    key: `field_${order + 1}`,
    label: `Поле ${order + 1}`,
    question: "",
    required: false,
    quick_replies: [],
    order,
  };
}

export const QuestionnaireEditor: React.FC<Props> = ({ template, onSave, isSaving }) => {
  const [welcome, setWelcome] = useState<string>(template.welcome_message || "");
  const [fields, setFields] = useState<QuestionnaireField[]>(template.fields);
  const [errors, setErrors] = useState<Record<string, string>>({});

  const addField = () => {
    if (fields.length >= 20) return;
    setFields([...fields, defaultField(fields.length)]);
  };

  const removeField = (idx: number) => {
    const next = [...fields];
    next.splice(idx, 1);
    setFields(next.map((f, i) => ({ ...f, order: i })));
  };

  const move = (idx: number, delta: number) => {
    const target = idx + delta;
    if (target < 0 || target >= fields.length) return;
    const next = [...fields];
    [next[idx], next[target]] = [next[target], next[idx]];
    setFields(next.map((f, i) => ({ ...f, order: i })));
  };

  const patch = (idx: number, changes: Partial<QuestionnaireField>) => {
    const next = [...fields];
    next[idx] = { ...next[idx], ...changes };
    setFields(next);
  };

  const validate = (): boolean => {
    const errs: Record<string, string> = {};
    const seen = new Set<string>();
    fields.forEach((f, i) => {
      if (!FIELD_KEY_RE.test(f.key)) {
        errs[`key:${i}`] = "Ключ: латинские буквы, цифры, _; начинается с буквы; до 30 символов";
      } else if (seen.has(f.key)) {
        errs[`key:${i}`] = "Ключ должен быть уникальным";
      }
      seen.add(f.key);
      if (!f.label.trim()) errs[`label:${i}`] = "Название обязательно";
      if (!f.question.trim()) errs[`question:${i}`] = "Вопрос не может быть пустым";
      if (f.quick_replies.length > 8) errs[`qr:${i}`] = "Не более 8 быстрых ответов";
    });
    setErrors(errs);
    return Object.keys(errs).length === 0;
  };

  const handleSave = async () => {
    if (!validate()) return;
    await onSave(welcome.trim(), fields);
  };

  return (
    <div className="space-y-6">
      <section className="bg-white border border-[#BEBAB7] rounded-sm p-4">
        <h2 className="text-lg font-semibold text-gray-900 mb-2">Приветствие</h2>
        <p className="text-sm text-gray-600 mb-3">
          Это сообщение бот пришлёт при старте анкеты. Используйте понятный и короткий текст.
        </p>
        <Textarea
          value={welcome}
          onChange={(e) => setWelcome(e.target.value)}
          placeholder="Привет! Давайте познакомимся — ответьте на несколько коротких вопросов."
          rows={3}
          maxLength={2000}
        />
      </section>

      <section className="bg-white border border-[#BEBAB7] rounded-sm p-4">
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-lg font-semibold text-gray-900">Поля анкеты</h2>
          <Button variant="secondary" size="sm" onClick={addField} disabled={fields.length >= 20} icon={<Plus />}>
            Добавить поле
          </Button>
        </div>
        {fields.length === 0 && (
          <div className="text-sm text-gray-500 border border-dashed border-[#BEBAB7] rounded-sm p-4 text-center">
            Пока нет ни одного поля. Нажмите «Добавить поле», чтобы создать первый вопрос.
          </div>
        )}
        <div className="space-y-4">
          {fields.map((f, idx) => (
            <FieldCard
              key={idx}
              field={f}
              index={idx}
              total={fields.length}
              errors={errors}
              onPatch={(changes) => patch(idx, changes)}
              onRemove={() => removeField(idx)}
              onMove={(delta) => move(idx, delta)}
            />
          ))}
        </div>
      </section>

      <div className="flex justify-end">
        <Button variant="primary" onClick={handleSave} isLoading={isSaving}>
          Сохранить анкету
        </Button>
      </div>
    </div>
  );
};

interface FieldCardProps {
  field: QuestionnaireField;
  index: number;
  total: number;
  errors: Record<string, string>;
  onPatch: (changes: Partial<QuestionnaireField>) => void;
  onRemove: () => void;
  onMove: (delta: number) => void;
}

const FieldCard: React.FC<FieldCardProps> = ({
  field,
  index,
  total,
  errors,
  onPatch,
  onRemove,
  onMove,
}) => {
  const [newQr, setNewQr] = useState<string>("");

  const addQuickReply = () => {
    const v = newQr.trim();
    if (!v) return;
    if (field.quick_replies.length >= 8) return;
    onPatch({ quick_replies: [...field.quick_replies, v] });
    setNewQr("");
  };

  const removeQuickReply = (i: number) => {
    const next = [...field.quick_replies];
    next.splice(i, 1);
    onPatch({ quick_replies: next });
  };

  return (
    <div className="border border-[#BEBAB7] rounded-sm p-3 bg-[#FAFAF8]">
      <div className="flex items-start justify-between gap-3 mb-3">
        <div className="text-sm text-gray-500">Поле #{index + 1}</div>
        <div className="flex items-center gap-1">
          <button
            onClick={() => onMove(-1)}
            disabled={index === 0}
            className="p-1 rounded-sm hover:bg-[#EEEAE7] disabled:opacity-30"
            aria-label="Вверх"
          >
            <ArrowUp size={16} />
          </button>
          <button
            onClick={() => onMove(1)}
            disabled={index === total - 1}
            className="p-1 rounded-sm hover:bg-[#EEEAE7] disabled:opacity-30"
            aria-label="Вниз"
          >
            <ArrowDown size={16} />
          </button>
          <button
            onClick={onRemove}
            className="p-1 rounded-sm text-red-600 hover:bg-red-50"
            aria-label="Удалить"
          >
            <Trash2 size={16} />
          </button>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mb-3">
        <Input
          label="Название (видит только админ)"
          value={field.label}
          onChange={(e) => onPatch({ label: e.target.value })}
          error={errors[`label:${index}`]}
          maxLength={80}
        />
        <Input
          label="Ключ (латиница, уникальный)"
          value={field.key}
          onChange={(e) => onPatch({ key: e.target.value.trim().toLowerCase() })}
          error={errors[`key:${index}`]}
          maxLength={30}
          helperText="Используется как имя поля во всех ответах. Менять ключ у существующего поля нельзя."
        />
      </div>

      <Textarea
        label="Вопрос пользователю (показывается в чате)"
        value={field.question}
        onChange={(e) => onPatch({ question: e.target.value })}
        rows={2}
        maxLength={500}
        error={errors[`question:${index}`]}
      />

      <div className="flex items-center justify-between mt-3">
        <span className="text-sm text-gray-700">Обязательное поле</span>
        <Toggle checked={field.required} onChange={(v) => onPatch({ required: v })} />
      </div>

      <div className="mt-3">
        <div className="text-sm font-medium text-gray-700 mb-1">Быстрые ответы (кнопки)</div>
        <p className="text-xs text-gray-500 mb-2">
          Показываются как inline-кнопки рядом с вопросом. До 8 штук. Если оставить пусто — пользователь отвечает
          свободным текстом.
        </p>
        <div className="flex flex-wrap gap-2 mb-2">
          {field.quick_replies.map((qr, i) => (
            <span
              key={i}
              className="inline-flex items-center gap-1 px-2 py-1 rounded-sm bg-[#EEEAE7] text-sm text-[#443C3C] border border-[#BEBAB7]"
            >
              {qr}
              <button
                onClick={() => removeQuickReply(i)}
                className="hover:text-red-600"
                aria-label="Удалить вариант"
              >
                <X size={14} />
              </button>
            </span>
          ))}
        </div>
        {field.quick_replies.length < 8 && (
          <div className="flex items-center gap-2">
            <Input
              value={newQr}
              onChange={(e) => setNewQr(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  e.preventDefault();
                  addQuickReply();
                }
              }}
              placeholder="Например: Да"
              maxLength={40}
            />
            <Button variant="secondary" size="sm" onClick={addQuickReply}>
              Добавить
            </Button>
          </div>
        )}
        {errors[`qr:${index}`] && (
          <p className="text-sm text-red-600 mt-1">{errors[`qr:${index}`]}</p>
        )}
      </div>
    </div>
  );
};
