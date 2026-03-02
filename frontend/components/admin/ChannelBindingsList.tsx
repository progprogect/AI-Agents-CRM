/** List component for channel bindings. */

"use client";

import { Button } from "@/components/shared/Button";
import type { ChannelBinding } from "@/lib/types/channel";

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
          {bindings.map((binding) => (
            <tr
              key={binding.binding_id}
              className="hover:bg-[#EEEAE7]/5 transition-colors duration-150"
            >
              <td className="px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-900">
                {binding.channel_type === "instagram"
                  ? "Instagram"
                  : binding.channel_type === "telegram"
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
                <div className="flex gap-2">
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
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

