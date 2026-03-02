/** List component for notification configs. */

"use client";

import { Button } from "@/components/shared/Button";
import type { NotificationConfig } from "@/lib/types/notification";

interface NotificationConfigListProps {
  configs: NotificationConfig[];
  onDelete: (configId: string) => void;
  onToggleActive: (configId: string, isActive: boolean) => void;
  onTest: (configId: string) => void;
  onEdit: (config: NotificationConfig) => void;
}

export function NotificationConfigList({
  configs,
  onDelete,
  onToggleActive,
  onTest,
  onEdit,
}: NotificationConfigListProps) {
  if (configs.length === 0) {
    return (
      <div className="text-center py-16 bg-white rounded-sm shadow border border-[#251D1C]/20">
        <div className="max-w-md mx-auto">
          <div className="text-6xl mb-4">🔔</div>
          <h2 className="text-xl font-semibold text-gray-900 mb-2">
            No notification configs yet
          </h2>
          <p className="text-gray-600">
            Add a notification configuration to receive alerts when conversations are escalated.
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
              Type
            </th>
            <th className="px-6 py-3 text-left text-xs font-medium text-[#443C3C] uppercase tracking-wider">
              Chat ID
            </th>
            <th className="px-6 py-3 text-left text-xs font-medium text-[#443C3C] uppercase tracking-wider">
              Description
            </th>
            <th className="px-6 py-3 text-left text-xs font-medium text-[#443C3C] uppercase tracking-wider">
              Status
            </th>
            <th className="px-6 py-3 text-left text-xs font-medium text-[#443C3C] uppercase tracking-wider">
              Actions
            </th>
          </tr>
        </thead>
        <tbody className="bg-white divide-y divide-gray-200">
          {configs.map((config) => (
            <tr
              key={config.config_id}
              className="hover:bg-[#EEEAE7]/5 transition-colors duration-150"
            >
              <td className="px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-900">
                {config.notification_type === "telegram" ? "Telegram" : config.notification_type}
              </td>
              <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                {config.chat_id}
              </td>
              <td className="px-6 py-4 text-sm text-gray-500">
                {config.description || "-"}
              </td>
              <td className="px-6 py-4 whitespace-nowrap">
                <span
                  className={`px-2 inline-flex text-xs leading-5 font-semibold rounded-sm ${
                    config.is_active
                      ? "bg-[#EEEAE7]/20 text-[#443C3C] border border-[#251D1C]/30"
                      : "bg-gray-100 text-gray-800"
                  }`}
                >
                  {config.is_active ? "Active" : "Inactive"}
                </span>
              </td>
              <td className="px-6 py-4 whitespace-nowrap text-sm font-medium">
                <div className="flex gap-2">
                  <button
                    onClick={() => onEdit(config)}
                    className="text-blue-600 hover:text-blue-700 transition-colors duration-200 cursor-pointer"
                    title="Edit config"
                  >
                    Edit
                  </button>
                  <button
                    onClick={() => onTest(config.config_id)}
                    className="text-green-600 hover:text-green-700 transition-colors duration-200 cursor-pointer"
                    title="Send test notification"
                  >
                    Test
                  </button>
                  <button
                    onClick={() => onToggleActive(config.config_id, config.is_active)}
                    className={`text-sm ${
                      config.is_active
                        ? "text-yellow-600 hover:text-yellow-700"
                        : "text-green-600 hover:text-green-700"
                    } transition-colors duration-200 cursor-pointer`}
                    title={config.is_active ? "Deactivate" : "Activate"}
                  >
                    {config.is_active ? "Deactivate" : "Activate"}
                  </button>
                  <button
                    onClick={() => onDelete(config.config_id)}
                    className="text-red-600 hover:text-red-700 transition-colors duration-200 cursor-pointer"
                    title="Delete config"
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
