/** Channel setup guide — Instagram, Telegram, WhatsApp. */

"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useParams } from "next/navigation";
import { api, ApiError } from "@/lib/api";
import { LoadingSpinner } from "@/components/shared/LoadingSpinner";
import type { ChannelBinding, ChannelConfig, ChannelType, CreateChannelBindingRequest } from "@/lib/types/channel";
import {
  CheckCircle2,
  Circle,
  Copy,
  Check,
  ExternalLink,
  ChevronDown,
  ChevronUp,
  RefreshCw,
  Trash2,
  ToggleLeft,
  ToggleRight,
  Settings,
  Eye,
  EyeOff,
} from "lucide-react";

// ── Helpers ───────────────────────────────────────────────────────────────────

function CopyButton({ value, label }: { value: string; label?: string }) {
  const [copied, setCopied] = useState(false);
  const handleCopy = async () => {
    if (!value) return;
    await navigator.clipboard.writeText(value);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };
  return (
    <button
      onClick={handleCopy}
      disabled={!value}
      className="flex items-center gap-1.5 px-2.5 py-1 text-xs font-medium rounded border transition-colors
        border-[#BEBAB7] text-[#443C3C] hover:border-[#251D1C] hover:text-[#251D1C]
        disabled:opacity-40 disabled:cursor-not-allowed"
      title={label ?? "Copy to clipboard"}
    >
      {copied ? <Check size={12} className="text-green-600" /> : <Copy size={12} />}
      {copied ? "Copied!" : "Copy"}
    </button>
  );
}

function CopyField({ value, masked }: { value: string; masked?: boolean }) {
  const [show, setShow] = useState(false);
  const display = masked && !show ? "•".repeat(Math.min(value.length, 24)) : value;
  return (
    <div className="flex items-center gap-2 mt-1.5">
      <code className="flex-1 bg-[#EEEAE7] border border-[#BEBAB7] rounded px-3 py-1.5 text-xs font-mono text-[#251D1C] truncate">
        {value ? display : <span className="text-[#9A9590]">Not configured</span>}
      </code>
      {masked && value && (
        <button
          onClick={() => setShow((s) => !s)}
          className="text-[#9A9590] hover:text-[#443C3C]"
          title={show ? "Hide" : "Show"}
        >
          {show ? <EyeOff size={14} /> : <Eye size={14} />}
        </button>
      )}
      {value && <CopyButton value={value} />}
    </div>
  );
}

function StatusBadge({ binding }: { binding?: ChannelBinding }) {
  if (!binding) {
    return (
      <span className="flex items-center gap-1.5 text-xs text-[#9A9590]">
        <Circle size={10} /> Not connected
      </span>
    );
  }
  if (!binding.is_active) {
    return (
      <span className="flex items-center gap-1.5 text-xs text-amber-600">
        <Circle size={10} className="fill-amber-400" /> Inactive
      </span>
    );
  }
  if (!binding.is_verified) {
    return (
      <span className="flex items-center gap-1.5 text-xs text-amber-600">
        <Circle size={10} className="fill-amber-400" /> Connected (unverified)
      </span>
    );
  }
  return (
    <span className="flex items-center gap-1.5 text-xs text-green-600 font-medium">
      <CheckCircle2 size={12} className="fill-green-100" /> Connected
    </span>
  );
}

function Step({
  n,
  children,
}: {
  n: number;
  children: React.ReactNode;
}) {
  return (
    <div className="flex gap-3">
      <span className="flex-shrink-0 w-6 h-6 rounded-full bg-[#EEEAE7] text-[#443C3C] text-xs font-bold flex items-center justify-center mt-0.5">
        {n}
      </span>
      <div className="flex-1 text-sm text-[#443C3C] leading-relaxed">{children}</div>
    </div>
  );
}

function ExtLink({ href, children }: { href: string; children: React.ReactNode }) {
  return (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      className="inline-flex items-center gap-1 text-[#251D1C] font-medium underline underline-offset-2 hover:opacity-70"
    >
      {children} <ExternalLink size={11} />
    </a>
  );
}

// ── WhatsApp provider-specific form fields ────────────────────────────────────

type WaProvider = "meta" | "twilio";

function WhatsAppFormFields({
  form,
  set,
  setMeta,
  firstInput,
  inputClass,
  labelClass,
}: {
  form: CreateChannelBindingRequest;
  set: (field: string, value: string) => void;
  setMeta: (key: string, value: string) => void;
  firstInput: React.RefObject<HTMLInputElement>;
  inputClass: string;
  labelClass: string;
}) {
  const provider: WaProvider = (form.metadata?.provider as WaProvider) || "meta";

  const handleProviderChange = (p: WaProvider) => {
    set("channel_account_id", "");
    set("access_token", "");
    set("channel_username", "");
    setMeta("provider", p);
    setMeta("account_sid", "");
  };

  return (
    <>
      {/* Provider selector */}
      <div>
        <label className={labelClass}>Provider</label>
        <div className="flex gap-2 mt-1">
          {(["meta", "twilio"] as WaProvider[]).map((p) => (
            <button
              key={p}
              type="button"
              onClick={() => handleProviderChange(p)}
              className={`flex-1 py-1.5 text-xs font-medium rounded border transition-colors ${
                provider === p
                  ? "bg-[#251D1C] text-white border-[#251D1C]"
                  : "bg-white text-[#443C3C] border-[#BEBAB7] hover:border-[#251D1C]"
              }`}
            >
              {p === "meta" ? "Meta (Direct)" : "Twilio"}
            </button>
          ))}
        </div>
        <p className="text-xs text-[#9A9590] mt-1">
          {provider === "meta"
            ? "Connect directly via Meta WhatsApp Cloud API — requires a Meta Business Account."
            : "Connect via Twilio — simpler setup, no Meta Developer account required for sandbox testing."}
        </p>
      </div>

      {provider === "meta" && (
        <>
          <div>
            <label className={labelClass}>Phone Number ID *</label>
            <input
              ref={firstInput}
              className={inputClass}
              value={form.channel_account_id}
              onChange={(e) => set("channel_account_id", e.target.value)}
              placeholder="123456789012345"
              required
            />
            <p className="text-xs text-[#9A9590] mt-1">
              From Meta App → WhatsApp → Getting Started
            </p>
          </div>
          <div>
            <label className={labelClass}>System User Access Token *</label>
            <input
              className={inputClass}
              type="password"
              value={form.access_token}
              onChange={(e) => set("access_token", e.target.value)}
              placeholder="EAAx..."
              required
            />
            <p className="text-xs text-[#9A9590] mt-1">
              Use a permanent System User token from Meta Business Manager for production.
            </p>
          </div>
          <div>
            <label className={labelClass}>Display Name (optional)</label>
            <input
              className={inputClass}
              value={form.channel_username ?? ""}
              onChange={(e) => set("channel_username", e.target.value)}
              placeholder="+1 555 000 0000"
            />
          </div>
        </>
      )}

      {provider === "twilio" && (
        <>
          <div>
            <label className={labelClass}>WhatsApp From Number *</label>
            <input
              ref={firstInput}
              className={inputClass}
              value={form.channel_account_id}
              onChange={(e) => set("channel_account_id", e.target.value)}
              placeholder="+14155238886"
              required
            />
            <p className="text-xs text-[#9A9590] mt-1">
              Your Twilio WhatsApp-enabled number in E.164 format.
              For sandbox: <code className="bg-[#EEEAE7] px-1 rounded">+14155238886</code>
            </p>
          </div>
          <div>
            <label className={labelClass}>Account SID *</label>
            <input
              className={inputClass}
              value={(form.metadata?.account_sid as string) ?? ""}
              onChange={(e) => setMeta("account_sid", e.target.value)}
              placeholder="ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
              required
            />
            <p className="text-xs text-[#9A9590] mt-1">
              From{" "}
              <a
                href="https://console.twilio.com"
                target="_blank"
                rel="noopener noreferrer"
                className="underline"
              >
                Twilio Console
              </a>{" "}
              → main dashboard
            </p>
          </div>
          <div>
            <label className={labelClass}>Auth Token *</label>
            <input
              className={inputClass}
              type="password"
              value={form.access_token}
              onChange={(e) => set("access_token", e.target.value)}
              placeholder="••••••••••••••••••••••••••••••••"
              required
            />
            <p className="text-xs text-[#9A9590] mt-1">
              From Twilio Console → main dashboard (below Account SID)
            </p>
          </div>
          <div>
            <label className={labelClass}>Display Name (optional)</label>
            <input
              className={inputClass}
              value={form.channel_username ?? ""}
              onChange={(e) => set("channel_username", e.target.value)}
              placeholder="My Business"
            />
          </div>
        </>
      )}
    </>
  );
}

// ── Inline connection form ────────────────────────────────────────────────────

interface ConnectFormProps {
  agentId: string;
  channelType: ChannelType;
  onSuccess: (binding: ChannelBinding) => void;
  onCancel: () => void;
}

function ConnectForm({ agentId, channelType, onSuccess, onCancel }: ConnectFormProps) {
  const [form, setForm] = useState<CreateChannelBindingRequest>({
    channel_type: channelType,
    channel_account_id: "",
    access_token: "",
    channel_username: "",
    metadata: {},
  });
  const [submitting, setSubmitting] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const firstInput = useRef<HTMLInputElement>(null);

  useEffect(() => {
    firstInput.current?.focus();
  }, []);

  const set = (field: string, value: string) =>
    setForm((prev) => ({ ...prev, [field]: value }));
  const setMeta = (key: string, value: string) =>
    setForm((prev) => ({ ...prev, metadata: { ...prev.metadata, [key]: value } }));

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setErr(null);
    setSubmitting(true);
    try {
      const binding = await api.createChannelBinding(agentId, form);
      // Auto-verify Telegram (sets webhook automatically) and Twilio (validates credentials)
      const isTwilio =
        channelType === "whatsapp" && form.metadata?.provider === "twilio";
      if ((channelType === "telegram" || isTwilio) && binding.binding_id) {
        await api.verifyChannelBinding(binding.binding_id).catch(() => {});
      }
      onSuccess(binding);
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : "Failed to connect channel");
    } finally {
      setSubmitting(false);
    }
  };

  const inputClass =
    "w-full text-sm px-3 py-2 border border-[#BEBAB7] rounded outline-none focus:border-[#251D1C] bg-white placeholder:text-[#BEBAB7]";
  const labelClass = "block text-xs font-medium text-[#443C3C] mb-1";

  return (
    <form
      onSubmit={handleSubmit}
      className="mt-4 p-4 bg-[#FAFAFA] border border-[#BEBAB7] rounded-md space-y-3"
    >
      {err && (
        <div className="text-xs text-red-600 bg-red-50 border border-red-200 rounded px-3 py-2">
          {err}
        </div>
      )}

      {channelType === "instagram" && (
        <>
          <div>
            <label className={labelClass}>Instagram Business Account ID *</label>
            <input
              ref={firstInput}
              className={inputClass}
              value={form.channel_account_id}
              onChange={(e) => set("channel_account_id", e.target.value)}
              placeholder="17841458318357324"
              required
            />
            <p className="text-xs text-[#9A9590] mt-1">
              Found in Meta Business Suite → Settings → Instagram Accounts
            </p>
          </div>
          <div>
            <label className={labelClass}>Page Access Token *</label>
            <input
              className={inputClass}
              type="password"
              value={form.access_token}
              onChange={(e) => set("access_token", e.target.value)}
              placeholder="IGAAXjRiKjwKFBZA..."
              required
            />
          </div>
          <div>
            <label className={labelClass}>Instagram Username (optional)</label>
            <input
              className={inputClass}
              value={form.channel_username ?? ""}
              onChange={(e) => set("channel_username", e.target.value)}
              placeholder="@yourbusiness"
            />
          </div>
          <div>
            <label className={labelClass}>App ID (optional)</label>
            <input
              className={inputClass}
              value={(form.metadata?.app_id as string) ?? ""}
              onChange={(e) => setMeta("app_id", e.target.value)}
              placeholder="1657265251926177"
            />
          </div>
        </>
      )}

      {channelType === "telegram" && (
        <>
          <div>
            <label className={labelClass}>Bot Token *</label>
            <input
              ref={firstInput}
              className={inputClass}
              type="password"
              value={form.access_token}
              onChange={(e) => {
                const token = e.target.value;
                set("access_token", token);
                // Auto-extract Bot ID from token (format: "123456789:ABC...")
                const numericPart = token.split(":")[0];
                if (numericPart && /^\d+$/.test(numericPart)) {
                  set("channel_account_id", numericPart);
                }
              }}
              placeholder="123456789:ABCdefGHIjklMNOpqrsTUVwxyz"
              required
            />
            <p className="text-xs text-[#9A9590] mt-1">
              Bot ID is extracted from the token automatically.
            </p>
          </div>
          <div>
            <label className={labelClass}>Bot Username (optional)</label>
            <input
              className={inputClass}
              value={form.channel_username ?? ""}
              onChange={(e) => set("channel_username", e.target.value)}
              placeholder="@my_bot"
            />
          </div>
          <p className="text-xs text-[#9A9590]">
            The webhook URL is set automatically after connecting.
          </p>
        </>
      )}

      {channelType === "whatsapp" && (
        <WhatsAppFormFields
          form={form}
          set={set}
          setMeta={setMeta}
          firstInput={firstInput}
          inputClass={inputClass}
          labelClass={labelClass}
        />
      )}

      <div className="flex gap-2 pt-1">
        <button
          type="submit"
          disabled={submitting}
          className="px-4 py-2 text-sm font-medium text-white bg-[#251D1C] rounded hover:bg-[#443C3C] disabled:opacity-50 transition-colors"
        >
          {submitting ? "Connecting..." : "Connect"}
        </button>
        <button
          type="button"
          onClick={onCancel}
          className="px-4 py-2 text-sm text-[#9A9590] hover:text-[#443C3C]"
        >
          Cancel
        </button>
      </div>
    </form>
  );
}

// ── Channel app settings form (Instagram / WhatsApp) ─────────────────────────

interface ChannelSettingsFormProps {
  title: string;
  currentVerifyToken: string;
  appSecretConfigured: boolean;
  verifyTokenHint?: string;
  onSave: (data: { verify_token?: string; app_secret?: string }) => Promise<void>;
}

function ChannelSettingsForm({
  title,
  currentVerifyToken,
  appSecretConfigured,
  verifyTokenHint,
  onSave,
}: ChannelSettingsFormProps) {
  const [verifyToken, setVerifyToken] = useState(currentVerifyToken);
  const [appSecret, setAppSecret] = useState("");
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    setErr(null);
    setSaving(true);
    try {
      const payload: { verify_token?: string; app_secret?: string } = {};
      if (verifyToken.trim()) payload.verify_token = verifyToken.trim();
      if (appSecret.trim()) payload.app_secret = appSecret.trim();
      await onSave(payload);
      setSaved(true);
      setAppSecret("");
      setTimeout(() => setSaved(false), 3000);
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : "Failed to save settings");
    } finally {
      setSaving(false);
    }
  };

  const inputClass =
    "w-full text-sm px-3 py-2 border border-[#BEBAB7] rounded outline-none focus:border-[#251D1C] bg-white placeholder:text-[#BEBAB7]";
  const labelClass = "block text-xs font-medium text-[#443C3C] mb-1";

  return (
    <form onSubmit={handleSave} className="p-4 bg-[#FAFAFA] border border-[#BEBAB7] rounded-md space-y-3">
      <div className="text-xs font-semibold text-[#443C3C] flex items-center gap-1.5">
        <Settings size={12} /> {title} App Settings
      </div>
      {err && (
        <div className="text-xs text-red-600 bg-red-50 border border-red-200 rounded px-3 py-2">{err}</div>
      )}
      <div>
        <label className={labelClass}>Verify Token</label>
        <input
          className={inputClass}
          value={verifyToken}
          onChange={(e) => setVerifyToken(e.target.value)}
          placeholder={verifyTokenHint ?? "Enter a custom string of your choice"}
        />
        <p className="text-xs text-[#9A9590] mt-1">
          Paste this exact value in the Meta Console when configuring the webhook.
        </p>
      </div>
      <div>
        <label className={labelClass}>App Secret <span className="font-normal text-[#9A9590]">(optional)</span></label>
        <input
          className={inputClass}
          type="password"
          value={appSecret}
          onChange={(e) => setAppSecret(e.target.value)}
          placeholder={
            appSecretConfigured
              ? "Already set — enter a new value to update"
              : "From Meta App → Settings → Basic"
          }
        />
        <p className="text-xs text-[#9A9590] mt-1">
          Enables signature verification of incoming webhook requests. Recommended for production.
        </p>
      </div>
      <button
        type="submit"
        disabled={saving}
        className="px-4 py-2 text-sm font-medium text-white bg-[#251D1C] rounded hover:bg-[#443C3C] disabled:opacity-50 transition-colors"
      >
        {saving ? "Saving..." : saved ? "Saved!" : "Save Settings"}
      </button>
    </form>
  );
}

// ── Connected binding row ─────────────────────────────────────────────────────

function BindingRow({
  binding,
  onToggle,
  onDelete,
  onVerify,
}: {
  binding: ChannelBinding;
  onToggle: () => void;
  onDelete: () => void;
  onVerify: () => void;
}) {
  return (
    <div className="flex items-center gap-3 p-3 bg-white border border-[#BEBAB7] rounded-md text-sm">
      <div className="flex-1 min-w-0">
        <div className="font-medium text-[#251D1C] truncate flex items-center gap-2">
          {binding.channel_username || binding.channel_account_id}
          {binding.channel_type === "whatsapp" && binding.metadata?.provider === "twilio" && (
            <span className="text-[10px] font-medium bg-[#EEEAE7] text-[#443C3C] px-1.5 py-0.5 rounded">
              Twilio
            </span>
          )}
        </div>
        <div className="text-xs text-[#9A9590]">ID: {binding.channel_account_id}</div>
      </div>
      <StatusBadge binding={binding} />
      <div className="flex items-center gap-1.5">
        {!binding.is_verified && (
          <button
            onClick={onVerify}
            className="text-xs text-blue-600 hover:text-blue-800 px-2 py-1 rounded border border-blue-200 hover:border-blue-400"
          >
            Verify
          </button>
        )}
        <button
          onClick={onToggle}
          className="text-[#9A9590] hover:text-[#443C3C]"
          title={binding.is_active ? "Deactivate" : "Activate"}
        >
          {binding.is_active ? <ToggleRight size={18} className="text-green-500" /> : <ToggleLeft size={18} />}
        </button>
        <button
          onClick={onDelete}
          className="text-[#9A9590] hover:text-red-500"
          title="Remove connection"
        >
          <Trash2 size={14} />
        </button>
      </div>
    </div>
  );
}

// ── Channel card ──────────────────────────────────────────────────────────────

interface ChannelCardProps {
  title: string;
  icon: string;
  bindings: ChannelBinding[];
  config: ChannelConfig | null;
  agentId: string;
  channelType: ChannelType;
  onBindingsChange: () => void;
  guide: React.ReactNode;
  settingsForm?: React.ReactNode;
}

function ChannelCard({
  title,
  icon,
  bindings,
  config,
  agentId,
  channelType,
  onBindingsChange,
  guide,
  settingsForm,
}: ChannelCardProps) {
  const [formOpen, setFormOpen] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [guideOpen, setGuideOpen] = useState(bindings.length === 0);
  const [busyId, setBusyId] = useState<string | null>(null);

  const activeBinding = bindings.find((b) => b.is_active);

  const handleDelete = async (bindingId: string) => {
    if (!confirm("Remove this connection?")) return;
    setBusyId(bindingId);
    try {
      await api.deleteChannelBinding(bindingId);
      onBindingsChange();
    } catch {}
    setBusyId(null);
  };

  const handleToggle = async (binding: ChannelBinding) => {
    setBusyId(binding.binding_id);
    try {
      await api.updateChannelBinding(binding.binding_id, { is_active: !binding.is_active });
      onBindingsChange();
    } catch {}
    setBusyId(null);
  };

  const handleVerify = async (bindingId: string) => {
    setBusyId(bindingId);
    try {
      await api.verifyChannelBinding(bindingId);
      onBindingsChange();
    } catch {}
    setBusyId(null);
  };

  return (
    <div className="bg-white border border-[#BEBAB7] rounded-lg overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between px-5 py-4 border-b border-[#BEBAB7]">
        <div className="flex items-center gap-3">
          <span className="text-xl">{icon}</span>
          <span className="font-semibold text-[#251D1C] text-base">{title}</span>
          {busyId && <LoadingSpinner size="sm" />}
        </div>
        <div className="flex items-center gap-3">
          <StatusBadge binding={activeBinding} />
          {settingsForm && (
            <button
              onClick={() => setSettingsOpen((o) => !o)}
              className={`p-1 transition-colors ${settingsOpen ? "text-[#251D1C]" : "text-[#9A9590] hover:text-[#443C3C]"}`}
              title="App Settings"
            >
              <Settings size={16} />
            </button>
          )}
        </div>
      </div>

      {/* App settings panel */}
      {settingsForm && settingsOpen && (
        <div className="px-5 py-4 border-b border-[#BEBAB7] bg-[#FAFAFA]">
          {settingsForm}
        </div>
      )}

      {/* Active connections */}
      {bindings.length > 0 && (
        <div className="px-5 py-3 space-y-2 border-b border-[#BEBAB7]">
          {bindings.map((b) => (
            <BindingRow
              key={b.binding_id}
              binding={b}
              onToggle={() => handleToggle(b)}
              onDelete={() => handleDelete(b.binding_id)}
              onVerify={() => handleVerify(b.binding_id)}
            />
          ))}
        </div>
      )}

      {/* Guide toggle */}
      <button
        onClick={() => setGuideOpen((o) => !o)}
        className="w-full flex items-center justify-between px-5 py-3 text-sm text-[#443C3C] hover:bg-[#FAFAFA] transition-colors"
      >
        <span className="font-medium">Setup Guide</span>
        {guideOpen ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
      </button>

      {guideOpen && (
        <div className="px-5 pb-5 space-y-4">
          {guide}

          {/* Connect form toggle */}
          {!formOpen ? (
            <button
              onClick={() => setFormOpen(true)}
              className="flex items-center gap-2 px-4 py-2 text-sm font-medium bg-[#251D1C] text-white rounded hover:bg-[#443C3C] transition-colors"
            >
              {bindings.length > 0 ? `Add another ${title} account` : `Connect ${title}`}
            </button>
          ) : (
            <ConnectForm
              agentId={agentId}
              channelType={channelType}
              onSuccess={() => {
                setFormOpen(false);
                onBindingsChange();
              }}
              onCancel={() => setFormOpen(false)}
            />
          )}
        </div>
      )}
    </div>
  );
}

// ── Inline token setup ────────────────────────────────────────────────────────

function InlineTokenSetup({
  channel,
  onSave,
}: {
  channel: "instagram" | "whatsapp";
  onSave: (token: string) => Promise<void>;
}) {
  const [value, setValue] = useState("");
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  const handleSave = async () => {
    const trimmed = value.trim();
    if (!trimmed) return;
    setSaving(true);
    try {
      await onSave(trimmed);
      setSaved(true);
      setTimeout(() => setSaved(false), 3000);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="mt-2 p-3 bg-[#EEEAE7]/50 border border-[#BEBAB7] rounded-md space-y-2">
      <p className="text-xs text-[#443C3C]">
        Create a <strong>Verify Token</strong> — choose any password-like phrase
        (you'll paste it in Meta Console in the next step):
      </p>
      <div className="flex gap-2">
        <input
          className="flex-1 text-sm px-2.5 py-1.5 border border-[#BEBAB7] rounded outline-none focus:border-[#251D1C] bg-white"
          value={value}
          onChange={(e) => setValue(e.target.value)}
          placeholder={`e.g. my-${channel}-secret-2024`}
          onKeyDown={(e) => e.key === "Enter" && handleSave()}
        />
        <button
          onClick={handleSave}
          disabled={!value.trim() || saving}
          className="px-3 py-1.5 text-sm font-medium text-white bg-[#251D1C] rounded hover:bg-[#443C3C] disabled:opacity-50 transition-colors"
        >
          {saving ? "Saving..." : saved ? "Saved ✓" : "Save"}
        </button>
      </div>
    </div>
  );
}

// ── WhatsApp guide (Meta + Twilio tabs) ──────────────────────────────────────

function WhatsAppGuide({
  waWebhookUrl,
  twilioWebhookUrl,
  config,
  setConfig,
}: {
  waWebhookUrl: string;
  twilioWebhookUrl: string;
  config: ChannelConfig | null;
  setConfig: (c: ChannelConfig) => void;
}) {
  const [tab, setTab] = useState<"meta" | "twilio">("meta");

  const tabClass = (active: boolean) =>
    `px-4 py-1.5 text-xs font-medium rounded-t border-b-2 transition-colors ${
      active
        ? "border-[#251D1C] text-[#251D1C]"
        : "border-transparent text-[#9A9590] hover:text-[#443C3C]"
    }`;

  return (
    <div className="space-y-4">
      {/* Tab switcher */}
      <div className="flex gap-1 border-b border-[#BEBAB7]">
        <button className={tabClass(tab === "meta")} onClick={() => setTab("meta")}>
          Meta (Direct)
        </button>
        <button className={tabClass(tab === "twilio")} onClick={() => setTab("twilio")}>
          Via Twilio
        </button>
      </div>

      {/* ── Meta guide ── */}
      {tab === "meta" && (
        <div className="space-y-4">
          <div className="text-xs text-[#9A9590] bg-[#EEEAE7]/60 rounded p-3 space-y-1">
            <div className="font-semibold text-[#443C3C] mb-1.5">What you'll need</div>
            <div>• A <strong>Meta Business Account</strong> (business.facebook.com)</div>
            <div>• A <strong>WhatsApp Business phone number</strong> approved by Meta</div>
          </div>

          <p className="text-xs text-[#9A9590]">
            Direct integration via Meta WhatsApp Cloud API. No third-party service — messages go straight from Meta to your AI.
          </p>

          <div className="space-y-3">
            <Step n={1}>
              If you don't have a Meta Business Account yet, create one at{" "}
              <ExtLink href="https://business.facebook.com">business.facebook.com</ExtLink>.
            </Step>

            <Step n={2}>
              Go to{" "}
              <ExtLink href="https://developers.facebook.com/apps">Meta Developers</ExtLink>,
              create a new app (type: <strong>Business</strong>), and add the{" "}
              <strong>WhatsApp</strong> product.
            </Step>

            <Step n={3}>
              <div className="font-medium">Configure the webhook.</div>
              <div className="text-xs text-[#9A9590] mt-0.5 mb-2">
                Go to <strong>WhatsApp → Configuration → Webhooks</strong> and enter:
              </div>

              <div className="space-y-1 mb-3">
                <div className="text-xs font-medium text-[#443C3C]">1. Callback URL</div>
                {waWebhookUrl ? (
                  <CopyField value={waWebhookUrl} />
                ) : (
                  <div className="text-xs bg-amber-50 border border-amber-200 rounded px-3 py-2">
                    <div className="font-medium text-amber-800">APP_URL not configured</div>
                    <div className="text-amber-700 mt-1">
                      Add <code className="bg-amber-100 px-1 rounded">APP_URL</code> to your Railway Variables and reload.
                    </div>
                  </div>
                )}
              </div>

              <div className="space-y-1">
                <div className="text-xs font-medium text-[#443C3C]">2. Verify Token</div>
                {config?.whatsapp_verify_token ? (
                  <>
                    <CopyField value={config.whatsapp_verify_token} masked />
                    <div className="text-xs text-[#9A9590]">Paste this into the Verify Token field in Meta Console.</div>
                  </>
                ) : (
                  <InlineTokenSetup
                    channel="whatsapp"
                    onSave={async (token) => {
                      await api.updateWhatsAppSettings({ verify_token: token });
                      const updated = await api.getChannelConfig();
                      setConfig(updated);
                    }}
                  />
                )}
              </div>

              <div className="text-xs text-[#9A9590] mt-3 bg-[#EEEAE7]/60 rounded px-3 py-2">
                After saving in Meta Console, subscribe to the <strong>messages</strong> field in the webhook section.
              </div>
            </Step>

            <Step n={4}>
              In your Meta App go to <strong>WhatsApp → Getting Started</strong>:
              <ol className="text-sm text-[#443C3C] space-y-1 list-decimal list-inside ml-1 mt-1.5">
                <li>Copy the <strong>Phone Number ID</strong></li>
                <li>
                  For production create a permanent <strong>System User Access Token</strong> via{" "}
                  <ExtLink href="https://business.facebook.com/settings/system-users">
                    Meta Business Manager → System Users
                  </ExtLink>
                  {" "}with scopes <code className="bg-[#EEEAE7] px-1 rounded text-xs">whatsapp_business_messaging</code> and <code className="bg-[#EEEAE7] px-1 rounded text-xs">whatsapp_business_management</code>.
                </li>
              </ol>
            </Step>

            <Step n={5}>
              Select <strong>Meta (Direct)</strong> in the form below, enter Phone Number ID and Access Token, then click <strong>Connect</strong>.
            </Step>
          </div>
        </div>
      )}

      {/* ── Twilio guide ── */}
      {tab === "twilio" && (
        <div className="space-y-4">
          <div className="text-xs text-[#9A9590] bg-[#EEEAE7]/60 rounded p-3 space-y-1">
            <div className="font-semibold text-[#443C3C] mb-1.5">What you'll need</div>
            <div>• A <ExtLink href="https://twilio.com">Twilio account</ExtLink> (free tier works for sandbox)</div>
          </div>

          <p className="text-xs text-[#9A9590]">
            Twilio acts as a bridge to WhatsApp. Easier to set up for testing — no Meta Business verification needed for the sandbox.
          </p>

          <div className="space-y-3">
            <Step n={1}>
              Sign up or log in at{" "}
              <ExtLink href="https://console.twilio.com">console.twilio.com</ExtLink>.
              On the dashboard you'll see your <strong>Account SID</strong> and <strong>Auth Token</strong> — copy both.
            </Step>

            <Step n={2}>
              <div className="font-medium">For testing (Sandbox):</div>
              <ol className="text-sm text-[#443C3C] space-y-1 list-decimal list-inside ml-1 mt-1">
                <li>Go to <strong>Messaging → Try it out → Send a WhatsApp message</strong></li>
                <li>Follow the instructions to join the sandbox from your phone</li>
                <li>Under <strong>Sandbox settings</strong>, paste the webhook URL below into the "When a message comes in" field</li>
              </ol>
              <div className="mt-2">
                <div className="text-xs font-medium text-[#443C3C] mb-1">Twilio Webhook URL</div>
                {twilioWebhookUrl ? (
                  <CopyField value={twilioWebhookUrl} />
                ) : (
                  <div className="text-xs bg-amber-50 border border-amber-200 rounded px-3 py-2">
                    <span className="font-medium text-amber-800">APP_URL not configured</span>
                    <span className="text-amber-700"> — add it to Railway Variables and reload.</span>
                  </div>
                )}
              </div>
              <div className="text-xs text-[#9A9590] mt-1.5">
                Sandbox From number: <code className="bg-[#EEEAE7] px-1 rounded">+14155238886</code>
              </div>
            </Step>

            <Step n={3}>
              <div className="font-medium">For production:</div>
              <ol className="text-sm text-[#443C3C] space-y-1 list-decimal list-inside ml-1 mt-1">
                <li>Go to <strong>Messaging → Senders → WhatsApp Senders</strong></li>
                <li>Add and verify your business phone number</li>
                <li>On the sender page set the webhook URL to the address shown above</li>
              </ol>
            </Step>

            <Step n={4}>
              Select <strong>Twilio</strong> in the form below, enter Account SID, Auth Token, and the WhatsApp From Number, then click <strong>Connect</strong>.
              The credentials are verified automatically.
            </Step>
          </div>
        </div>
      )}
    </div>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────

export default function AgentChannelsPage() {
  const params = useParams();
  const agentId = params.agentId as string;

  const [bindings, setBindings] = useState<ChannelBinding[]>([]);
  const [config, setConfig] = useState<ChannelConfig | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Derive the public base URL: use config value if available,
  // otherwise fall back to window.location.origin (works on same-domain Railway deployments)
  const appBase =
    config?.app_url ||
    (typeof window !== "undefined" ? window.location.origin : "");

  // Webhook URLs — always available even if config endpoint fails
  const igWebhookUrl =
    config?.instagram_webhook_url ||
    (appBase ? `${appBase}/api/v1/instagram/webhook` : "");
  const waWebhookUrl =
    config?.whatsapp_webhook_url ||
    (appBase ? `${appBase}/api/v1/whatsapp/webhook` : "");

  const load = useCallback(async () => {
    try {
      setError(null);
      const [bindingsData, configData] = await Promise.all([
        api.listChannelBindings(agentId, undefined, false),
        api.getChannelConfig().catch(() => null),
      ]);
      setBindings(bindingsData);
      setConfig(configData);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Failed to load channel data");
    } finally {
      setLoading(false);
    }
  }, [agentId]);

  useEffect(() => {
    load();
  }, [load]);

  const byType = (type: ChannelType) =>
    bindings.filter((b) => b.channel_type === type);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <LoadingSpinner size="lg" />
      </div>
    );
  }

  // ── Instagram guide ─────────────────────────────────────────────────────────

  const instagramGuide = (
    <div className="space-y-4">
      {/* What you'll need */}
      <div className="text-xs text-[#9A9590] bg-[#EEEAE7]/60 rounded p-3 space-y-1">
        <div className="font-semibold text-[#443C3C] mb-1.5">What you'll need</div>
        <div>• A <strong>Facebook account</strong> with developer access</div>
        <div>• A <strong>Facebook Business Page</strong> connected to your Instagram</div>
        <div>• An <strong>Instagram Professional or Business account</strong></div>
      </div>

      {/* Quick intro */}
      <p className="text-xs text-[#9A9590]">
        This setup tells Instagram to send all incoming messages to this AI assistant.
        It takes about 10–15 minutes and is a one-time process.
      </p>

      <div className="space-y-3">
        <Step n={1}>
          Go to{" "}
          <ExtLink href="https://developers.facebook.com/apps">
            Meta Developers
          </ExtLink>{" "}
          and create a new app. When asked for the type, choose <strong>Business</strong>.
          <div className="text-xs text-[#9A9590] mt-1">
            You need a Facebook account to log in. If you already have a Meta app, you can use it.
          </div>
        </Step>

        <Step n={2}>
          Inside your app, find the <strong>Instagram</strong> product in the left menu and add it.
          Then go to <em>Instagram → Webhooks</em> and click <strong>Subscribe to messages</strong>.
        </Step>

        <Step n={3}>
          <div className="font-medium">Connect this system to your Instagram.</div>
          <div className="text-xs text-[#9A9590] mt-0.5 mb-2">
            Meta will ask for two values. Copy them from here and paste into Meta Console:
          </div>

          {/* Callback URL */}
          <div className="space-y-1 mb-3">
            <div className="text-xs font-medium text-[#443C3C]">
              1. Callback URL{" "}
              <span className="font-normal text-[#9A9590]">— your system's address</span>
            </div>
            {igWebhookUrl ? (
              <CopyField value={igWebhookUrl} />
            ) : (
              <div className="text-xs bg-amber-50 border border-amber-200 rounded px-3 py-2 space-y-1.5">
                <div className="font-medium text-amber-800">Address not configured yet</div>
                <div className="text-amber-700">
                  To get this address, add <code className="bg-amber-100 px-1 rounded">APP_URL</code> to
                  your Railway project:
                </div>
                <ol className="text-amber-700 space-y-0.5 list-decimal list-inside ml-1">
                  <li>Open <ExtLink href="https://railway.app/dashboard">Railway Dashboard</ExtLink></li>
                  <li>Select your project → click your service</li>
                  <li>Go to <strong>Settings → Domains</strong> — copy the URL shown there</li>
                  <li>Go to <strong>Variables</strong> → Add: <code className="bg-amber-100 px-1 rounded">APP_URL = https://your-url.up.railway.app</code></li>
                  <li>Save and come back here — the address will appear automatically</li>
                </ol>
              </div>
            )}
          </div>

          {/* Verify Token */}
          <div className="space-y-1">
            <div className="text-xs font-medium text-[#443C3C]">
              2. Verify Token{" "}
              <span className="font-normal text-[#9A9590]">— a secret password you choose</span>
            </div>
            {config?.instagram_verify_token ? (
              <>
                <CopyField value={config.instagram_verify_token} masked />
                <div className="text-xs text-[#9A9590]">
                  Use this same value in the Meta Console "Verify Token" field.
                </div>
              </>
            ) : (
              <InlineTokenSetup
                channel="instagram"
                onSave={async (token) => {
                  await api.updateInstagramSettings({ verify_token: token });
                  const updated = await api.getChannelConfig();
                  setConfig(updated);
                }}
              />
            )}
          </div>

          <div className="text-xs text-[#9A9590] mt-3 bg-[#EEEAE7]/60 rounded px-3 py-2">
            After you enter both values in Meta Console and click <strong>Verify and Save</strong>,
            Meta sends a test request to your system — it responds automatically.
            You'll see a green checkmark if it worked.
          </div>
        </Step>

        <Step n={4}>
          <div>Get an <strong>Access Token</strong> to allow the AI to send messages back.</div>
          <div className="text-xs text-[#9A9590] mt-1 mb-1.5">
            In your Meta App, go to <strong>Tools → Graph API Explorer</strong>:
          </div>
          <ol className="text-sm text-[#443C3C] space-y-1 list-decimal list-inside ml-1">
            <li>Select your app in the top dropdown</li>
            <li>Click <strong>Generate Access Token</strong> and choose your Facebook Page</li>
            <li>
              Make sure these permissions are checked:{" "}
              <code className="bg-[#EEEAE7] px-1 rounded text-xs">instagram_manage_messages</code>,{" "}
              <code className="bg-[#EEEAE7] px-1 rounded text-xs">pages_manage_metadata</code>
            </li>
            <li>Copy the token shown — you'll need it in the next step</li>
          </ol>
          <div className="text-xs text-[#9A9590] mt-1.5">
            You also need your <strong>Instagram Account ID</strong> — find it in{" "}
            <ExtLink href="https://www.facebook.com/business/help">Meta Business Suite</ExtLink>{" "}
            → Settings → Instagram Accounts.
          </div>
        </Step>

        <Step n={5}>
          Enter your Account ID and Access Token in the form below, then click{" "}
          <strong>Connect Instagram</strong>.
        </Step>
      </div>

      <div className="flex items-center gap-3 pt-1">
        <a
          href="/admin/instagram-test"
          className="text-xs text-[#9A9590] hover:text-[#251D1C] flex items-center gap-1"
        >
          <ExternalLink size={11} /> Test Instagram connection after connecting
        </a>
      </div>
    </div>
  );

  // ── Telegram guide ───────────────────────────────────────────────────────────

  const telegramGuide = (
    <div className="space-y-4">
      <div className="text-xs text-[#9A9590] bg-[#EEEAE7]/60 rounded p-3 space-y-1">
        <div className="font-semibold text-[#443C3C] mb-1.5">What you'll need</div>
        <div>• A Telegram account</div>
      </div>

      <div className="space-y-3">
        <Step n={1}>
          Open{" "}
          <ExtLink href="https://t.me/BotFather">@BotFather</ExtLink> in Telegram.
          Send <code className="bg-[#EEEAE7] px-1 rounded text-xs">/newbot</code>,
          follow the prompts, and copy the <strong>Bot Token</strong>.
        </Step>

        <Step n={2}>
          Enter the bot token below and click Connect. The webhook URL is registered
          with Telegram automatically — you do not need to configure anything in
          the Telegram console.
        </Step>
      </div>
    </div>
  );

  // ── WhatsApp guide ───────────────────────────────────────────────────────────

  const twilioWebhookUrl = appBase ? `${appBase}/api/v1/twilio/whatsapp/webhook` : "";

  const whatsappGuide = (
    <WhatsAppGuide
      waWebhookUrl={waWebhookUrl}
      twilioWebhookUrl={twilioWebhookUrl}
      config={config}
      setConfig={setConfig}
    />
  );

  return (
    <div className="max-w-2xl">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-[#251D1C]">Channel Connections</h1>
          <p className="text-sm text-[#9A9590] mt-1">Agent: {agentId}</p>
        </div>
        <button
          onClick={load}
          className="flex items-center gap-1.5 text-sm text-[#9A9590] hover:text-[#443C3C] border border-[#BEBAB7] px-3 py-1.5 rounded hover:border-[#443C3C] transition-colors"
        >
          <RefreshCw size={13} /> Refresh
        </button>
      </div>

      {error && (
        <div className="mb-4 bg-red-50 border-l-4 border-red-500 px-4 py-3 rounded-sm text-sm text-red-700">
          {error}
        </div>
      )}

      <div className="space-y-4">
        <ChannelCard
          title="Instagram"
          icon="📷"
          bindings={byType("instagram")}
          config={config}
          agentId={agentId}
          channelType="instagram"
          onBindingsChange={load}
          guide={instagramGuide}
          settingsForm={
            config ? (
              <ChannelSettingsForm
                title="Instagram"
                currentVerifyToken={config.instagram_verify_token}
                appSecretConfigured={config.instagram_app_secret_configured}
                verifyTokenHint="e.g. my-instagram-token-2024"
                onSave={async (data) => {
                  await api.updateInstagramSettings(data);
                  const updated = await api.getChannelConfig();
                  setConfig(updated);
                }}
              />
            ) : undefined
          }
        />

        <ChannelCard
          title="Telegram"
          icon="✈️"
          bindings={byType("telegram")}
          config={config}
          agentId={agentId}
          channelType="telegram"
          onBindingsChange={load}
          guide={telegramGuide}
        />

        <ChannelCard
          title="WhatsApp"
          icon="💬"
          bindings={byType("whatsapp")}
          config={config}
          agentId={agentId}
          channelType="whatsapp"
          onBindingsChange={load}
          guide={whatsappGuide}
          settingsForm={
            config ? (
              <ChannelSettingsForm
                title="WhatsApp"
                currentVerifyToken={config.whatsapp_verify_token}
                appSecretConfigured={config.whatsapp_app_secret_configured}
                verifyTokenHint="Auto-generated — you can change it"
                onSave={async (data) => {
                  await api.updateWhatsAppSettings(data);
                  const updated = await api.getChannelConfig();
                  setConfig(updated);
                }}
              />
            ) : undefined
          }
        />
      </div>
    </div>
  );
}
