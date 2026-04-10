/** List component for channel bindings with bot command management. */

"use client";

import { useState, useEffect, useCallback } from "react";
import { Button } from "@/components/shared/Button";
import { api, ApiError } from "@/lib/api";
import type { ChannelBinding, TelegramCommand } from "@/lib/types/channel";

interface ChannelBindingsListProps {
  bindings: ChannelBinding[];
  onDelete: (bindingId: string) => void;
  onToggleActive: (bindingId: string, isActive: boolean) => void;
  onVerify: (bindingId: string) => void;
}

// ---------------------------------------------------------------------------
// Bot commands panel (inline, shown per Telegram binding)
// ---------------------------------------------------------------------------

function BotCommandsPanel({ binding }: { binding: ChannelBinding }) {
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

  if (loading) {
    return (
      <div className="px-6 py-4 bg-gray-50 border-t border-gray-100 text-sm text-gray-500">
        Загрузка команд…
      </div>
    );
  }

  return (
    <div className="px-6 py-4 bg-gray-50 border-t border-gray-100">
      <p className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-3">
        Команды бота в Telegram
      </p>
      {commands.length === 0 ? (
        <p className="text-sm text-gray-400">Нет доступных команд</p>
      ) : (
        <div className="flex flex-col gap-3">
          {commands.map((cmd) => {
            const isSaving = savingKey === cmd.key;
            return (
              <div
                key={cmd.key}
                className="flex items-start justify-between gap-4 rounded-sm border border-gray-200 bg-white p-3"
              >
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-mono font-semibold text-gray-800">
                      {cmd.command}
                    </span>
                    {cmd.enabled && (
                      <span className="text-xs bg-green-100 text-green-700 px-1.5 py-0.5 rounded-sm font-medium">
                        Включена
                      </span>
                    )}
                  </div>
                  <p className="text-xs text-gray-500 mt-0.5">{cmd.description}</p>
                </div>
                {/* Toggle switch */}
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
      {error && (
        <p className="mt-2 text-xs text-red-600">{error}</p>
      )}
      <p className="mt-3 text-xs text-gray-400">
        При включении команда сразу появляется в меню бота в Telegram.
        Пользователи могут нажать на неё прямо в чате.
      </p>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main list component
// ---------------------------------------------------------------------------

export function ChannelBindingsList({
  bindings,
  onDelete,
  onToggleActive,
  onVerify,
}: ChannelBindingsListProps) {
  const [expandedCommands, setExpandedCommands] = useState<string | null>(null);

  const toggleCommandsPanel = (bindingId: string) => {
    setExpandedCommands((prev) => (prev === bindingId ? null : bindingId));
  };

  if (bindings.length === 0) {
    return (
      <div className="text-center py-16 bg-white rounded-sm shadow border border-[#251D1C]/20">
        <div className="max-w-md mx-auto">
          <div className="text-6xl mb-4">📱</div>
          <h2 className="text-xl font-semibold text-gray-900 mb-2">
            No channel bindings yet
          </h2>
          <p className="text-gray-600">
            Connect a channel (Instagram or Telegram) to start receiving messages.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="bg-white rounded-sm shadow border border-[#251D1C]/20 overflow-hidden">
      <table className="min-w-full divide-y divide-gray-200">
        <thead className="bg-[#EEEAE7]/10">
          <tr>
            <th className="px-6 py-3 text-left text-xs font-medium text-[#443C3C] uppercase tracking-wider">
              Channel
            </th>
            <th className="px-6 py-3 text-left text-xs font-medium text-[#443C3C] uppercase tracking-wider">
              Account ID
            </th>
            <th className="px-6 py-3 text-left text-xs font-medium text-[#443C3C] uppercase tracking-wider">
              Username
            </th>
            <th className="px-6 py-3 text-left text-xs font-medium text-[#443C3C] uppercase tracking-wider">
              Status
            </th>
            <th className="px-6 py-3 text-left text-xs font-medium text-[#443C3C] uppercase tracking-wider">
              Verified
            </th>
            <th className="px-6 py-3 text-left text-xs font-medium text-[#443C3C] uppercase tracking-wider">
              Actions
            </th>
          </tr>
        </thead>
        <tbody className="bg-white divide-y divide-gray-200">
          {bindings.map((binding) => {
            const isTelegram = binding.channel_type === "telegram";
            const commandsOpen = expandedCommands === binding.binding_id;

            return (
              <>
                <tr
                  key={binding.binding_id}
                  className="hover:bg-[#EEEAE7]/5 transition-colors duration-150"
                >
                  <td className="px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-900">
                    {binding.channel_type === "instagram"
                      ? "Instagram"
                      : isTelegram
                      ? "Telegram"
                      : binding.channel_type}
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                    {binding.channel_account_id}
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                    {binding.channel_username || "-"}
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap">
                    <span
                      className={`px-2 inline-flex text-xs leading-5 font-semibold rounded-sm ${
                        binding.is_active
                          ? "bg-[#EEEAE7]/20 text-[#443C3C] border border-[#251D1C]/30"
                          : "bg-gray-100 text-gray-800"
                      }`}
                    >
                      {binding.is_active ? "Active" : "Inactive"}
                    </span>
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap">
                    <span
                      className={`px-2 inline-flex text-xs leading-5 font-semibold rounded-sm ${
                        binding.is_verified
                          ? "bg-green-100 text-green-800"
                          : "bg-yellow-100 text-yellow-800"
                      }`}
                    >
                      {binding.is_verified ? "Verified" : "Not Verified"}
                    </span>
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm font-medium">
                    <div className="flex gap-2 flex-wrap">
                      <button
                        onClick={() => onToggleActive(binding.binding_id, binding.is_active)}
                        className={`text-sm ${
                          binding.is_active
                            ? "text-yellow-600 hover:text-yellow-700"
                            : "text-green-600 hover:text-green-700"
                        } transition-colors duration-200 cursor-pointer`}
                        title={binding.is_active ? "Deactivate" : "Activate"}
                      >
                        {binding.is_active ? "Deactivate" : "Activate"}
                      </button>
                      <button
                        onClick={() => onVerify(binding.binding_id)}
                        className="text-blue-600 hover:text-blue-700 transition-colors duration-200 cursor-pointer"
                        title="Verify token"
                      >
                        Verify
                      </button>
                      <button
                        onClick={() => onDelete(binding.binding_id)}
                        className="text-red-600 hover:text-red-700 transition-colors duration-200 cursor-pointer"
                        title="Delete binding"
                      >
                        Delete
                      </button>
                      {isTelegram && (
                        <button
                          onClick={() => toggleCommandsPanel(binding.binding_id)}
                          className="text-[#443C3C] hover:text-[#251D1C] transition-colors duration-200 cursor-pointer flex items-center gap-0.5"
                          title="Manage bot commands"
                        >
                          Команды
                          <span className="text-xs">{commandsOpen ? "▲" : "▼"}</span>
                        </button>
                      )}
                    </div>
                  </td>
                </tr>
                {isTelegram && commandsOpen && (
                  <tr key={`${binding.binding_id}-commands`}>
                    <td colSpan={6} className="p-0">
                      <BotCommandsPanel binding={binding} />
                    </td>
                  </tr>
                )}
              </>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
