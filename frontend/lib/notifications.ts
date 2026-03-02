/** Notification service for browser notifications and toast messages. */

const NOTIFICATION_PERMISSION_KEY = "agent_notification_permission";
const NOTIFICATION_SOUND_ENABLED_KEY = "agent_notification_sound_enabled";

export type NotificationPermission = "default" | "granted" | "denied";

/**
 * Check if browser notifications are supported.
 */
export function isNotificationSupported(): boolean {
  if (typeof window === "undefined") {
    return false;
  }
  return "Notification" in window;
}

/**
 * Get current notification permission status.
 */
export function getNotificationPermission(): NotificationPermission {
  if (!isNotificationSupported()) {
    return "denied";
  }
  return Notification.permission as NotificationPermission;
}

/**
 * Request notification permission from user.
 */
export async function requestNotificationPermission(): Promise<NotificationPermission> {
  if (!isNotificationSupported()) {
    return "denied";
  }

  if (Notification.permission === "granted") {
    return "granted";
  }

  if (Notification.permission === "denied") {
    return "denied";
  }

  try {
    const permission = await Notification.requestPermission();
    return permission as NotificationPermission;
  } catch (error) {
    console.error("Error requesting notification permission:", error);
    return "denied";
  }
}

/**
 * Show browser notification.
 */
export function showNotification(
  title: string,
  options?: NotificationOptions
): Notification | null {
  if (!isNotificationSupported()) {
    return null;
  }

  if (Notification.permission !== "granted") {
    return null;
  }

  try {
    const notification = new Notification(title, {
      icon: "/logo.svg",
      badge: "/logo.svg",
      ...options,
    });

    // Auto-close after 5 seconds
    setTimeout(() => {
      notification.close();
    }, 5000);

    return notification;
  } catch (error) {
    console.error("Error showing notification:", error);
    return null;
  }
}

/**
 * Play notification sound (optional).
 */
export function playNotificationSound(): void {
  if (typeof window === "undefined") {
    return;
  }

  const soundEnabled = localStorage.getItem(NOTIFICATION_SOUND_ENABLED_KEY);
  if (soundEnabled === "false") {
    return;
  }

  try {
    // Create a simple beep sound using Web Audio API
    const audioContext = new (window.AudioContext ||
      (window as any).webkitAudioContext)();
    const oscillator = audioContext.createOscillator();
    const gainNode = audioContext.createGain();

    oscillator.connect(gainNode);
    gainNode.connect(audioContext.destination);

    oscillator.frequency.value = 800;
    oscillator.type = "sine";

    gainNode.gain.setValueAtTime(0.3, audioContext.currentTime);
    gainNode.gain.exponentialRampToValueAtTime(0.01, audioContext.currentTime + 0.2);

    oscillator.start(audioContext.currentTime);
    oscillator.stop(audioContext.currentTime + 0.2);
  } catch (error) {
    console.error("Error playing notification sound:", error);
  }
}

/**
 * Show toast notification (fallback when browser notifications are not available).
 */
export function showToast(
  message: string,
  type: "info" | "warning" | "error" | "success" = "info",
  duration: number = 5000
): void {
  if (typeof window === "undefined") {
    return;
  }

  // Create toast element
  const toast = document.createElement("div");
  toast.className = `fixed top-4 right-4 z-50 px-4 py-3 rounded-sm shadow-lg max-w-md transition-all duration-300 transform translate-x-full`;
  
  // Set background color based on type
  const bgColors = {
    info: "bg-blue-500",
    warning: "bg-yellow-500",
    error: "bg-red-500",
    success: "bg-green-500",
  };
  toast.className += ` ${bgColors[type]} text-white`;

  toast.textContent = message;
  document.body.appendChild(toast);

  // Animate in
  setTimeout(() => {
    toast.classList.remove("translate-x-full");
  }, 10);

  // Remove after duration
  setTimeout(() => {
    toast.classList.add("translate-x-full");
    setTimeout(() => {
      document.body.removeChild(toast);
    }, 300);
  }, duration);
}

/**
 * Show notification for new escalation.
 */
export async function showEscalationNotification(
  conversationId: string,
  reason?: string
): Promise<void> {
  const title = "New Conversation Escalation";
  const body = reason
    ? `Conversation ${conversationId.substring(0, 8)}... requires attention: ${reason}`
    : `Conversation ${conversationId.substring(0, 8)}... requires attention`;

  // Try browser notification first
  const permission = getNotificationPermission();
  if (permission === "granted") {
    showNotification(title, {
      body,
      tag: `escalation-${conversationId}`,
      requireInteraction: false,
    });
    playNotificationSound();
  } else if (permission === "default") {
    // Request permission and show notification if granted
    const newPermission = await requestNotificationPermission();
    if (newPermission === "granted") {
      showNotification(title, {
        body,
        tag: `escalation-${conversationId}`,
        requireInteraction: false,
      });
      playNotificationSound();
    } else {
      // Fallback to toast
      showToast(body, "warning");
    }
  } else {
    // Fallback to toast
    showToast(body, "warning");
  }
}

/**
 * Get notification sound enabled state.
 */
export function isNotificationSoundEnabled(): boolean {
  if (typeof window === "undefined") {
    return true; // Default to enabled
  }
  const enabled = localStorage.getItem(NOTIFICATION_SOUND_ENABLED_KEY);
  return enabled !== "false";
}

/**
 * Set notification sound enabled state.
 */
export function setNotificationSoundEnabled(enabled: boolean): void {
  if (typeof window === "undefined") {
    return;
  }
  localStorage.setItem(NOTIFICATION_SOUND_ENABLED_KEY, enabled.toString());
}

