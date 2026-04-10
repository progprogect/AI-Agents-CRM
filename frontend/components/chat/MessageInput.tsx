/** Message input component with send icon, image attachment, and voice recording. */

import React, {
  useState,
  KeyboardEvent,
  useRef,
  useEffect,
  useCallback,
} from "react";
import { Button } from "@/components/shared/Button";
import { api, ApiError } from "@/lib/api";
import type { ChatSendPayload } from "@/lib/types/message";

interface MessageInputProps {
  onSend: (payload: ChatSendPayload) => void;
  disabled?: boolean;
  placeholder?: string;
  maxLength?: number;
  /** When the parent holds an attachment (e.g. admin composer), allow send with empty text. */
  allowEmpty?: boolean;
  /** Conversation ID — required for backend voice transcription. */
  conversationId?: string;
}

// ---------------------------------------------------------------------------
// Icons
// ---------------------------------------------------------------------------

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
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        d="M5.25 7.5A2.25 2.25 0 017.5 5.25h9a2.25 2.25 0 012.25 2.25v9a2.25 2.25 0 01-2.25 2.25h-9a2.25 2.25 0 01-2.25-2.25v-9z"
      />
    ) : (
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        d="M12 18.75a6 6 0 006-6v-1.5m-6 7.5a6 6 0 01-6-6v-1.5m6 7.5v3.75m-3.75 0h7.5M12 15.75a3 3 0 01-3-3V4.5a3 3 0 116 0v8.25a3 3 0 01-3 3z"
      />
    )}
  </svg>
);

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Pick the best supported MIME type for MediaRecorder (prefer ogg/opus for Whisper). */
function getBestMimeType(): string {
  const candidates = [
    "audio/ogg;codecs=opus",
    "audio/webm;codecs=opus",
    "audio/webm",
    "audio/mp4",
  ];
  for (const type of candidates) {
    if (typeof MediaRecorder !== "undefined" && MediaRecorder.isTypeSupported(type)) {
      return type;
    }
  }
  return "";
}

function mimeToExtension(mime: string): string {
  if (mime.includes("ogg")) return "ogg";
  if (mime.includes("mp4")) return "mp4";
  return "webm";
}

/** Format elapsed seconds as mm:ss */
function formatDuration(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return `${m}:${s.toString().padStart(2, "0")}`;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export const MessageInput: React.FC<MessageInputProps> = ({
  onSend,
  disabled = false,
  placeholder = "Type your message...",
  maxLength,
  allowEmpty = false,
  conversationId,
}) => {
  const [content, setContent] = useState("");
  const [pendingFile, setPendingFile] = useState<File | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);

  // Voice recording state
  const [isRecording, setIsRecording] = useState(false);
  const [isTranscribing, setIsTranscribing] = useState(false);
  const [recordingSeconds, setRecordingSeconds] = useState(0);
  const [voiceError, setVoiceError] = useState<string | null>(null);
  // true once we confirm MediaRecorder is available (SSR-safe)
  const [micSupported, setMicSupported] = useState(false);

  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const audioChunksRef = useRef<Blob[]>([]);
  const streamRef = useRef<MediaStream | null>(null);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Check MediaRecorder support after mount (SSR-safe)
  useEffect(() => {
    setMicSupported(typeof MediaRecorder !== "undefined" && !!navigator.mediaDevices?.getUserMedia);
  }, []);

  // Auto-resize textarea
  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
      textareaRef.current.style.height = `${textareaRef.current.scrollHeight}px`;
    }
  }, [content]);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      stopTimer();
      streamRef.current?.getTracks().forEach((t) => t.stop());
    };
  }, []);

  // ---------------------------------------------------------------------------
  // Image attachment
  // ---------------------------------------------------------------------------

  const clearAttachment = useCallback(() => {
    setPendingFile(null);
    setPreviewUrl((prev) => {
      if (prev) URL.revokeObjectURL(prev);
      return null;
    });
    if (fileInputRef.current) fileInputRef.current.value = "";
  }, []);

  useEffect(() => {
    return () => {
      if (previewUrl) URL.revokeObjectURL(previewUrl);
    };
  }, [previewUrl]);

  const onFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0];
    if (!f || !f.type.startsWith("image/")) return;
    setPreviewUrl((prev) => {
      if (prev) URL.revokeObjectURL(prev);
      return URL.createObjectURL(f);
    });
    setPendingFile(f);
  };

  // ---------------------------------------------------------------------------
  // Voice recording (MediaRecorder → backend STT)
  // ---------------------------------------------------------------------------

  function stopTimer() {
    if (timerRef.current) {
      clearInterval(timerRef.current);
      timerRef.current = null;
    }
  }

  const startRecording = useCallback(async () => {
    if (!conversationId) {
      setVoiceError("Голосовой ввод недоступен в этом режиме.");
      return;
    }
    setVoiceError(null);
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = stream;

      const mimeType = getBestMimeType();
      const options = mimeType ? { mimeType } : {};
      const recorder = new MediaRecorder(stream, options);
      audioChunksRef.current = [];

      recorder.ondataavailable = (e) => {
        if (e.data.size > 0) audioChunksRef.current.push(e.data);
      };

      recorder.onstop = async () => {
        stopTimer();
        setRecordingSeconds(0);
        stream.getTracks().forEach((t) => t.stop());
        streamRef.current = null;

        const blob = new Blob(audioChunksRef.current, {
          type: mimeType || "audio/webm",
        });
        const ext = mimeToExtension(mimeType);
        const filename = `voice.${ext}`;

        setIsTranscribing(true);
        try {
          const { transcript } = await api.transcribeVoice(conversationId, blob, filename);
          if (transcript) {
            setContent((prev) => (prev ? `${prev} ${transcript}` : transcript));
          } else {
            setVoiceError("Не удалось распознать речь. Попробуйте ещё раз.");
          }
        } catch (err) {
          const msg = err instanceof ApiError ? err.message : "Ошибка транскрипции.";
          setVoiceError(msg);
        } finally {
          setIsTranscribing(false);
        }
      };

      mediaRecorderRef.current = recorder;
      recorder.start(250); // collect chunks every 250ms
      setIsRecording(true);
      setRecordingSeconds(0);
      timerRef.current = setInterval(() => setRecordingSeconds((s) => s + 1), 1000);
    } catch {
      setVoiceError("Нет доступа к микрофону. Разрешите доступ в настройках браузера.");
    }
  }, [conversationId]);

  const stopRecording = useCallback(() => {
    mediaRecorderRef.current?.stop();
    setIsRecording(false);
  }, []);

  const handleMicClick = useCallback(() => {
    if (isRecording) stopRecording();
    else void startRecording();
  }, [isRecording, startRecording, stopRecording]);

  // ---------------------------------------------------------------------------
  // Send
  // ---------------------------------------------------------------------------

  const handleSend = () => {
    const canSend = !disabled && (content.trim() || pendingFile || allowEmpty);
    if (canSend) {
      onSend({ content, file: pendingFile });
      setContent("");
      clearAttachment();
      if (textareaRef.current) textareaRef.current.style.height = "auto";
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
    if (maxLength && value.length > maxLength) return;
    setContent(value);
  };

  const remainingChars = maxLength ? maxLength - content.length : null;
  const isNearLimit = maxLength && remainingChars !== null && remainingChars < 20;

  // ---------------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------------

  return (
    <div className="border-t border-[#251D1C]/20 p-4 bg-white">
      {/* Image preview */}
      {previewUrl && (
        <div className="mb-2 flex items-center gap-2 rounded-sm border border-gray-200 bg-gray-50 p-2">
          <img
            src={previewUrl}
            alt="Attachment preview"
            className="h-14 w-14 rounded object-cover"
          />
          <span className="text-xs text-gray-600 flex-1 truncate">{pendingFile?.name}</span>
          <button type="button" onClick={clearAttachment} className="text-sm text-red-600 hover:underline">
            Remove
          </button>
        </div>
      )}

      {/* Recording indicator */}
      {isRecording && (
        <div className="mb-2 flex items-center gap-2 rounded-sm bg-red-50 border border-red-200 px-3 py-1.5">
          <span className="h-2 w-2 rounded-full bg-red-500 animate-pulse" aria-hidden />
          <span className="text-xs font-medium text-red-600">
            Запись… {formatDuration(recordingSeconds)}
          </span>
          <span className="text-xs text-red-500 ml-auto">Нажмите стоп чтобы отправить</span>
        </div>
      )}

      {/* Transcribing indicator */}
      {isTranscribing && (
        <div className="mb-2 flex items-center gap-2 rounded-sm bg-blue-50 border border-blue-200 px-3 py-1.5">
          <span className="text-xs text-blue-600">Распознаю речь…</span>
        </div>
      )}

      {/* Error */}
      {voiceError && <p className="mb-1 text-xs text-red-500">{voiceError}</p>}

      <div className="flex gap-2 items-end">
        {/* Image attach */}
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
          disabled={disabled || isRecording || isTranscribing}
          className="shrink-0 p-2.5 rounded-sm border border-gray-300 text-gray-600 hover:bg-gray-50 disabled:opacity-50"
          aria-label="Attach image"
        >
          <AttachmentIcon />
        </button>

        {/* Mic button — shown only when MediaRecorder is available and conversationId given */}
        {micSupported && conversationId && (
          <button
            type="button"
            onClick={handleMicClick}
            disabled={disabled || isTranscribing}
            className={`shrink-0 p-2.5 rounded-sm border transition-colors disabled:opacity-50 ${
              isRecording
                ? "border-red-400 bg-red-50 text-red-500"
                : "border-gray-300 text-gray-600 hover:bg-gray-50"
            }`}
            aria-label={isRecording ? "Стоп" : "Голосовое сообщение"}
            title={isRecording ? "Остановить запись" : "Записать голосовое сообщение"}
          >
            <MicIcon active={isRecording} />
          </button>
        )}

        {/* Textarea */}
        <div className="flex-1 flex flex-col">
          <textarea
            ref={textareaRef}
            value={content}
            onChange={handleChange}
            onKeyPress={handleKeyPress}
            disabled={disabled || isRecording || isTranscribing}
            placeholder={isRecording ? "Говорите…" : isTranscribing ? "Распознаю…" : placeholder}
            rows={1}
            maxLength={maxLength}
            className="flex-1 px-4 py-2.5 border border-gray-300 rounded-sm bg-white transition-all duration-200 focus:outline-none focus:ring-2 focus:ring-[#251D1C] focus:border-[#251D1C] resize-none disabled:opacity-50 disabled:cursor-not-allowed min-h-[44px] max-h-[120px] overflow-y-auto"
            aria-label="Message input"
          />
          {maxLength && (
            <div className={`text-xs mt-1 px-1 ${isNearLimit ? "text-[#F59E0B]" : "text-gray-400"}`}>
              {remainingChars} characters remaining
            </div>
          )}
        </div>

        <Button
          onClick={handleSend}
          disabled={disabled || isRecording || isTranscribing || (!content.trim() && !pendingFile && !allowEmpty)}
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
