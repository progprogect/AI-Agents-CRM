/** Message input component with send icon and improved styling. */

import React, {
  useState,
  KeyboardEvent,
  useRef,
  useEffect,
  useCallback,
} from "react";
import { Button } from "@/components/shared/Button";
import type { ChatSendPayload } from "@/lib/types/message";

// Web Speech API type declarations (not in default TS lib)
declare global {
  interface Window {
    SpeechRecognition?: new () => SpeechRecognition;
    webkitSpeechRecognition?: new () => SpeechRecognition;
  }
}

/** Returns the browser SpeechRecognition constructor, or null if unsupported. */
function getSpeechRecognition(): (new () => SpeechRecognition) | null {
  if (typeof window === "undefined") return null;
  return window.SpeechRecognition ?? window.webkitSpeechRecognition ?? null;
}

interface MessageInputProps {
  onSend: (payload: ChatSendPayload) => void;
  disabled?: boolean;
  placeholder?: string;
  maxLength?: number;
  /** When the parent holds an attachment (e.g. admin composer), allow send with empty text. */
  allowEmpty?: boolean;
}

const AttachmentIcon = () => (
  <svg
    xmlns="http://www.w3.org/2000/svg"
    fill="none"
    viewBox="0 0 24 24"
    strokeWidth={1.5}
    stroke="currentColor"
    className="h-5 w-5"
    aria-hidden
  >
    <path
      strokeLinecap="round"
      strokeLinejoin="round"
      d="m18.375 12.739-7.693 7.693a4.5 4.5 0 0 1-6.364-6.364l10.94-10.94A3 3 0 1 1 19.5 7.372L8.552 18.32m.009-.01-.01.01m5.699-9.941-7.81 7.81a1.5 1.5 0 0 0 2.112 2.13"
    />
  </svg>
);

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

const MicIcon = ({ active }: { active: boolean }) => (
  <svg
    xmlns="http://www.w3.org/2000/svg"
    fill="none"
    viewBox="0 0 24 24"
    strokeWidth={1.5}
    stroke="currentColor"
    className="h-5 w-5"
    aria-hidden
  >
    {active ? (
      /* Stop / recording indicator */
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        d="M5.25 7.5A2.25 2.25 0 017.5 5.25h9a2.25 2.25 0 012.25 2.25v9a2.25 2.25 0 01-2.25 2.25h-9a2.25 2.25 0 01-2.25-2.25v-9z"
      />
    ) : (
      /* Microphone icon */
      <>
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          d="M12 18.75a6 6 0 006-6v-1.5m-6 7.5a6 6 0 01-6-6v-1.5m6 7.5v3.75m-3.75 0h7.5M12 15.75a3 3 0 01-3-3V4.5a3 3 0 116 0v8.25a3 3 0 01-3 3z"
        />
      </>
    )}
  </svg>
);

export const MessageInput: React.FC<MessageInputProps> = ({
  onSend,
  disabled = false,
  placeholder = "Type your message...",
  maxLength,
  allowEmpty = false,
}) => {
  const [content, setContent] = useState("");
  const [pendingFile, setPendingFile] = useState<File | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [isRecording, setIsRecording] = useState(false);
  const [voiceError, setVoiceError] = useState<string | null>(null);
  const recognitionRef = useRef<SpeechRecognition | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const speechSupported = getSpeechRecognition() !== null;

  const toggleRecording = useCallback(() => {
    const SpeechRecognitionClass = getSpeechRecognition();
    if (!SpeechRecognitionClass) return;

    if (isRecording) {
      recognitionRef.current?.stop();
      return;
    }

    setVoiceError(null);
    const recognition = new SpeechRecognitionClass();
    recognition.continuous = false;
    recognition.interimResults = false;
    recognition.lang = "ru-RU";

    recognition.onstart = () => setIsRecording(true);

    recognition.onresult = (event: SpeechRecognitionEvent) => {
      const transcript = event.results[0]?.[0]?.transcript ?? "";
      if (transcript) {
        setContent((prev) => (prev ? `${prev} ${transcript}` : transcript));
      }
    };

    recognition.onerror = (event: SpeechRecognitionErrorEvent) => {
      if (event.error !== "aborted") {
        setVoiceError("Не удалось распознать речь. Попробуйте ещё раз.");
      }
      setIsRecording(false);
    };

    recognition.onend = () => setIsRecording(false);

    recognitionRef.current = recognition;
    recognition.start();
  }, [isRecording]);

  // Cleanup recognition on unmount
  useEffect(() => {
    return () => {
      recognitionRef.current?.abort();
    };
  }, []);

  const clearAttachment = useCallback(() => {
    setPendingFile(null);
    setPreviewUrl((prev) => {
      if (prev) URL.revokeObjectURL(prev);
      return null;
    });
    if (fileInputRef.current) {
      fileInputRef.current.value = "";
    }
  }, []);

  useEffect(() => {
    return () => {
      if (previewUrl) URL.revokeObjectURL(previewUrl);
    };
  }, [previewUrl]);

  // Auto-resize textarea
  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
      textareaRef.current.style.height = `${textareaRef.current.scrollHeight}px`;
    }
  }, [content]);

  const onFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0];
    if (!f || !f.type.startsWith("image/")) {
      return;
    }
    setPreviewUrl((prev) => {
      if (prev) URL.revokeObjectURL(prev);
      return URL.createObjectURL(f);
    });
    setPendingFile(f);
  };

  const handleSend = () => {
    const canSend =
      !disabled &&
      (content.trim() || pendingFile || allowEmpty);
    if (canSend) {
      onSend({ content, file: pendingFile });
      setContent("");
      clearAttachment();
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
      {previewUrl && (
        <div className="mb-2 flex items-center gap-2 rounded-sm border border-gray-200 bg-gray-50 p-2">
          <img
            src={previewUrl}
            alt="Attachment preview"
            className="h-14 w-14 rounded object-cover"
          />
          <span className="text-xs text-gray-600 flex-1 truncate">
            {pendingFile?.name}
          </span>
          <button
            type="button"
            onClick={clearAttachment}
            className="text-sm text-red-600 hover:underline"
          >
            Remove
          </button>
        </div>
      )}
      {voiceError && (
        <p className="mb-1 text-xs text-red-500">{voiceError}</p>
      )}
      <div className="flex gap-2 items-end">
        <input
          ref={fileInputRef}
          type="file"
          accept="image/*"
          className="hidden"
          aria-hidden
          onChange={onFileChange}
        />
        <button
          type="button"
          onClick={() => fileInputRef.current?.click()}
          disabled={disabled}
          className="shrink-0 p-2.5 rounded-sm border border-gray-300 text-gray-600 hover:bg-gray-50 disabled:opacity-50"
          aria-label="Attach image"
        >
          <AttachmentIcon />
        </button>
        {speechSupported && (
          <button
            type="button"
            onClick={toggleRecording}
            disabled={disabled}
            className={`shrink-0 p-2.5 rounded-sm border transition-colors disabled:opacity-50 ${
              isRecording
                ? "border-red-400 bg-red-50 text-red-500 animate-pulse"
                : "border-gray-300 text-gray-600 hover:bg-gray-50"
            }`}
            aria-label={isRecording ? "Stop recording" : "Voice input"}
            title={isRecording ? "Запись… нажмите чтобы остановить" : "Голосовой ввод"}
          >
            <MicIcon active={isRecording} />
          </button>
        )}
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
          disabled={
            disabled ||
            (!content.trim() && !pendingFile && !allowEmpty)
          }
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

