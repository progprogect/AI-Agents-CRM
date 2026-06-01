/** List component for channel bindings with bot command management. */

"use client";

import React, { useState } from "react";
import { TelegramBotCommandsPanel } from "@/components/admin/TelegramBotCommandsPanel";
import type { ChannelBinding } from "@/lib/types/channel";
import { getChannelLabel } from "@/lib/utils/channelDisplay";

interface ChannelBindingsListProps {
  bindings: ChannelBinding[];
  onDelete: (bindingId: string) => void;
  onToggleActive: (bindingId: string, isActive: boolean) => void;
  onVerify: (bindingId: string) => void;
}

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
          <div className="text-6xl mb-4" aria-hidden>
            {"\u{1F4F1}"}
          </div>
          <h2 className="text-xl font-semibold text-gray-900 mb-2">
            No channel bindings yet
          </h2>
          <p className="text-gray-600">
            Connect a channel (Instagram, Telegram, WhatsApp, VK, or Max) to start receiving messages.
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
            const isVk = binding.channel_type === "vk";
            const isMax = binding.channel_type === "max";
            const commandsOpen = expandedCommands === binding.binding_id;
            const vkConfirmationCode = isVk ? (binding.metadata?.confirmation_code as string | undefined) : undefined;

            return (
              <React.Fragment key={binding.binding_id}>
                <tr
                  className="hover:bg-[#EEEAE7]/5 transition-colors duration-150"
                >
                  <td className="px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-900">
                    {getChannelLabel(binding.channel_type)}
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
                          <span className="text-xs">{commandsOpen ? "\u25b2" : "\u25bc"}</span>
                        </button>
                      )}
                      {isVk && vkConfirmationCode && (
                        <span
                          className="text-xs text-[#9A9590] font-mono bg-[#EEEAE7] px-1.5 py-0.5 rounded select-all"
                          title="VK confirmation code — copy into Callback API settings"
                        >
                          code: {vkConfirmationCode}
                        </span>
                      )}
                      {(isVk || isMax) && binding.metadata?.webhook_url && (
                        <span
                          className="text-xs text-[#9A9590] truncate max-w-[180px] block"
                          title={binding.metadata.webhook_url as string}
                        >
                          🔗 {(binding.metadata.webhook_url as string).split("/").slice(-3).join("/")}
                        </span>
                      )}
                    </div>
                  </td>
                </tr>
                {isTelegram && commandsOpen && (
                  <tr>
                    <td colSpan={6} className="p-0">
                      <TelegramBotCommandsPanel binding={binding} />
                    </td>
                  </tr>
                )}
              </React.Fragment>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
