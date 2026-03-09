"use client";

import { useEffect, useState } from "react";
import { Button } from "@/components/shared/Button";
import { Input } from "@/components/shared/Input";
import { Textarea } from "@/components/shared/Textarea";

interface LogEntry {
  timestamp: string;
  level: "info" | "success" | "error" | "warning";
  message: string;
  data?: any;
}

interface WhatsAppBinding {
  binding_id: string;
  agent_id: string;
  phone_number_id: string;
  display_name: string;
  is_active: boolean;
  is_verified: boolean;
  provider: "meta" | "twilio";
}

export default function WhatsAppTestPage() {
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [bindings, setBindings] = useState<WhatsAppBinding[]>([]);
  const [selectedBindingId, setSelectedBindingId] = useState<string>("");
  const [recipientPhone, setRecipientPhone] = useState("");
  const [messageText, setMessageText] = useState("Hello! This is a test message from CAworks AI.");
  const [isSending, setIsSending] = useState(false);
  const [recentWebhooks, setRecentWebhooks] = useState<any[]>([]);

  const addLog = (level: LogEntry["level"], message: string, data?: any) => {
    setLogs((prev) => [
      ...prev,
      { timestamp: new Date().toLocaleTimeString(), level, message, data },
    ]);
  };

  const loadBindings = async () => {
    try {
      const token = localStorage.getItem("agent_admin_token");
      const res = await fetch("/api/v1/whatsapp-test/bindings", {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      if (res.ok) {
        const data = await res.json();
        const list: WhatsAppBinding[] = data.bindings || [];
        setBindings(list);
        if (list.length > 0 && !selectedBindingId) {
          setSelectedBindingId(list[0].binding_id);
        }
        addLog("info", `Loaded ${list.length} WhatsApp binding(s)`);
        if (list.length === 0) {
          addLog("warning", "No WhatsApp bindings found. Connect a WhatsApp account in Channel Settings first.");
        }
      } else {
        addLog("error", "Failed to load bindings", await res.text());
      }
    } catch (e: any) {
      addLog("error", "Failed to load bindings", e.message);
    }
  };

  const sendTestMessage = async () => {
    if (!selectedBindingId) {
      addLog("error", "No binding selected. Please connect a WhatsApp account first.");
      return;
    }
    if (!recipientPhone.trim()) {
      addLog("error", "Please enter a recipient phone number.");
      return;
    }

    setIsSending(true);
    const binding = bindings.find((b) => b.binding_id === selectedBindingId);
    const providerLabel = binding?.provider === "twilio" ? "Twilio" : "Meta Cloud API";
    addLog("info", `Sending via ${providerLabel} | From: ${binding?.phone_number_id}`);
    addLog("info", `Recipient: ${recipientPhone}`);
    addLog("info", `Message: ${messageText}`);

    try {
      const token = localStorage.getItem("agent_admin_token");
      const res = await fetch("/api/v1/whatsapp-test/send", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({
          binding_id: selectedBindingId,
          to: recipientPhone.replace(/^\+/, ""),
          message_text: messageText,
        }),
      });

      const result = await res.json();

      if (result.success) {
        addLog("success", "✅ Message sent successfully!", result.response_data);
      } else {
        addLog("error", `❌ Failed: ${result.error}`, result.response_data);
      }
    } catch (e: any) {
      addLog("error", "Send error", e.message);
    } finally {
      setIsSending(false);
    }
  };

  const loadRecentWebhooks = async () => {
    try {
      const res = await fetch("/api/v1/webhook-events/recent?limit=50");
      if (res.ok) {
        const data = await res.json();
        // Filter only WhatsApp events
        const waEvents = (data.events || []).filter(
          (e: any) => e.type === "whatsapp_webhook" || e.type === "twilio_whatsapp"
        );
        setRecentWebhooks(waEvents);
      }
    } catch (e: any) {
      addLog("error", "Failed to load webhook events", e.message);
    }
  };

  const clearWebhooks = async () => {
    try {
      const res = await fetch("/api/v1/webhook-events/clear", { method: "POST" });
      if (res.ok) {
        addLog("success", "Webhook events cleared");
        setRecentWebhooks([]);
      }
    } catch (e: any) {
      addLog("error", "Failed to clear events", e.message);
    }
  };

  useEffect(() => {
    addLog("info", "WhatsApp API test page loaded");
    loadBindings();
    loadRecentWebhooks();

    const interval = setInterval(loadRecentWebhooks, 5000);
    return () => clearInterval(interval);
  }, []);

  const getLogColor = (level: LogEntry["level"]) => {
    switch (level) {
      case "success": return "text-green-400";
      case "error":   return "text-red-400";
      case "warning": return "text-yellow-400";
      default:        return "text-gray-300";
    }
  };

  const selectedBinding = bindings.find((b) => b.binding_id === selectedBindingId);

  return (
    <div className="p-6 max-w-7xl mx-auto">
      <h1 className="text-2xl font-bold text-gray-900 mb-2">WhatsApp API Testing</h1>
      <p className="text-sm text-gray-500 mb-6">
        Test outgoing messages and monitor incoming webhook events from your WhatsApp Business number.
      </p>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Left column */}
        <div className="space-y-4">
          {/* Send form */}
          <div className="bg-white rounded-sm shadow border border-[#251D1C]/20 p-6">
            <h2 className="text-lg font-semibold mb-4">Send Test Message</h2>

            <div className="space-y-4">
              {/* Binding selector */}
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  WhatsApp Business Number (Binding)
                </label>
                {bindings.length === 0 ? (
                  <div className="text-sm text-amber-600 bg-amber-50 border border-amber-200 rounded px-3 py-2">
                    No WhatsApp bindings found. Go to{" "}
                    <a href="/admin/agents" className="underline font-medium">
                      Agents → Channel Connections
                    </a>{" "}
                    to connect a WhatsApp account.
                  </div>
                ) : (
                  <select
                    value={selectedBindingId}
                    onChange={(e) => setSelectedBindingId(e.target.value)}
                    className="w-full border border-gray-300 rounded px-3 py-2 text-sm outline-none focus:border-[#251D1C]"
                  >
                    {bindings.map((b) => (
                      <option key={b.binding_id} value={b.binding_id}>
                        {b.display_name} · ID: {b.phone_number_id}
                        {b.provider === "twilio" ? " [Twilio]" : " [Meta]"}
                        {!b.is_active ? " (inactive)" : ""}
                        {!b.is_verified ? " (unverified)" : ""}
                      </option>
                    ))}
                  </select>
                )}
                {selectedBinding && (
                  <p className="text-xs text-gray-500 mt-1">
                    Phone Number ID: <code className="bg-gray-100 px-1 rounded">{selectedBinding.phone_number_id}</code>
                  </p>
                )}
              </div>

              {/* Recipient */}
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  Recipient Phone Number
                </label>
                <Input
                  value={recipientPhone}
                  onChange={(e) => setRecipientPhone(e.target.value)}
                  placeholder="375255092206  (international format, no + needed)"
                />
                <p className="text-xs text-gray-500 mt-1">
                  Enter the number without + prefix, e.g. <code>375255092206</code>
                </p>
              </div>

              {/* Message */}
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  Message Text
                </label>
                <Textarea
                  value={messageText}
                  onChange={(e) => setMessageText(e.target.value)}
                  rows={3}
                  placeholder="Enter test message..."
                />
              </div>

              <div className="flex gap-2 flex-wrap">
                <Button
                  variant="primary"
                  onClick={sendTestMessage}
                  disabled={isSending || bindings.length === 0}
                >
                  {isSending ? "Sending..." : "Send Message"}
                </Button>
                <Button variant="secondary" onClick={loadBindings}>
                  Reload Bindings
                </Button>
                <Button variant="secondary" onClick={loadRecentWebhooks}>
                  Refresh Webhooks
                </Button>
              </div>
            </div>
          </div>

          {/* Incoming Webhook Events */}
          <div className="bg-white rounded-sm shadow border border-[#251D1C]/20 p-6">
            <div className="flex justify-between items-center mb-4">
              <h2 className="text-lg font-semibold">
                Incoming Webhook Events
                {recentWebhooks.length > 0 && (
                  <span className="ml-2 text-sm font-normal text-gray-500">
                    ({recentWebhooks.length})
                  </span>
                )}
              </h2>
              <div className="flex items-center gap-2">
                <span className="text-xs text-green-600 flex items-center gap-1">
                  <span className="inline-block w-2 h-2 rounded-full bg-green-500 animate-pulse" />
                  Auto-refresh 5s
                </span>
                {recentWebhooks.length > 0 && (
                  <Button variant="secondary" onClick={clearWebhooks} className="text-sm">
                    Clear
                  </Button>
                )}
              </div>
            </div>

            {recentWebhooks.length === 0 ? (
              <div className="text-sm text-gray-500 text-center py-8">
                <p className="font-medium mb-1">No incoming WhatsApp events yet</p>
                <p className="text-xs">
                  Send a message to your WhatsApp Business number from any phone.
                  Events will appear here automatically.
                </p>
              </div>
            ) : (
              <div className="space-y-3 max-h-96 overflow-y-auto">
                {recentWebhooks.slice().reverse().map((event: any, idx: number) => {
                  const extracted = event.extracted || {};
                  const senderPhone = extracted.sender_phone || "";
                  const msgText = extracted.message_text || "";
                  const phoneNumberId = extracted.phone_number_id || "";
                  const displayPhone = extracted.display_phone || phoneNumberId;
                  const msgType = extracted.message_type || "text";
                  const isStatus = !!extracted.status_update;
                  const isTwilio = event.type === "twilio_whatsapp" || extracted.provider === "twilio";

                  return (
                    <div
                      key={event.id || idx}
                      className="p-3 bg-gray-50 rounded border text-sm"
                    >
                      <div className="flex justify-between items-start mb-2">
                        <div className="text-xs text-gray-500 flex items-center gap-2">
                          {new Date(event.timestamp).toLocaleString()}
                          {isTwilio ? (
                            <span className="bg-blue-100 text-blue-700 px-1.5 py-0.5 rounded font-medium">Twilio</span>
                          ) : (
                            <span className="bg-gray-100 text-gray-600 px-1.5 py-0.5 rounded font-medium">Meta</span>
                          )}
                          {isStatus && (
                            <span className="text-amber-600 font-medium">
                              Status: {extracted.status_update}
                            </span>
                          )}
                        </div>
                        <div className="flex gap-1">
                          {senderPhone && (
                            <button
                              onClick={() => {
                                setRecipientPhone(senderPhone);
                                addLog("success", `Recipient set from webhook: ${senderPhone}`);
                              }}
                              className="text-xs bg-[#251D1C] text-white px-2 py-1 rounded hover:bg-[#443C3C] transition-colors"
                              title="Use this phone as Recipient"
                            >
                              Use as Recipient
                            </button>
                          )}
                        </div>
                      </div>

                      <div className="space-y-1">
                        {senderPhone && (
                          <div className="font-medium">
                            <span className="text-gray-600">From:</span>{" "}
                            <span className="text-green-700 font-bold">+{senderPhone}</span>
                            <span className="text-xs text-gray-400 ml-2">
                              (use this as recipient to reply)
                            </span>
                          </div>
                        )}
                        {phoneNumberId && (
                          <div className="text-xs text-gray-500">
                            <span className="text-gray-600">To (our number):</span>{" "}
                            <span className="text-blue-600">{displayPhone || phoneNumberId}</span>
                            <span className="text-gray-400 ml-1">(ID: {phoneNumberId})</span>
                          </div>
                        )}
                        {isStatus && extracted.status_recipient && (
                          <div className="text-xs text-gray-500">
                            <span className="text-gray-600">Status for:</span>{" "}
                            +{extracted.status_recipient}
                          </div>
                        )}
                        {msgType !== "text" && msgType && (
                          <div className="text-xs text-amber-600">
                            Message type: <strong>{msgType}</strong> (non-text)
                          </div>
                        )}
                      </div>

                      {msgText && (
                        <div className="mt-2 text-xs bg-white p-2 rounded border">
                          <strong>Message:</strong> {msgText}
                        </div>
                      )}

                      <details className="mt-2">
                        <summary className="text-xs text-gray-500 cursor-pointer hover:text-gray-700">
                          Show full payload (debug)
                        </summary>
                        <pre className="mt-2 text-xs bg-gray-900 text-green-400 p-2 rounded overflow-x-auto max-h-48">
                          {JSON.stringify(event.payload, null, 2)}
                        </pre>
                      </details>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        </div>

        {/* Right column — Logs */}
        <div className="bg-white rounded-sm shadow border border-[#251D1C]/20 p-6">
          <div className="flex justify-between items-center mb-4">
            <h2 className="text-lg font-semibold">Logs</h2>
            <Button
              variant="secondary"
              onClick={() => setLogs([])}
              className="text-sm"
            >
              Clear
            </Button>
          </div>

          <div className="bg-gray-900 text-gray-100 p-4 rounded font-mono text-xs overflow-auto max-h-[600px]">
            {logs.length === 0 ? (
              <div className="text-gray-500">Logs will appear here...</div>
            ) : (
              logs.map((log, idx) => (
                <div key={idx} className="mb-2">
                  <span className="text-gray-500">[{log.timestamp}]</span>{" "}
                  <span className={getLogColor(log.level)}>
                    [{log.level.toUpperCase()}]
                  </span>{" "}
                  <span>{log.message}</span>
                  {log.data && (
                    <pre className="mt-1 ml-4 text-xs overflow-x-auto text-gray-400">
                      {typeof log.data === "string"
                        ? log.data
                        : JSON.stringify(log.data, null, 2)}
                    </pre>
                  )}
                </div>
              ))
            )}
          </div>
        </div>
      </div>

      {/* Documentation notes */}
      <div className="mt-6 space-y-4">
        <div className="bg-blue-50 border border-blue-200 rounded-sm p-4">
          <h3 className="font-semibold text-blue-900 mb-2">
            🟦 Twilio Sandbox — Webhook Setup Required
          </h3>
          <div className="text-sm text-blue-800 space-y-1">
            <p>
              In <strong>Twilio Console → Messaging → Try it out → Sandbox Settings</strong>,
              set <strong>"When a message comes in"</strong> to:
            </p>
            <code className="block bg-blue-100 px-3 py-1.5 rounded font-mono text-xs break-all">
              {typeof window !== "undefined"
                ? `${window.location.origin}/api/v1/twilio/whatsapp/webhook`
                : "https://your-domain.up.railway.app/api/v1/twilio/whatsapp/webhook"}
            </code>
            <p className="text-xs text-blue-600 mt-1">
              Method: <strong>POST</strong>. Without this, incoming messages will not be received.
            </p>
            <p className="text-xs text-blue-600">
              For Sandbox testing: your phone must first send <strong>join &lt;word&gt;</strong> to the Twilio Sandbox number.
            </p>
          </div>
        </div>

        <div className="bg-green-50 border border-green-200 rounded-sm p-4">
          <h3 className="font-semibold text-green-900 mb-2">
            📖 How to test
          </h3>
          <div className="text-sm text-green-800 space-y-2">
            <ul className="space-y-1 list-disc list-inside ml-4">
              <li>
                <strong>Outgoing:</strong> Select a binding, enter a recipient number, click Send Message.
                The correct API (Twilio or Meta) is chosen automatically.
              </li>
              <li>
                <strong>Incoming:</strong> Send a WhatsApp message to your Business/Sandbox number —
                events appear in "Incoming Webhook Events" automatically (5s refresh).
              </li>
              <li>
                Click <strong>Use as Recipient</strong> on an incoming event to quickly reply.
              </li>
            </ul>
            <p className="mt-2 text-xs text-green-600">
              <strong>Meta:</strong> Recipient must have messaged you within 24h, or use a template.
              Use a permanent System User token for production.
            </p>
            <p className="mt-1 text-xs text-green-600">
              <strong>Twilio Sandbox:</strong> Both sender and recipient must join the sandbox first.
              For production, register a real WhatsApp Sender in Twilio Console.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
