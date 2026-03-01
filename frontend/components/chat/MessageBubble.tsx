/** Message bubble component with avatars and improved styling. */

import React, { memo } from "react";
import type { Message } from "@/lib/types/message";
import { formatMessageTime } from "@/lib/utils/timeFormat";

/** Parse content and render [Image: URL] and ![alt](url) as <img> elements. */
function parseContentWithImages(content: string): React.ReactNode[] {
  const parts: React.ReactNode[] = [];
  // Match [Image: URL] or ![description](URL)
  const regex = /\[Image:\s*(https?:\/\/[^\]]+)\]|!\[([^\]]*)\]\((https?:\/\/[^)]+)\)/g;
  let lastIndex = 0;
  let match;
  while ((match = regex.exec(content)) !== null) {
    if (match.index > lastIndex) {
      parts.push(
        <span key={`t-${lastIndex}`}>{content.slice(lastIndex, match.index)}</span>
      );
    }
    const url = match[1] || match[3];
    const alt = match[2] || "Image";
    parts.push(
      <img
        key={`img-${match.index}`}
        src={url}
        alt={alt}
        className="max-w-full max-h-64 rounded-sm my-2 object-contain"
      />
    );
    lastIndex = regex.lastIndex;
  }
  if (lastIndex < content.length) {
    parts.push(<span key={`t-end`}>{content.slice(lastIndex)}</span>);
  }
  return parts.length > 0 ? parts : [content];
}

interface MessageBubbleProps {
  message: Message;
}

const getAvatar = (role: Message["role"]) => {
  switch (role) {
    case "user":
      return "👤";
    case "admin":
      return "👨‍💼";
    case "agent":
      return "🤖";
    default:
      return "💬";
  }
};

const getRoleLabel = (role: Message["role"]) => {
  switch (role) {
    case "user":
      return "You";
    case "admin":
      return "Admin";
    case "agent":
      return "AI Assistant";
    default:
      return "Unknown";
  }
};

export const MessageBubble: React.FC<MessageBubbleProps> = memo(({ message }) => {
  const isUser = message.role === "user";
  const isAdmin = message.role === "admin";
  const isAgent = message.role === "agent";

  return (
    <div
      className={`flex items-start gap-2 mb-4 ${isUser ? "flex-row-reverse" : "flex-row"}`}
    >
      {/* Avatar */}
      <div
        className={`flex-shrink-0 w-8 h-8 rounded-full flex items-center justify-center text-lg ${
          isUser
            ? "bg-[#D4AF37]/20"
            : isAdmin
            ? "bg-[#B8860B]/20"
            : "bg-[#F5D76E]/20"
        }`}
        aria-label={getRoleLabel(message.role)}
      >
        {getAvatar(message.role)}
      </div>

      {/* Message content */}
      <div className={`flex flex-col ${isUser ? "items-end" : "items-start"} max-w-[70%]`}>
        {/* Role label for admin/agent */}
        {(isAdmin || isAgent) && (
          <span
            className={`text-xs font-medium mb-1 ${
              isAdmin ? "text-[#B8860B]" : "text-[#D4AF37]"
            }`}
          >
            {getRoleLabel(message.role)}
          </span>
        )}

        {/* Message bubble */}
        <div
          className={`rounded-sm px-4 py-2.5 transition-all duration-200 ${
            isUser
              ? "bg-[#D4AF37] text-white shadow-sm"
              : isAdmin
              ? "bg-[#B8860B] text-white shadow-sm border border-[#D4AF37]"
              : "bg-white text-gray-900 border border-[#D4AF37]/30 shadow-sm"
          }`}
        >
          <div className="text-sm whitespace-pre-wrap break-words leading-relaxed">
            {parseContentWithImages(message.content)}
          </div>
        </div>

        {/* Timestamp */}
        <p
          className={`text-xs mt-1 px-1 ${
            isUser || isAdmin ? "text-gray-500" : "text-gray-400"
          }`}
        >
          {formatMessageTime(message.timestamp)}
        </p>
      </div>
    </div>
  );
});

MessageBubble.displayName = "MessageBubble";



