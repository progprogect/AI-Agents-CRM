/** /admin/subscriptions — view and manage user payment subscriptions. */

"use client";

import { useCallback, useEffect, useState } from "react";
import {
  AlertCircle,
  CheckCircle2,
  ChevronDown,
  CreditCard,
  RefreshCw,
  RotateCcw,
  X,
} from "lucide-react";
import { api, ApiError } from "@/lib/api";
import type { ChannelBinding } from "@/lib/types/channel";
import type {
  PaymentTransaction,
  SubscriptionStatus,
  UpdateSubscriptionRequest,
  UserSubscription,
} from "@/lib/types/payment";
import { Toggle } from "@/components/shared/Toggle";
import { Input } from "@/components/shared/Input";

// ── Helpers ───────────────────────────────────────────────────────────────────

const STATUS_LABELS: Record<SubscriptionStatus, string> = {
  free: "Бесплатный",
  active: "Активен",
  expired: "Истёк",
  manual: "Ручной",
};

const STATUS_COLORS: Record<SubscriptionStatus, string> = {
  free: "bg-gray-100 text-gray-700",
  active: "bg-green-100 text-green-700",
  expired: "bg-red-100 text-red-700",
  manual: "bg-blue-100 text-blue-700",
};

function StatusBadge({ status }: { status: string }) {
  const s = status as SubscriptionStatus;
  return (
    <span
      className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${
        STATUS_COLORS[s] ?? "bg-gray-100 text-gray-600"
      }`}
    >
      {STATUS_LABELS[s] ?? status}
    </span>
  );
}

function formatDate(d: string | null) {
  if (!d) return "—";
  return new Date(d).toLocaleDateString("ru-RU");
}

// ── Override modal ─────────────────────────────────────────────────────────────

function OverrideModal({
  sub,
  bindingId,
  onClose,
  onSaved,
}: {
  sub: UserSubscription;
  bindingId: string;
  onClose: () => void;
  onSaved: (updated: UserSubscription) => void;
}) {
  const [form, setForm] = useState<UpdateSubscriptionRequest>({
    status: sub.status,
    expires_at: sub.expires_at ? sub.expires_at.slice(0, 10) : undefined,
    messages_limit: sub.messages_limit ?? undefined,
    messages_used: sub.messages_used,
    manual_override: sub.manual_override,
    notes: sub.notes ?? "",
  });
  const [saving, setSaving] = useState(false);
  const [resetting, setResetting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [transactions, setTransactions] = useState<PaymentTransaction[]>([]);
  const [tab, setTab] = useState<"settings" | "history">("settings");

  useEffect(() => {
    api.listTransactions(bindingId, 20)
      .then((txns) => setTransactions(txns.filter((t) => t.external_user_id === sub.external_user_id)))
      .catch(() => {});
  }, [bindingId, sub.external_user_id]);

  const handleSave = async () => {
    setSaving(true);
    setError(null);
    try {
      const patch: UpdateSubscriptionRequest = {
        status: form.status,
        manual_override: form.manual_override,
        notes: form.notes,
      };
      if (form.expires_at) {
        patch.expires_at = new Date(form.expires_at as string).toISOString();
      }
      if (form.messages_limit != null) {
        patch.messages_limit = Number(form.messages_limit);
      }
      if (form.messages_used != null) {
        patch.messages_used = Number(form.messages_used);
      }
      const updated = await api.updateSubscription(bindingId, sub.external_user_id, patch);
      onSaved(updated);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Ошибка сохранения");
    } finally {
      setSaving(false);
    }
  };

  const handleReset = async () => {
    if (!confirm("Сбросить счётчик сообщений?")) return;
    setResetting(true);
    try {
      await api.resetSubscriptionCounter(bindingId, sub.external_user_id);
      const updated = await api.updateSubscription(bindingId, sub.external_user_id, {});
      onSaved(updated);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Ошибка сброса");
    } finally {
      setResetting(false);
    }
  };

  const handleRefund = async (txnId: string) => {
    if (!confirm("Оформить возврат?")) return;
    try {
      await api.refundTransaction(txnId);
      setTransactions((prev) =>
        prev.map((t) => (t.txn_id === txnId ? { ...t, status: "refunded" } : t))
      );
    } catch {
      setError("Ошибка возврата");
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <div className="bg-white rounded-lg shadow-xl w-full max-w-lg max-h-[90vh] flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-[#EEEAE7]">
          <div>
            <p className="font-semibold text-[#251D1C]">Управление подпиской</p>
            <p className="text-xs text-[#9A9590] font-mono">{sub.external_user_id}</p>
          </div>
          <button type="button" onClick={onClose} className="text-[#9A9590] hover:text-[#251D1C]">
            <X size={18} />
          </button>
        </div>

        {/* Tabs */}
        <div className="flex border-b border-[#EEEAE7]">
          {(["settings", "history"] as const).map((t) => (
            <button
              key={t}
              type="button"
              onClick={() => setTab(t)}
              className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors ${
                tab === t
                  ? "border-[#251D1C] text-[#251D1C]"
                  : "border-transparent text-[#9A9590] hover:text-[#443C3C]"
              }`}
            >
              {t === "settings" ? "Настройки" : "История"}
            </button>
          ))}
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto px-5 py-4">
          {tab === "settings" ? (
            <div className="space-y-4">
              <div>
                <label className="text-xs font-medium text-[#443C3C] mb-1 block">Статус</label>
                <select
                  value={form.status as string}
                  onChange={(e) => setForm((f) => ({ ...f, status: e.target.value as SubscriptionStatus }))}
                  className="w-full border border-[#BEBAB7] rounded px-3 py-2 text-sm focus:outline-none focus:border-[#251D1C]"
                >
                  {Object.entries(STATUS_LABELS).map(([k, v]) => (
                    <option key={k} value={k}>{v}</option>
                  ))}
                </select>
              </div>

              <Input
                label="Дата истечения"
                type="date"
                value={form.expires_at as string ?? ""}
                onChange={(e) => setForm((f) => ({ ...f, expires_at: e.target.value || undefined }))}
              />

              <div className="grid grid-cols-2 gap-3">
                <Input
                  label="Лимит сообщений"
                  type="number"
                  value={form.messages_limit != null ? String(form.messages_limit) : ""}
                  onChange={(e) => setForm((f) => ({
                    ...f,
                    messages_limit: e.target.value ? Number(e.target.value) : undefined,
                  }))}
                  placeholder="Пусто = безлимит"
                />
                <Input
                  label="Использовано"
                  type="number"
                  value={String(form.messages_used ?? 0)}
                  onChange={(e) => setForm((f) => ({ ...f, messages_used: Number(e.target.value) }))}
                />
              </div>

              <div className="flex items-center gap-3">
                <Toggle
                  checked={!!form.manual_override}
                  onChange={() => setForm((f) => ({ ...f, manual_override: !f.manual_override }))}
                />
                <span className="text-sm text-[#443C3C]">Ручное управление (игнорировать лимиты)</span>
              </div>

              <div>
                <label className="text-xs font-medium text-[#443C3C] mb-1 block">Примечание</label>
                <textarea
                  rows={2}
                  value={form.notes ?? ""}
                  onChange={(e) => setForm((f) => ({ ...f, notes: e.target.value }))}
                  placeholder="Комментарий оператора"
                  className="w-full border border-[#BEBAB7] rounded px-3 py-2 text-sm resize-none focus:outline-none focus:border-[#251D1C]"
                />
              </div>

              <button
                type="button"
                onClick={handleReset}
                disabled={resetting}
                className="flex items-center gap-1.5 text-sm text-[#9A9590] hover:text-[#251D1C] transition-colors"
              >
                <RotateCcw size={13} />
                {resetting ? "Сбрасываем…" : "Сбросить счётчик сообщений"}
              </button>
            </div>
          ) : (
            <div className="space-y-2">
              {transactions.length === 0 ? (
                <p className="text-sm text-[#9A9590]">Нет транзакций</p>
              ) : (
                transactions.map((t) => (
                  <div
                    key={t.txn_id}
                    className="flex items-center justify-between border border-[#EEEAE7] rounded p-3"
                  >
                    <div>
                      <p className="text-sm font-medium text-[#251D1C]">
                        {t.amount != null && t.currency
                          ? `${(t.amount / 100).toFixed(0)} ${t.currency}`
                          : "—"}
                      </p>
                      <p className="text-xs text-[#9A9590]">
                        {t.status} · {formatDate(t.created_at)}
                      </p>
                    </div>
                    {t.status === "completed" && t.provider_charge_id && (
                      <button
                        type="button"
                        onClick={() => handleRefund(t.txn_id)}
                        className="text-xs text-red-500 hover:text-red-700"
                      >
                        Возврат
                      </button>
                    )}
                    {t.status === "refunded" && (
                      <span className="text-xs text-gray-500">Возвращено</span>
                    )}
                  </div>
                ))
              )}
            </div>
          )}
        </div>

        {error && <p className="px-5 pb-2 text-xs text-red-600">{error}</p>}

        {tab === "settings" && (
          <div className="px-5 py-4 border-t border-[#EEEAE7] flex justify-end gap-2">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 text-sm border border-[#BEBAB7] rounded hover:bg-[#EEEAE7] transition-colors"
            >
              Отмена
            </button>
            <button
              type="button"
              onClick={handleSave}
              disabled={saving}
              className="px-4 py-2 text-sm font-medium bg-[#251D1C] text-white rounded hover:bg-[#443C3C] disabled:opacity-50 transition-colors"
            >
              {saving ? "Сохраняем…" : "Сохранить"}
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function SubscriptionsPage() {
  const [bindings, setBindings] = useState<ChannelBinding[]>([]);
  const [selectedBindingId, setSelectedBindingId] = useState<string>("");
  const [statusFilter, setStatusFilter] = useState<string>("");
  const [subscriptions, setSubscriptions] = useState<UserSubscription[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [overrideSub, setOverrideSub] = useState<UserSubscription | null>(null);

  useEffect(() => {
    api.listAgents().then(async (agents) => {
      const all: ChannelBinding[] = [];
      for (const agent of agents) {
        try {
          const bs = await api.listChannelBindings(agent.agent_id, "telegram", false);
          all.push(...bs);
        } catch {}
      }
      setBindings(all);
      if (all.length > 0) setSelectedBindingId(all[0].binding_id);
    }).catch(() => {});
  }, []);

  const loadSubs = useCallback(async () => {
    if (!selectedBindingId) return;
    setLoading(true);
    setError(null);
    try {
      const data = await api.listSubscriptions(
        selectedBindingId,
        statusFilter || undefined,
        100,
        0
      );
      setSubscriptions(data);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Ошибка загрузки");
    } finally {
      setLoading(false);
    }
  }, [selectedBindingId, statusFilter]);

  useEffect(() => {
    void loadSubs();
  }, [loadSubs]);

  return (
    <div className="p-6 max-w-5xl mx-auto">
      {/* Title */}
      <div className="flex items-center gap-3 mb-6">
        <CreditCard size={22} className="text-[#251D1C]" />
        <h1 className="text-xl font-semibold text-[#251D1C]">Подписки</h1>
      </div>

      {/* Filters */}
      <div className="flex flex-wrap gap-3 mb-5">
        <select
          value={selectedBindingId}
          onChange={(e) => setSelectedBindingId(e.target.value)}
          className="border border-[#BEBAB7] rounded px-3 py-2 text-sm focus:outline-none focus:border-[#251D1C]"
        >
          {bindings.map((b) => (
            <option key={b.binding_id} value={b.binding_id}>
              {b.channel_username || b.channel_account_id}
            </option>
          ))}
        </select>

        <select
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value)}
          className="border border-[#BEBAB7] rounded px-3 py-2 text-sm focus:outline-none focus:border-[#251D1C]"
        >
          <option value="">Все статусы</option>
          {Object.entries(STATUS_LABELS).map(([k, v]) => (
            <option key={k} value={k}>{v}</option>
          ))}
        </select>

        <button
          type="button"
          onClick={loadSubs}
          className="flex items-center gap-1.5 px-3 py-2 text-sm border border-[#BEBAB7] rounded hover:bg-[#EEEAE7] transition-colors"
        >
          <RefreshCw size={13} />
          Обновить
        </button>
      </div>

      {/* Table */}
      {error && (
        <div className="flex items-center gap-2 text-red-600 text-sm mb-4">
          <AlertCircle size={15} />
          {error}
        </div>
      )}

      {loading ? (
        <p className="text-sm text-[#9A9590]">Загрузка…</p>
      ) : subscriptions.length === 0 ? (
        <div className="text-center py-16 text-[#9A9590] text-sm">
          Нет пользователей с подпиской для выбранного фильтра
        </div>
      ) : (
        <div className="bg-white border border-[#BEBAB7] rounded-lg overflow-hidden">
          <table className="min-w-full divide-y divide-[#EEEAE7]">
            <thead className="bg-[#FAFAFA]">
              <tr>
                {["Пользователь", "Статус", "Истекает", "Сообщений", "Лимит", "Ручной", ""].map(
                  (h) => (
                    <th
                      key={h}
                      className="px-4 py-3 text-left text-xs font-semibold text-[#9A9590] uppercase tracking-wider"
                    >
                      {h}
                    </th>
                  )
                )}
              </tr>
            </thead>
            <tbody className="divide-y divide-[#EEEAE7]">
              {subscriptions.map((sub) => (
                <tr key={sub.sub_id} className="hover:bg-[#FAFAFA] transition-colors">
                  <td className="px-4 py-3 text-sm font-mono text-[#251D1C]">
                    {sub.external_user_id}
                  </td>
                  <td className="px-4 py-3">
                    <StatusBadge status={sub.status} />
                  </td>
                  <td className="px-4 py-3 text-sm text-[#443C3C]">
                    {formatDate(sub.expires_at)}
                  </td>
                  <td className="px-4 py-3 text-sm text-[#443C3C]">{sub.messages_used}</td>
                  <td className="px-4 py-3 text-sm text-[#443C3C]">
                    {sub.messages_limit ?? "∞"}
                  </td>
                  <td className="px-4 py-3">
                    {sub.manual_override ? (
                      <CheckCircle2 size={14} className="text-blue-500" />
                    ) : (
                      <span className="text-[#EEEAE7]">—</span>
                    )}
                  </td>
                  <td className="px-4 py-3 text-right">
                    <button
                      type="button"
                      onClick={() => setOverrideSub(sub)}
                      className="text-xs text-[#443C3C] hover:text-[#251D1C] font-medium transition-colors"
                    >
                      Управление
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {overrideSub && selectedBindingId && (
        <OverrideModal
          sub={overrideSub}
          bindingId={selectedBindingId}
          onClose={() => setOverrideSub(null)}
          onSaved={(updated) => {
            setSubscriptions((prev) =>
              prev.map((s) => (s.sub_id === updated.sub_id ? updated : s))
            );
            setOverrideSub(null);
          }}
        />
      )}
    </div>
  );
}
