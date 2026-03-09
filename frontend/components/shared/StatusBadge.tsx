/** Status badge component for displaying conversation status consistently. */

"use client";

import React from "react";
import { useTranslations } from "next-intl";
import type { ConversationStatus } from "@/lib/types/conversation";
import { getStatusDisplay } from "@/lib/utils/statusDisplay";

const STATUS_LABEL_KEYS: Record<ConversationStatus, string> = {
  AI_ACTIVE: "aiResponding",
  NEEDS_HUMAN: "needsAttention",
  HUMAN_ACTIVE: "adminActive",
  CLOSED: "closed",
};

const STATUS_ARIA_KEYS: Record<ConversationStatus, string> = {
  AI_ACTIVE: "aiRespondingAria",
  NEEDS_HUMAN: "needsAttentionAria",
  HUMAN_ACTIVE: "adminActiveAria",
  CLOSED: "closedAria",
};

interface StatusBadgeProps {
  status: ConversationStatus;
  size?: "sm" | "md";
  showIcon?: boolean;
  className?: string;
}

export const StatusBadge: React.FC<StatusBadgeProps> = ({
  status,
  size = "md",
  showIcon = true,
  className = "",
}) => {
  const t = useTranslations("Status");
  const statusDisplay = getStatusDisplay(status);
  const label = t(STATUS_LABEL_KEYS[status] ?? "closed");
  const ariaLabel = t(STATUS_ARIA_KEYS[status] ?? "closedAria");

  const sizeClasses = {
    sm: "px-2 py-0.5 text-xs",
    md: "px-2 py-1 text-xs",
  };

  return (
    <span
      className={`inline-flex items-center gap-1 leading-5 font-semibold rounded-sm ${statusDisplay.colorClasses} ${sizeClasses[size]} ${className}`}
      aria-label={ariaLabel}
      role="status"
    >
      {showIcon && <span aria-hidden="true">{statusDisplay.icon}</span>}
      <span>{label}</span>
    </span>
  );
};
