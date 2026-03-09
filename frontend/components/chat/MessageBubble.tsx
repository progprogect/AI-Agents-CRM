/** Message bubble component with avatars, media rendering and improved styling. */

import React, { memo } from "react";
import type { Message } from "@/lib/types/message";
import { formatMessageTime } from "@/lib/utils/timeFormat";

/** Parse content and render [Image: URL] and ![alt](url) as <img> elements. */
function parseContentWithImages(content: string): React.ReactNode[] {
  const parts: React.ReactNode[] = [];
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
    parts.push(<span key="t-end">{content.slice(lastIndex)}</span>);
  }
  return parts.length > 0 ? parts : [content];
}

/** Render a media attachment based on media_type. */
function MediaAttachment({
  url,
  mediaType,
  isUser,
  displayFilename,
}: {
  url: string;
  mediaType: string | null | undefined;
  isUser: boolean;
  displayFilename?: string | null;
}) {
  const type = mediaType || "document";

  if (type === "image") {
    return (
      <a href={url} target="_blank" rel="noopener noreferrer" className="block">
        <img
          src={url}
          alt="Attachment"
          className="max-w-full max-h-72 rounded-sm my-1 object-contain cursor-pointer hover:opacity-90 transition-opacity"
        />
      </a>
    );
  }

  if (type === "video") {
    return (
      <video
        src={url}
        controls
        className="max-w-full max-h-64 rounded-sm my-1"
      />
    );
  }

  if (type === "audio") {
    return (
      <audio src={url} controls className="w-full my-1" />
    );
  }

  // document / unknown — use provided displayName or extract from URL
  const urlFilename = url.split("/").pop()?.split("?")[0] || "file";
  // If the URL filename looks like a UUID (no spaces, long hex), hide it
  const isUuidFilename = /^[0-9a-f-]{36}\.[a-z]+$/i.test(urlFilename);
  const displayName = isUuidFilename ? (displayFilename || "Document") : (displayFilename || urlFilename);

  return (
    <a
      href={url}
      target="_blank"
      rel="noopener noreferrer"
      className={`flex items-center gap-2 my-1 px-3 py-2 rounded-sm border text-sm underline-offset-2 hover:opacity-80 transition-opacity ${
        isUser
          ? "border-white/30 text-white"
          : "border-[#251D1C]/20 text-[#251D1C]"
      }`}
    >
      <span className="text-base">📎</span>
      <span className="truncate max-w-[200px]">{displayName}</span>
    </a>
  );
}

interface MessageBubbleProps {
  message: Message;
}

const getAvatar = (role: Message["role"]) => {
  switch (role) {
    case "user":   return "👤";
    case "admin":  return "👨‍💼";
    case "agent":  return "🤖";
    default:       return "💬";
  }
};

const getRoleLabel = (role: Message["role"]) => {
  switch (role) {
    case "user":  return "You";
    case "admin": return "Admin";
    case "agent": return "AI Assistant";
    default:      return "Unknown";
  }
};

export const MessageBubble: React.FC<MessageBubbleProps> = memo(({ message }) => {
  const isUser  = message.role === "user";
  const isAdmin = message.role === "admin";
  const isAgent = message.role === "agent";

  // Prefer top-level fields, fall back to metadata
  const mediaUrl      = message.media_url      ?? message.metadata?.media_url      ?? null;
  const mediaType     = message.media_type     ?? message.metadata?.media_type     ?? null;
  const mediaFilename = message.media_filename ?? message.metadata?.media_filename ?? null;

  return (
    <div className={`flex items-start gap-2 mb-4 ${isUser ? "flex-row-reverse" : "flex-row"}`}>
      {/* Avatar */}
      <div
        className={`flex-shrink-0 w-8 h-8 rounded-full flex items-center justify-center text-lg ${
          isUser
            ? "bg-[#251D1C]/20"
            : isAdmin
            ? "bg-[#443C3C]/20"
            : "bg-[#EEEAE7]/20"
        }`}
        aria-label={getRoleLabel(message.role)}
      >
        {getAvatar(message.role)}
      </div>

      {/* Message content */}
      <div className={`flex flex-col ${isUser ? "items-end" : "items-start"} max-w-[70%]`}>
        {(isAdmin || isAgent) && (
          <span className={`text-xs font-medium mb-1 ${isAdmin ? "text-[#443C3C]" : "text-[#251D1C]"}`}>
            {getRoleLabel(message.role)}
          </span>
        )}

        <div
          className={`rounded-sm px-4 py-2.5 transition-all duration-200 ${
            isUser
              ? "bg-[#251D1C] text-white shadow-sm"
              : isAdmin
              ? "bg-[#443C3C] text-white shadow-sm border border-[#251D1C]"
              : "bg-white text-gray-900 border border-[#251D1C]/30 shadow-sm"
          }`}
        >
          {/* Media attachment */}
          {mediaUrl && (
            <MediaAttachment
              url={mediaUrl}
              mediaType={mediaType}
              isUser={isUser || isAdmin}
              displayFilename={mediaFilename}
            />
          )}

          {/* Text content */}
          {message.content && (
            <div className="text-sm whitespace-pre-wrap break-words leading-relaxed">
              {parseContentWithImages(message.content)}
            </div>
          )}

          {/* Fallback if both empty */}
          {!message.content && !mediaUrl && (
            <div className="text-sm opacity-50 italic">[empty message]</div>
          )}
        </div>

        <p className={`text-xs mt-1 px-1 ${isUser || isAdmin ? "text-gray-500" : "text-gray-400"}`}>
          {formatMessageTime(message.timestamp)}
        </p>
      </div>
    </div>
  );
});

MessageBubble.displayName = "MessageBubble";
