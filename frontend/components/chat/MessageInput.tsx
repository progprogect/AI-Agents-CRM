/** Message input component with send icon and improved styling. */

import React, { useState, KeyboardEvent, useRef, useEffect } from "react";
import { Button } from "@/components/shared/Button";

interface MessageInputProps {
  onSend: (content: string) => void;
  disabled?: boolean;
  placeholder?: string;
  maxLength?: number;
}

const SendIcon = () => (
  <svg
    xmlns="http://www.w3.org/2000/svg"
    fill="none"
    viewBox="0 0 24 24"
    strokeWidth={2}
    stroke="currentColor"
    className="h-4 w-4"
  >
    <path
      strokeLinecap="round"
      strokeLinejoin="round"
      d="M6 12L3.269 3.126A59.768 59.768 0 0121.485 12 59.77 59.77 0 013.27 20.876L5.999 12zm0 0h7.5"
    />
  </svg>
);

export const MessageInput: React.FC<MessageInputProps> = ({
  onSend,
  disabled = false,
  placeholder = "Type your message...",
  maxLength,
}) => {
  const [content, setContent] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // Auto-resize textarea
  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
      textareaRef.current.style.height = `${textareaRef.current.scrollHeight}px`;
    }
  }, [content]);

  const handleSend = () => {
    if (content.trim() && !disabled) {
      onSend(content);
      setContent("");
      if (textareaRef.current) {
        textareaRef.current.style.height = "auto";
      }
    }
  };

  const handleKeyPress = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    const value = e.target.value;
    if (maxLength && value.length > maxLength) {
      return;
    }
    setContent(value);
  };

  const remainingChars = maxLength ? maxLength - content.length : null;
  const isNearLimit = maxLength && remainingChars !== null && remainingChars < 20;

  return (
    <div className="border-t border-[#251D1C]/20 p-4 bg-white">
      <div className="flex gap-2 items-end">
        <div className="flex-1 flex flex-col">
          <textarea
            ref={textareaRef}
            value={content}
            onChange={handleChange}
            onKeyPress={handleKeyPress}
            disabled={disabled}
            placeholder={placeholder}
            rows={1}
            maxLength={maxLength}
            className="flex-1 px-4 py-2.5 border border-gray-300 rounded-sm bg-white transition-all duration-200 focus:outline-none focus:ring-2 focus:ring-[#251D1C] focus:border-[#251D1C] resize-none disabled:opacity-50 disabled:cursor-not-allowed min-h-[44px] max-h-[120px] overflow-y-auto"
            aria-label="Message input"
          />
          {maxLength && (
            <div
              className={`text-xs mt-1 px-1 ${
                isNearLimit ? "text-[#F59E0B]" : "text-gray-400"
              }`}
            >
              {remainingChars} characters remaining
            </div>
          )}
        </div>
        <Button
          onClick={handleSend}
          disabled={disabled || !content.trim()}
          variant="primary"
          icon={<SendIcon />}
          iconPosition="right"
          aria-label="Send message"
        >
          Send
        </Button>
      </div>
    </div>
  );
};

