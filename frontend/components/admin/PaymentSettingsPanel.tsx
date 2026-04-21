/** Payment settings section for a Telegram channel binding. */

"use client";

import { useCallback, useEffect, useState } from "react";
import { CreditCard, Eye, EyeOff, FlaskConical, Mic, Plus, Image, Trash2, X } from "lucide-react";
import { api, ApiError } from "@/lib/api";
import type {
  CreatePlanRequest,
  FeatureGates,
  PaymentPlan,
  PaymentSettings,
  PaywallMessages,
  UpsertPaymentSettingsRequest,
} from "@/lib/types/payment";
import type { ChannelBinding } from "@/lib/types/channel";
import { Toggle } from "@/components/shared/Toggle";
import { Input } from "@/components/shared/Input";
import { Textarea } from "@/components/shared/Textarea";

interface Props {
  binding: ChannelBinding;
}

const CURRENCIES = ["RUB", "USD", "EUR", "XTR"];

// ── Plan form modal ────────────────────────────────────────────────────────────

const CURRENCY_SYMBOLS: Record<string, string> = {
  RUB: "₽", USD: "$", EUR: "€", XTR: "⭐",
};

function formatPrice(amount: number, currency: string): string {
  if (currency === "XTR") return `${amount} Stars`;
  const sym = CURRENCY_SYMBOLS[currency] ?? currency;
  return `${(amount / 100).toFixed(2).replace(/\.00$/, "")} ${sym}`;
}

function PlanModal({
  bindingId,
  plan,
  onSave,
  onClose,
}: {
  bindingId: string;
  plan?: PaymentPlan;
  onSave: (p: PaymentPlan) => void;
  onClose: () => void;
}) {
  const [form, setForm] = useState<CreatePlanRequest>({
    name: plan?.name ?? "",
    duration_days: plan?.duration_days ?? 30,
    price_amount: plan?.price_amount ?? 29900,
    currency: plan?.currency ?? "RUB",
    messages_limit: plan?.messages_limit ?? null,
    sort_order: plan?.sort_order ?? 0,
  });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSave = async () => {
    setSaving(true);
    setError(null);
    try {
      let saved: PaymentPlan;
      if (plan) {
        saved = await api.updatePaymentPlan(bindingId, plan.plan_id, form);
      } else {
        saved = await api.createPaymentPlan(bindingId, form);
      }
      onSave(saved);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Ошибка сохранения");
    } finally {
      setSaving(false);
    }
  };

  const priceHint = form.price_amount > 0 ? formatPrice(form.price_amount, form.currency) : null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
      <div className="bg-white rounded-lg shadow-xl w-full max-w-md mx-4 p-6">
        <div className="flex items-center justify-between mb-4">
          <h3 className="font-semibold text-[#251D1C]">
            {plan ? "Редактировать план" : "Новый план"}
          </h3>
          <button type="button" onClick={onClose} className="text-[#9A9590] hover:text-[#251D1C]">
            <X size={18} />
          </button>
        </div>

        <div className="space-y-3">
          <Input
            label="Название плана"
            value={form.name}
            onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
            placeholder="Например: 1 месяц"
          />

          <div className="grid grid-cols-2 gap-3">
            <Input
              label="Срок действия (дней)"
              type="number"
              value={String(form.duration_days)}
              onChange={(e) => setForm((f) => ({ ...f, duration_days: Number(e.target.value) || 30 }))}
              placeholder="30"
            />
            <div>
              <label className="text-xs font-medium text-[#443C3C] mb-1 block">Валюта</label>
              <select
                value={form.currency}
                onChange={(e) => setForm((f) => ({ ...f, currency: e.target.value }))}
                className="w-full border border-[#BEBAB7] rounded px-3 py-2 text-sm text-[#251D1C] focus:outline-none focus:border-[#251D1C]"
              >
                {CURRENCIES.map((c) => <option key={c}>{c}</option>)}
              </select>
            </div>
          </div>

          {/* Price field with live preview */}
          <div>
            <div className="flex items-baseline justify-between mb-1">
              <label className="text-xs font-medium text-[#443C3C]">
                Цена
                {form.currency !== "XTR" && (
                  <span className="ml-1 font-normal text-[#9A9590]">
                    (в копейках/центах, т.е. × 100)
                  </span>
                )}
              </label>
              {priceHint && (
                <span className="text-xs font-semibold text-green-700 bg-green-50 px-2 py-0.5 rounded">
                  = {priceHint}
                </span>
              )}
            </div>
            <input
              type="number"
              min={0}
              value={String(form.price_amount)}
              onChange={(e) => setForm((f) => ({ ...f, price_amount: Number(e.target.value) || 0 }))}
              placeholder={form.currency === "XTR" ? "50" : "29900"}
              className="w-full border border-[#BEBAB7] rounded px-3 py-2 text-sm focus:outline-none focus:border-[#251D1C]"
            />
            {form.currency !== "XTR" && (
              <p className="mt-1 text-xs text-[#9A9590]">
                Пример: 29900 = 299 ₽ · 99900 = 999 ₽
              </p>
            )}
          </div>

          <div>
            <label className="text-xs font-medium text-[#443C3C] mb-1 block">
              Лимит сообщений{" "}
              <span className="font-normal text-[#9A9590]">(оставьте пустым — безлимит)</span>
            </label>
            <input
              type="number"
              min={1}
              value={form.messages_limit != null ? String(form.messages_limit) : ""}
              onChange={(e) =>
                setForm((f) => ({
                  ...f,
                  messages_limit: e.target.value ? Number(e.target.value) : null,
                }))
              }
              placeholder="Безлимит"
              className="w-full border border-[#BEBAB7] rounded px-3 py-2 text-sm focus:outline-none focus:border-[#251D1C]"
            />
          </div>
        </div>

        {error && <p className="mt-3 text-xs text-red-600">{error}</p>}

        <div className="mt-5 flex justify-end gap-2">
          <button
            type="button"
            onClick={onClose}
            className="px-4 py-2 text-sm text-[#443C3C] border border-[#BEBAB7] rounded hover:bg-[#EEEAE7] transition-colors"
          >
            Отмена
          </button>
          <button
            type="button"
            onClick={handleSave}
            disabled={saving || !form.name}
            className="px-4 py-2 text-sm font-medium bg-[#251D1C] text-white rounded hover:bg-[#443C3C] disabled:opacity-50 transition-colors"
          >
            {saving ? "Сохраняем…" : "Сохранить"}
          </button>
        </div>
      </div>
    </div>
  );
}

// ── Main panel ─────────────────────────────────────────────────────────────────

const DEFAULT_FEATURE_GATES: FeatureGates = { voice: false, images: false };
const DEFAULT_PAYWALL_MESSAGES: PaywallMessages = {
  voice: "Голосовые сообщения доступны по подписке.",
  images: "Анализ изображений доступен по подписке.",
  limit_reached: "Вы исчерпали лимит бесплатных сообщений. Выберите план подписки.",
};

export function PaymentSettingsPanel({ binding }: Props) {
  const [settings, setSettings] = useState<PaymentSettings | null>(null);
  const [plans, setPlans] = useState<PaymentPlan[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [simulating, setSimulating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);
  const [liveToken, setLiveToken] = useState("");
  const [sandboxToken, setSandboxToken] = useState("");
  const [showLive, setShowLive] = useState(false);
  const [showSandbox, setShowSandbox] = useState(false);
  const [planModal, setPlanModal] = useState<{ open: boolean; plan?: PaymentPlan }>({
    open: false,
  });
  const [simUserId, setSimUserId] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [s, p] = await Promise.all([
        api.getPaymentSettings(binding.binding_id),
        api.listPaymentPlans(binding.binding_id, false),
      ]);
      setSettings(s);
      setPlans(p);
    } catch {
      setError("Не удалось загрузить настройки оплаты");
    } finally {
      setLoading(false);
    }
  }, [binding.binding_id]);

  useEffect(() => {
    void load();
  }, [load]);

  const handleSaveSettings = async () => {
    if (!settings) return;
    setSaving(true);
    setError(null);
    setSuccessMsg(null);
    try {
      const req: UpsertPaymentSettingsRequest = {
        enabled: settings.enabled,
        provider: settings.provider,
        free_messages: settings.free_messages,
        grace_messages: settings.grace_messages,
        sandbox_mode: settings.sandbox_mode,
        payment_title: settings.payment_title,
        payment_description: settings.payment_description,
        invoice_resend_hours: settings.invoice_resend_hours,
        support_contact: settings.support_contact ?? undefined,
        feature_gates: settings.feature_gates,
        paywall_messages: settings.paywall_messages,
        free_message_limit_enabled: settings.free_message_limit_enabled,
      };
      const saved = await api.upsertPaymentSettings(binding.binding_id, req);
      setSettings(saved);

      if (liveToken || sandboxToken) {
        await api.setPaymentToken(
          binding.binding_id,
          liveToken || undefined,
          sandboxToken || undefined
        );
        setLiveToken("");
        setSandboxToken("");
      }
      setSuccessMsg("Настройки сохранены");
      setTimeout(() => setSuccessMsg(null), 3000);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Ошибка сохранения");
    } finally {
      setSaving(false);
    }
  };

  const handleSimulateSandbox = async () => {
    if (!simUserId.trim() || plans.length === 0) return;
    setSimulating(true);
    setError(null);
    setSuccessMsg(null);
    try {
      const result = await api.simulateSandboxPayment(binding.binding_id, {
        external_user_id: simUserId.trim(),
        plan_id: plans[0].plan_id,
      });
      const expiresAt = result.sub.expires_at
        ? new Date(result.sub.expires_at).toLocaleDateString("ru-RU")
        : "бессрочно";
      setSuccessMsg(`✅ Подписка активирована до ${expiresAt} для пользователя ${simUserId.trim()}`);
      setSimUserId("");
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Ошибка симуляции");
    } finally {
      setSimulating(false);
    }
  };

  const handleDeletePlan = async (planId: string) => {
    if (!confirm("Удалить план?")) return;
    try {
      await api.deletePaymentPlan(binding.binding_id, planId);
      setPlans((prev) => prev.filter((p) => p.plan_id !== planId));
    } catch {
      setError("Не удалось удалить план");
    }
  };

  if (loading) {
    return (
      <div className="px-4 py-3 bg-[#FAFAFA] border-t border-[#BEBAB7] text-sm text-[#9A9590]">
        Загрузка настроек оплаты…
      </div>
    );
  }

  const s = settings ?? {
    binding_id: binding.binding_id,
    enabled: false,
    provider: "telegram_native" as const,
    free_messages: 10,
    grace_messages: 3,
    sandbox_mode: false,
    has_live_token: false,
    has_sandbox_token: false,
    payment_title: "Подписка",
    payment_description: "Доступ к чат-боту",
    invoice_resend_hours: 24,
    feature_gates: DEFAULT_FEATURE_GATES,
    paywall_messages: DEFAULT_PAYWALL_MESSAGES,
    free_message_limit_enabled: false,
  };

  const set = (patch: Partial<typeof s>) =>
    setSettings((prev) => (prev ? { ...prev, ...patch } : { ...s, ...patch }));

  return (
    <div className="px-4 py-4 bg-[#FAFAFA] border-t border-[#BEBAB7] rounded-b-md space-y-5">
      {/* Header */}
      <div className="flex items-center gap-2">
        <CreditCard size={15} className="text-[#443C3C]" />
        <p className="text-xs font-semibold uppercase tracking-wider text-[#9A9590]">
          Монетизация
        </p>
      </div>

      {/* Enable toggle */}
      <div className="flex items-center justify-between">
        <div>
          <p className="text-sm font-medium text-[#251D1C]">Включить оплату</p>
          <p className="text-xs text-[#9A9590]">Пользователи получат лимит бесплатных сообщений</p>
        </div>
        <Toggle checked={s.enabled} onChange={() => set({ enabled: !s.enabled })} />
      </div>

      {s.enabled && (
        <>
          {/* Provider */}
          <div>
            <label className="text-xs font-medium text-[#443C3C] mb-1 block">Провайдер</label>
            <select
              value={s.provider}
              onChange={(e) => set({ provider: e.target.value as "telegram_native" | "external_link" })}
              className="w-full border border-[#BEBAB7] rounded px-3 py-2 text-sm text-[#251D1C] focus:outline-none focus:border-[#251D1C]"
            >
              <option value="telegram_native">Telegram Native (YooKassa / Stars)</option>
              <option value="external_link">Внешняя ссылка (Stripe / другое)</option>
            </select>
          </div>

          {/* Tokens */}
          <div className="space-y-2">
            <p className="text-xs font-medium text-[#443C3C]">
              Токен провайдера{" "}
              {s.has_live_token && (
                <span className="text-green-600">(установлен)</span>
              )}
            </p>
            <div className="flex gap-2">
              <div className="relative flex-1">
                <input
                  type={showLive ? "text" : "password"}
                  value={liveToken}
                  onChange={(e) => setLiveToken(e.target.value)}
                  placeholder={s.has_live_token ? "••• оставьте пустым чтобы не менять •••" : "Вставьте токен от BotFather"}
                  className="w-full border border-[#BEBAB7] rounded px-3 py-2 text-sm pr-8 focus:outline-none focus:border-[#251D1C]"
                />
                <button
                  type="button"
                  onClick={() => setShowLive((v) => !v)}
                  className="absolute right-2 top-1/2 -translate-y-1/2 text-[#9A9590] hover:text-[#443C3C]"
                >
                  {showLive ? <EyeOff size={14} /> : <Eye size={14} />}
                </button>
              </div>
            </div>

            <p className="text-xs font-medium text-[#443C3C]">
              Тестовый токен{" "}
              {s.has_sandbox_token && (
                <span className="text-green-600">(установлен)</span>
              )}
            </p>
            <div className="relative">
              <input
                type={showSandbox ? "text" : "password"}
                value={sandboxToken}
                onChange={(e) => setSandboxToken(e.target.value)}
                placeholder={s.has_sandbox_token ? "••• оставьте пустым чтобы не менять •••" : "Токен TEST от BotFather"}
                className="w-full border border-[#BEBAB7] rounded px-3 py-2 text-sm pr-8 focus:outline-none focus:border-[#251D1C]"
              />
              <button
                type="button"
                onClick={() => setShowSandbox((v) => !v)}
                className="absolute right-2 top-1/2 -translate-y-1/2 text-[#9A9590] hover:text-[#443C3C]"
              >
                {showSandbox ? <EyeOff size={14} /> : <Eye size={14} />}
              </button>
            </div>
          </div>

          {/* Invoice text */}
          <div className="space-y-2">
            <Input
              label="Заголовок инвойса"
              value={s.payment_title}
              onChange={(e) => set({ payment_title: e.target.value })}
              placeholder="Подписка"
            />
            <Textarea
              label="Описание"
              value={s.payment_description}
              onChange={(e) => set({ payment_description: e.target.value })}
              rows={2}
              placeholder="Доступ к чат-боту"
            />
            <Input
              label="Контакт поддержки по оплате"
              value={s.support_contact ?? ""}
              onChange={(e) => set({ support_contact: e.target.value })}
              placeholder="@support или email"
            />
          </div>

          {/* ── Paid features ────────────────────────────────────────── */}
          <div className="border-t border-[#EEEAE7] pt-4 space-y-3">
            <p className="text-xs font-semibold uppercase tracking-wider text-[#9A9590]">
              Платные функции
            </p>

            {/* Voice */}
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <Mic size={14} className="text-[#443C3C]" />
                  <span className="text-sm text-[#443C3C]">Голосовые сообщения — платно</span>
                </div>
                <Toggle
                  checked={s.feature_gates?.voice ?? false}
                  onChange={() =>
                    set({
                      feature_gates: {
                        ...(s.feature_gates ?? DEFAULT_FEATURE_GATES),
                        voice: !(s.feature_gates?.voice ?? false),
                      },
                    })
                  }
                />
              </div>
              {s.feature_gates?.voice && (
                <Textarea
                  label="Сообщение при блокировке (голос)"
                  value={s.paywall_messages?.voice ?? DEFAULT_PAYWALL_MESSAGES.voice}
                  onChange={(e) =>
                    set({
                      paywall_messages: {
                        ...(s.paywall_messages ?? DEFAULT_PAYWALL_MESSAGES),
                        voice: e.target.value,
                      },
                    })
                  }
                  rows={2}
                  placeholder="Голосовые сообщения доступны по подписке."
                />
              )}
            </div>

            {/* Images */}
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <Image size={14} className="text-[#443C3C]" />
                  <span className="text-sm text-[#443C3C]">Анализ изображений — платно</span>
                </div>
                <Toggle
                  checked={s.feature_gates?.images ?? false}
                  onChange={() =>
                    set({
                      feature_gates: {
                        ...(s.feature_gates ?? DEFAULT_FEATURE_GATES),
                        images: !(s.feature_gates?.images ?? false),
                      },
                    })
                  }
                />
              </div>
              {s.feature_gates?.images && (
                <Textarea
                  label="Сообщение при блокировке (изображения)"
                  value={s.paywall_messages?.images ?? DEFAULT_PAYWALL_MESSAGES.images}
                  onChange={(e) =>
                    set({
                      paywall_messages: {
                        ...(s.paywall_messages ?? DEFAULT_PAYWALL_MESSAGES),
                        images: e.target.value,
                      },
                    })
                  }
                  rows={2}
                  placeholder="Анализ изображений доступен по подписке."
                />
              )}
            </div>
          </div>

          {/* ── Free message limit ───────────────────────────────────── */}
          <div className="border-t border-[#EEEAE7] pt-4 space-y-3">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm font-medium text-[#251D1C]">Лимит бесплатных сообщений</p>
                <p className="text-xs text-[#9A9590]">
                  Требовать подписку после N бесплатных сообщений
                </p>
              </div>
              <Toggle
                checked={s.free_message_limit_enabled ?? false}
                onChange={() => set({ free_message_limit_enabled: !s.free_message_limit_enabled })}
              />
            </div>
            {s.free_message_limit_enabled && (
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="text-xs font-medium text-[#443C3C] mb-1 block">
                    Бесплатных сообщений
                  </label>
                  <input
                    type="number"
                    value={s.free_messages}
                    min={0}
                    onChange={(e) => set({ free_messages: Number(e.target.value) })}
                    className="w-full border border-[#BEBAB7] rounded px-3 py-2 text-sm focus:outline-none focus:border-[#251D1C]"
                  />
                </div>
                <div>
                  <label className="text-xs font-medium text-[#443C3C] mb-1 block">
                    Grace-сообщений
                  </label>
                  <input
                    type="number"
                    value={s.grace_messages}
                    min={0}
                    onChange={(e) => set({ grace_messages: Number(e.target.value) })}
                    className="w-full border border-[#BEBAB7] rounded px-3 py-2 text-sm focus:outline-none focus:border-[#251D1C]"
                  />
                </div>
              </div>
            )}
            {s.free_message_limit_enabled && (
              <Textarea
                label="Сообщение при достижении лимита"
                value={s.paywall_messages?.limit_reached ?? DEFAULT_PAYWALL_MESSAGES.limit_reached}
                onChange={(e) =>
                  set({
                    paywall_messages: {
                      ...(s.paywall_messages ?? DEFAULT_PAYWALL_MESSAGES),
                      limit_reached: e.target.value,
                    },
                  })
                }
                rows={2}
                placeholder="Вы исчерпали лимит бесплатных сообщений."
              />
            )}
          </div>

          {/* ── Sandbox mode ─────────────────────────────────────────── */}
          <div className="border-t border-[#EEEAE7] pt-4 space-y-3">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <FlaskConical size={14} className="text-[#443C3C]" />
                <span className="text-sm font-medium text-[#251D1C]">Тестовый режим (Sandbox)</span>
              </div>
              <Toggle
                checked={s.sandbox_mode}
                onChange={() => set({ sandbox_mode: !s.sandbox_mode })}
              />
            </div>

            {s.sandbox_mode && (
              <div className="bg-amber-50 border border-amber-200 rounded p-3 space-y-3">
                {!s.has_sandbox_token && !s.has_live_token ? (
                  <>
                    <div className="flex items-center gap-2">
                      <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-amber-100 text-amber-800">
                        🔧 Внутренний тест
                      </span>
                      <span className="text-xs text-amber-700">
                        Токен провайдера не настроен — используется встроенная симуляция
                      </span>
                    </div>
                    <div className="space-y-2">
                      <p className="text-xs font-medium text-[#443C3C]">
                        Симулировать оплату для пользователя
                      </p>
                      <div className="flex gap-2">
                        <input
                          type="text"
                          value={simUserId}
                          onChange={(e) => setSimUserId(e.target.value)}
                          placeholder="Telegram chat_id пользователя"
                          className="flex-1 border border-[#BEBAB7] rounded px-3 py-1.5 text-sm focus:outline-none focus:border-[#251D1C]"
                        />
                        <button
                          type="button"
                          onClick={handleSimulateSandbox}
                          disabled={simulating || !simUserId.trim() || plans.length === 0}
                          className="px-3 py-1.5 text-sm font-medium bg-amber-600 text-white rounded hover:bg-amber-700 disabled:opacity-50 transition-colors whitespace-nowrap"
                        >
                          {simulating ? "Симулируем…" : "Активировать"}
                        </button>
                      </div>
                      {plans.length === 0 && (
                        <p className="text-xs text-amber-600">
                          Добавьте хотя бы один план подписки для симуляции
                        </p>
                      )}
                    </div>
                  </>
                ) : (
                  <div className="flex items-center gap-2">
                    <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-blue-100 text-blue-800">
                      🧪 Тест-провайдер
                    </span>
                    <span className="text-xs text-blue-700">
                      Используется тестовый токен YooKassa
                    </span>
                  </div>
                )}
              </div>
            )}
          </div>

          {/* Plans */}
          <div>
            <div className="flex items-center justify-between mb-2">
              <p className="text-xs font-semibold uppercase tracking-wider text-[#9A9590]">
                Планы подписки
              </p>
              <button
                type="button"
                onClick={() => setPlanModal({ open: true })}
                className="flex items-center gap-1 text-xs text-[#251D1C] hover:text-[#443C3C]"
              >
                <Plus size={12} />
                Добавить
              </button>
            </div>

            {plans.length === 0 ? (
              <p className="text-xs text-[#9A9590]">Нет планов. Добавьте хотя бы один.</p>
            ) : (
              <div className="space-y-2">
                {plans.map((p) => (
                  <div
                    key={p.plan_id}
                    className="flex items-center justify-between bg-white border border-[#BEBAB7] rounded px-3 py-2"
                  >
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-medium text-[#251D1C] truncate">{p.name}</p>
                      <p className="text-xs text-[#9A9590]">
                        {p.duration_days} дн · {(p.price_amount / 100).toFixed(0)} {p.currency}
                        {p.messages_limit ? ` · ${p.messages_limit} сообщ.` : " · безлимит"}
                        {!p.is_active && " · отключён"}
                      </p>
                    </div>
                    <div className="flex items-center gap-2 ml-2">
                      <button
                        type="button"
                        onClick={() => setPlanModal({ open: true, plan: p })}
                        className="text-xs text-[#443C3C] hover:text-[#251D1C]"
                      >
                        Изм.
                      </button>
                      <button
                        type="button"
                        onClick={() => handleDeletePlan(p.plan_id)}
                        className="text-[#9A9590] hover:text-red-500"
                      >
                        <Trash2 size={13} />
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </>
      )}

      {error && <p className="text-xs text-red-600">{error}</p>}
      {successMsg && <p className="text-xs text-green-600">{successMsg}</p>}

      <button
        type="button"
        onClick={handleSaveSettings}
        disabled={saving}
        className="w-full py-2 text-sm font-medium bg-[#251D1C] text-white rounded hover:bg-[#443C3C] disabled:opacity-50 transition-colors"
      >
        {saving ? "Сохраняем…" : "Сохранить настройки"}
      </button>

      {planModal.open && (
        <PlanModal
          bindingId={binding.binding_id}
          plan={planModal.plan}
          onSave={(saved) => {
            setPlans((prev) => {
              const idx = prev.findIndex((p) => p.plan_id === saved.plan_id);
              if (idx >= 0) {
                const next = [...prev];
                next[idx] = saved;
                return next;
              }
              return [...prev, saved];
            });
            setPlanModal({ open: false });
          }}
          onClose={() => setPlanModal({ open: false })}
        />
      )}
    </div>
  );
}
