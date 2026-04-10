"use client";

import React, { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Key, Save, Trash2, Eye, EyeOff, CheckCircle } from "lucide-react";
import { isAuthenticated, getAdminToken, canManageKeys } from "@/lib/auth";
import { LoadingSpinner } from "@/components/shared/LoadingSpinner";
import { Button } from "@/components/shared/Button";

const getApiUrl = (): string => {
  if (typeof window !== "undefined" && !window.location.host.startsWith("localhost")) return "";
  return process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
};

function authHeaders() {
  const token = getAdminToken();
  return {
    "Content-Type": "application/json",
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  };
}

interface LLMKeyStatus {
  provider: string;
  is_set: boolean;
  masked_key: string | null;
}

const PROVIDER_LABELS: Record<string, { label: string; placeholder: string }> = {
  openai: { label: "OpenAI API Key", placeholder: "sk-..." },
  google: { label: "Google AI Studio API Key", placeholder: "AI..." },
};

function LLMKeyRow({
  status,
  onSave,
  onDelete,
  readonly,
}: {
  status: LLMKeyStatus;
  onSave: (provider: string, key: string) => Promise<void>;
  onDelete: (provider: string) => Promise<void>;
  readonly: boolean;
}) {
  const [editing, setEditing] = useState(false);
  const [keyValue, setKeyValue] = useState("");
  const [saving, setSaving] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [showKey, setShowKey] = useState(false);
  const [saved, setSaved] = useState(false);

  const info = PROVIDER_LABELS[status.provider] ?? {
    label: status.provider,
    placeholder: "API key...",
  };

  const handleSave = async () => {
    if (!keyValue.trim()) return;
    setSaving(true);
    try {
      await onSave(status.provider, keyValue.trim());
      setKeyValue("");
      setEditing(false);
      setSaved(true);
      setTimeout(() => setSaved(false), 3000);
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async () => {
    if (!confirm(`Удалить ключ ${info.label}?`)) return;
    setDeleting(true);
    try {
      await onDelete(status.provider);
    } finally {
      setDeleting(false);
    }
  };

  return (
    <div className="p-4 border border-gray-200 rounded-xl bg-white">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <Key className="w-4 h-4 text-gray-400" />
          <span className="text-sm font-medium text-gray-800">{info.label}</span>
          {status.is_set && (
            <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-green-100 text-green-700">
              <CheckCircle className="w-3 h-3" />
              Установлен
            </span>
          )}
          {!status.is_set && (
            <span className="inline-flex px-2 py-0.5 rounded-full text-xs font-medium bg-gray-100 text-gray-500">
              Не задан
            </span>
          )}
          {saved && (
            <span className="text-xs text-green-600 font-medium">Сохранено!</span>
          )}
        </div>
        {!readonly && (
          <div className="flex gap-2">
            <Button
              variant="outline"
              onClick={() => setEditing(!editing)}
              className="text-xs"
            >
              {editing ? "Отмена" : status.is_set ? "Изменить" : "Добавить"}
            </Button>
            {status.is_set && (
              <button
                onClick={handleDelete}
                disabled={deleting}
                className="text-gray-400 hover:text-red-500 transition-colors disabled:opacity-40"
                title="Удалить ключ"
              >
                <Trash2 className="w-4 h-4" />
              </button>
            )}
          </div>
        )}
      </div>

      {status.is_set && status.masked_key && !editing && (
        <p className="text-xs text-gray-400 font-mono">{status.masked_key}</p>
      )}

      {editing && (
        <div className="mt-2 flex gap-2">
          <div className="relative flex-1">
            <input
              type={showKey ? "text" : "password"}
              value={keyValue}
              onChange={(e) => setKeyValue(e.target.value)}
              placeholder={info.placeholder}
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm pr-10 focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
            <button
              type="button"
              onClick={() => setShowKey(!showKey)}
              className="absolute right-2 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600"
            >
              {showKey ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
            </button>
          </div>
          <Button onClick={handleSave} disabled={saving || !keyValue.trim()}>
            {saving ? "..." : <><Save className="w-4 h-4 mr-1" />Сохранить</>}
          </Button>
        </div>
      )}
    </div>
  );
}

export default function SettingsPage() {
  const router = useRouter();
  const [keys, setKeys] = useState<LLMKeyStatus[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!isAuthenticated()) {
      router.replace("/admin/login");
    }
  }, [router]);

  const fetchKeys = async () => {
    setIsLoading(true);
    setError(null);
    try {
      const res = await fetch(`${getApiUrl()}/api/v1/org/llm-keys`, {
        headers: authHeaders(),
      });
      if (!res.ok) throw new Error(`Ошибка ${res.status}`);
      setKeys(await res.json());
    } catch {
      setError("Не удалось загрузить настройки ключей.");
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchKeys();
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const handleSave = async (provider: string, key: string) => {
    const res = await fetch(`${getApiUrl()}/api/v1/org/llm-keys`, {
      method: "PUT",
      headers: authHeaders(),
      body: JSON.stringify({ provider, key }),
    });
    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      throw new Error(data.detail || "Ошибка сохранения.");
    }
    await fetchKeys();
  };

  const handleDelete = async (provider: string) => {
    const res = await fetch(`${getApiUrl()}/api/v1/org/llm-keys/${provider}`, {
      method: "DELETE",
      headers: authHeaders(),
    });
    if (!res.ok) throw new Error("Ошибка удаления ключа.");
    await fetchKeys();
  };

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <LoadingSpinner />
      </div>
    );
  }

  return (
    <div className="max-w-2xl mx-auto py-8 px-4">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-gray-900">Настройки</h1>
        <p className="text-sm text-gray-500 mt-1">
          API-ключи для LLM-провайдеров вашей организации
        </p>
      </div>

      {error && (
        <div className="mb-4 p-3 bg-red-50 border border-red-200 rounded-lg text-red-700 text-sm">
          {error}
        </div>
      )}

      {!canManageKeys() && (
        <div className="mb-4 p-3 bg-amber-50 border border-amber-200 rounded-lg text-amber-700 text-sm">
          Только владелец организации может изменять API-ключи.
        </div>
      )}

      <div className="space-y-4">
        <h2 className="text-sm font-semibold text-gray-600 uppercase tracking-wider">
          LLM API-ключи
        </h2>
        {keys.map((k) => (
          <LLMKeyRow
            key={k.provider}
            status={k}
            onSave={handleSave}
            onDelete={handleDelete}
            readonly={!canManageKeys()}
          />
        ))}
        {keys.length === 0 && (
          <p className="text-sm text-gray-400 text-center py-4">
            Нет доступных провайдеров
          </p>
        )}
      </div>

      <div className="mt-6 p-3 bg-blue-50 border border-blue-100 rounded-lg text-xs text-blue-600">
        Ключи хранятся в зашифрованном виде. При отображении используется маскирование.
        Если ключ организации не задан, используется ключ платформы.
      </div>
    </div>
  );
}
