/** Notifications management page. */

"use client";

import { useEffect, useState } from "react";
import { api, ApiError } from "@/lib/api";
import { LoadingSpinner } from "@/components/shared/LoadingSpinner";
import { Button } from "@/components/shared/Button";
import type { NotificationConfig } from "@/lib/types/notification";
import { NotificationConfigList } from "@/components/admin/NotificationConfigList";
import { NotificationConfigModal } from "@/components/admin/NotificationConfigModal";

export default function NotificationsPage() {
  const [configs, setConfigs] = useState<NotificationConfig[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [editingConfig, setEditingConfig] = useState<NotificationConfig | null>(null);
  const [isDeleting, setIsDeleting] = useState<string | null>(null);
  const [isToggling, setIsToggling] = useState<string | null>(null);
  const [isTesting, setIsTesting] = useState<string | null>(null);

  useEffect(() => {
    loadConfigs();
  }, []);

  const loadConfigs = async () => {
    try {
      setIsLoading(true);
      setError(null);
      const configsData = await api.listNotificationConfigs(false);
      setConfigs(configsData);
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err.message);
      } else {
        setError("Failed to load notification configs");
      }
    } finally {
      setIsLoading(false);
    }
  };

  const handleCreateConfig = () => {
    setEditingConfig(null);
    setIsModalOpen(true);
  };

  const handleEditConfig = (config: NotificationConfig) => {
    setEditingConfig(config);
    setIsModalOpen(true);
  };

  const handleModalClose = () => {
    setIsModalOpen(false);
    setEditingConfig(null);
  };

  const handleModalSuccess = () => {
    setIsModalOpen(false);
    setEditingConfig(null);
    loadConfigs();
  };

  const handleDeleteConfig = async (configId: string) => {
    if (!confirm("Are you sure you want to delete this notification config?")) {
      return;
    }

    try {
      setIsDeleting(configId);
      await api.deleteNotificationConfig(configId);
      setConfigs(configs.filter((c) => c.config_id !== configId));
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err.message);
      } else {
        setError("Failed to delete notification config");
      }
    } finally {
      setIsDeleting(null);
    }
  };

  const handleToggleActive = async (configId: string, isActive: boolean) => {
    try {
      setIsToggling(configId);
      const updated = await api.updateNotificationConfig(configId, {
        is_active: !isActive,
      });
      setConfigs(
        configs.map((c) => (c.config_id === configId ? updated : c))
      );
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err.message);
      } else {
        setError("Failed to update notification config");
      }
    } finally {
      setIsToggling(null);
    }
  };

  const handleTest = async (configId: string) => {
    try {
      setIsTesting(configId);
      await api.testNotification(configId);
      alert("Test notification sent successfully! Check your Telegram.");
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err.message);
        alert(`Failed to send test notification: ${err.message}`);
      } else {
        setError("Failed to send test notification");
        alert("Failed to send test notification");
      }
    } finally {
      setIsTesting(null);
    }
  };

  if (isLoading) {
    return (
      <div className="flex items-center justify-center min-h-screen bg-white">
        <LoadingSpinner size="lg" />
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-white via-[#EEEAE7]/5 to-[#251D1C]/10">
      <div className="container mx-auto px-4 py-8">
        <div className="mb-6 flex items-center justify-between">
          <div>
            <h1 className="text-3xl font-bold text-gray-900">Notifications</h1>
            <p className="text-gray-600 mt-1">
              Configure Telegram notifications for escalation alerts
            </p>
          </div>
          <Button variant="primary" onClick={handleCreateConfig}>
            Add Notification
          </Button>
        </div>

        {error && (
          <div className="bg-red-50 border-l-4 border-red-500 p-4 mb-6 rounded-sm">
            <p className="text-sm text-red-700">{error}</p>
          </div>
        )}

        <NotificationConfigList
          configs={configs}
          onDelete={handleDeleteConfig}
          onToggleActive={handleToggleActive}
          onTest={handleTest}
          onEdit={handleEditConfig}
        />

        {isModalOpen && (
          <NotificationConfigModal
            config={editingConfig}
            onClose={handleModalClose}
            onSuccess={handleModalSuccess}
          />
        )}
      </div>
    </div>
  );
}
