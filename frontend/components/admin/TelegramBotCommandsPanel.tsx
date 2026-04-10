/** Telegram bot menu commands (/restart, etc.) — loads toggles from API. */

"use client";

import { useCallback, useEffect, useState } from "react";
import { api, ApiError } from "@/lib/api";
import type { ChannelBinding, TelegramCommand } from "@/lib/types/channel";

type Props = {
  binding: ChannelBinding;
  /** When true, styles match embedded card footer (channels page). */
  embedded?: boolean;
};

export function TelegramBotCommandsPanel({ binding, embedded }: Props) {
  const [commands, setCommands] = useState<TelegramCommand[]>([]);
  const [loading, setLoading] = useState(true);
  const [savingKey, setSavingKey] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await api.getTelegramCommands(binding.binding_id);
      setCommands(data);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Не удалось загрузить команды");
    } finally {
      setLoading(false);
    }
  }, [binding.binding_id]);

  useEffect(() => {
    void load();
  }, [load]);

  const toggleCommand = async (key: string, currentEnabled: boolean) => {
    setSavingKey(key);
    setError(null);
    try {
      const updated = await api.updateTelegramCommands(binding.binding_id, {
        [key]: !currentEnabled,
      });
      setCommands(updated);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Не удалось сохранить");
    } finally {
      setSavingKey(null);
    }
  };

  const shell = embedded
    ? "px-4 py-3 bg-[#FAFAFA] border-t border-[#BEBAB7] rounded-b-md"
    : "px-6 py-4 bg-gray-50 border-t border-gray-100";

  if (loading) {
    return (
      <div className={`${shell} text-sm text-[#9A9590]`}>Загрузка команд…</div>
    );
  }

  return (
    <div className={shell}>
      <p
        className={`text-xs font-semibold uppercase tracking-wider mb-3 ${
          embedded ? "text-[#9A9590]" : "text-gray-500"
        }`}
      >
        Команды бота в Telegram
      </p>
      {commands.length === 0 ? (
        <p className={`text-sm ${embedded ? "text-[#9A9590]" : "text-gray-400"}`}>
          Нет доступных команд
        </p>
      ) : (
        <div className="flex flex-col gap-3">
          {commands.map((cmd) => {
            const isSaving = savingKey === cmd.key;
            return (
              <div
                key={cmd.key}
                className={`flex items-start justify-between gap-4 rounded-sm border p-3 ${
                  embedded
                    ? "border-[#BEBAB7] bg-white"
                    : "border-gray-200 bg-white"
                }`}
              >
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-mono font-semibold text-[#251D1C]">
                      {cmd.command}
                    </span>
                    {cmd.enabled && (
                      <span className="text-xs bg-green-100 text-green-700 px-1.5 py-0.5 rounded-sm font-medium">
                        Включена
                      </span>
                    )}
                  </div>
                  <p className="text-xs text-[#9A9590] mt-0.5">{cmd.description}</p>
                </div>
                <button
                  type="button"
                  role="switch"
                  aria-checked={cmd.enabled}
                  aria-label={`${cmd.enabled ? "Выключить" : "Включить"} команду ${cmd.command}`}
                  disabled={isSaving}
                  onClick={() => void toggleCommand(cmd.key, cmd.enabled)}
                  className={`relative inline-flex h-6 w-11 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 focus:outline-none focus:ring-2 focus:ring-[#251D1C] focus:ring-offset-2 disabled:opacity-60 ${
                    cmd.enabled ? "bg-[#251D1C]" : "bg-gray-200"
                  }`}
                >
                  <span
                    className={`pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow ring-0 transition duration-200 ${
                      cmd.enabled ? "translate-x-5" : "translate-x-0"
                    }`}
                  />
                </button>
              </div>
            );
          })}
        </div>
      )}
      {error && <p className="mt-2 text-xs text-red-600">{error}</p>}
      <p className={`mt-3 text-xs ${embedded ? "text-[#9A9590]" : "text-gray-400"}`}>
        При включении команда сразу появляется в меню бота в Telegram. Пользователи могут нажать
        на неё прямо в чате.
      </p>
    </div>
  );
}
