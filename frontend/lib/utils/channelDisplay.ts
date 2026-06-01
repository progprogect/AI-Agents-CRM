/** Utility functions for displaying channel information. */

/**
 * Get display text for a channel.
 * @param channel - Channel identifier (e.g., "instagram", "web_chat", "vk", "max")
 * @returns Formatted channel display string with emoji
 */
export function getChannelDisplay(channel?: string | null): string {
  if (!channel) return "-";
  if (channel === "instagram") return "📷 Instagram";
  if (channel === "telegram") return "💬 Telegram";
  if (channel === "web_chat") return "🌐 Web Chat";
  if (channel === "whatsapp") return "📱 WhatsApp";
  if (channel === "vk") return "💙 ВКонтакте";
  if (channel === "max") return "🔵 Max";
  return channel;
}

/**
 * Get short label for a channel (without emoji), suitable for badges.
 */
export function getChannelLabel(channel?: string | null): string {
  if (!channel) return "-";
  if (channel === "instagram") return "Instagram";
  if (channel === "telegram") return "Telegram";
  if (channel === "web_chat") return "Web Chat";
  if (channel === "whatsapp") return "WhatsApp";
  if (channel === "vk") return "ВКонтакте";
  if (channel === "max") return "Max";
  return channel;
}

export function isInstagramChannel(channel?: string | null): boolean {
  return channel === "instagram";
}

export function isWebChatChannel(channel?: string | null): boolean {
  return channel === "web_chat";
}

export function isTelegramChannel(channel?: string | null): boolean {
  return channel === "telegram";
}

export function isWhatsAppChannel(channel?: string | null): boolean {
  return channel === "whatsapp";
}

export function isVkChannel(channel?: string | null): boolean {
  return channel === "vk";
}

export function isMaxChannel(channel?: string | null): boolean {
  return channel === "max";
}
