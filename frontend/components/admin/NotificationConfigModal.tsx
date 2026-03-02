/** Modal for creating/editing notification configs. */

"use client";

import { useState, useEffect } from "react";
import { api, ApiError } from "@/lib/api";
import { Button } from "@/components/shared/Button";
import { Input } from "@/components/shared/Input";
import type {
  NotificationConfig,
  CreateNotificationConfigRequest,
  UpdateNotificationConfigRequest,
} from "@/lib/types/notification";

interface NotificationConfigModalProps {
  config?: NotificationConfig | null;
  onClose: () => void;
  onSuccess: () => void;
}

export function NotificationConfigModal({
  config,
  onClose,
  onSuccess,
}: NotificationConfigModalProps) {
  const [formData, setFormData] = useState<{
    bot_token: string;
    chat_id: string;
    description: string;
  }>({
    bot_token: "",
    chat_id: "",
    description: "",
  });
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isTesting, setIsTesting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  useEffect(() => {
    if (config) {
      setFormData({
        bot_token: "", // Don't show existing token for security
        chat_id: config.chat_id,
        description: config.description || "",
      });
    }
  }, [config]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setSuccessMessage(null);
    setIsSubmitting(true);

    try {
      if (config) {
        // Update existing config
        const updateData: UpdateNotificationConfigRequest = {
          chat_id: formData.chat_id,
          description: formData.description || undefined,
        };
        if (formData.bot_token) {
          updateData.bot_token = formData.bot_token;
        }
        await api.updateNotificationConfig(config.config_id, updateData);
      } else {
        // Create new config
        const createData: CreateNotificationConfigRequest = {
          notification_type: "telegram",
          bot_token: formData.bot_token,
          chat_id: formData.chat_id,
          description: formData.description || undefined,
        };
        await api.createNotificationConfig(createData);
      }
      setSuccessMessage("Notification config saved successfully!");
      setTimeout(() => {
        onSuccess();
      }, 1000);
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err.message);
      } else {
        setError("Failed to save notification config");
      }
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleTest = async () => {
    if (!config) {
      setError("Please save the config first before testing");
      return;
    }
    setError(null);
    setSuccessMessage(null);
    setIsTesting(true);

    try {
      await api.testNotification(config.config_id);
      setSuccessMessage("Test notification sent successfully! Check your Telegram.");
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err.message);
      } else {
        setError("Failed to send test notification");
      }
    } finally {
      setIsTesting(false);
    }
  };

  const handleChange = (
    e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>
  ) => {
    const { name, value } = e.target;
    setFormData({ ...formData, [name]: value });
  };

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
      <div className="bg-white rounded-sm shadow-lg max-w-md w-full mx-4 p-6 max-h-[90vh] overflow-y-auto">
        <h2 className="text-xl font-bold text-gray-900 mb-4">
          {config ? "Edit Notification Config" : "Add Notification Config"}
        </h2>

        {error && (
          <div className="bg-red-50 border-l-4 border-red-500 p-4 mb-4 rounded-sm">
            <p className="text-sm text-red-700">{error}</p>
          </div>
        )}

        {successMessage && (
          <div className="bg-green-50 border-l-4 border-green-500 p-4 mb-4 rounded-sm">
            <p className="text-sm text-green-700">{successMessage}</p>
          </div>
        )}

        <form onSubmit={handleSubmit}>
          <div className="space-y-4">
            <Input
              label="Bot Token"
              name="bot_token"
              type="password"
              value={formData.bot_token}
              onChange={handleChange}
              required={!config}
              placeholder={config ? "Leave empty to keep current token" : "Enter Telegram bot token"}
              helperText={
                config
                  ? "Leave empty to keep the current token, or enter a new token to update"
                  : "Get your bot token from @BotFather on Telegram"
              }
            />

            <Input
              label="Chat ID"
              name="chat_id"
              type="text"
              value={formData.chat_id}
              onChange={handleChange}
              required
              placeholder="Enter Telegram chat ID"
              helperText="To get your chat ID: Start a chat with your bot and send /start, then use @userinfobot to get your chat ID"
            />

            <div>
              <label
                htmlFor="description"
                className="block text-sm font-medium text-gray-700 mb-1"
              >
                Description (optional)
              </label>
              <textarea
                id="description"
                name="description"
                rows={3}
                value={formData.description}
                onChange={handleChange}
                className="w-full px-3 py-2 border border-gray-300 rounded-sm shadow-sm focus:outline-none focus:ring-[#251D1C] focus:border-[#251D1C]"
                placeholder="e.g., Admin notifications, Team alerts, etc."
              />
            </div>
          </div>

          <div className="mt-6 flex gap-3 justify-end">
            {config && (
              <Button
                type="button"
                variant="secondary"
                onClick={handleTest}
                disabled={isTesting || isSubmitting}
              >
                {isTesting ? "Sending..." : "Test"}
              </Button>
            )}
            <Button
              type="button"
              variant="secondary"
              onClick={onClose}
              disabled={isSubmitting || isTesting}
            >
              Cancel
            </Button>
            <Button
              type="submit"
              variant="primary"
              disabled={isSubmitting || isTesting}
            >
              {isSubmitting ? "Saving..." : config ? "Update" : "Create"}
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
}
