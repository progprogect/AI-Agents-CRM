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

export default function InstagramTestPage() {
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [recipientId, setRecipientId] = useState("62670099264");
  const [messageText, setMessageText] = useState("Test message from Agent");
  const [isSending, setIsSending] = useState(false);
  const [accountId, setAccountId] = useState("25638311079121978");
  const [recentWebhooks, setRecentWebhooks] = useState<any[]>([]);

  const addLog = (level: LogEntry["level"], message: string, data?: any) => {
    setLogs((prev) => [
      ...prev,
      {
        timestamp: new Date().toLocaleTimeString(),
        level,
        message,
        data,
      },
    ]);
  };

  const checkAccountInfo = async () => {
    try {
      addLog("info", "Checking account info...");
      const response = await fetch(
        `/api/v1/instagram-test/account-info?account_id=${accountId}`
      );

      if (response.ok) {
        const data = await response.json();
        addLog("success", "Account info retrieved", data);
        return data;
      } else {
        const error = await response.json();
        addLog("error", "Failed to retrieve account info", error);
      }
    } catch (error: any) {
      addLog("error", "Request error", error.message);
    }
  };

  const sendTestMessage = async () => {
    setIsSending(true);
    addLog("info", "Sending test message...");
    addLog("info", `Recipient ID: ${recipientId}`);
    addLog("info", `Account ID: ${accountId}`);
    addLog("info", `Message: ${messageText}`);

    try {
      addLog("info", "Sending via backend API...");
      const response = await fetch("/api/v1/instagram-test/send", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          account_id: accountId,
          recipient_id: recipientId,
          message_text: messageText,
          use_self_messaging: false,
        }),
      });

      const result = await response.json();

      if (result.success) {
        addLog("success", "✅ Message sent successfully!", result.response_data);
      } else {
        addLog("error", `❌ Error: ${result.error}`, result.response_data);

        // If standard format failed, try Self Messaging
        if (result.status_code === 400 && result.response_data?.error?.code === 100) {
          addLog("info", "Trying Self Messaging format (without recipient)...");
          const response2 = await fetch("/api/v1/instagram-test/send", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              account_id: accountId,
              recipient_id: recipientId,
              message_text: messageText,
              use_self_messaging: true,
            }),
          });

          const result2 = await response2.json();
          if (result2.success) {
            addLog("success", "✅ Message sent via Self Messaging!", result2.response_data);
          } else {
            addLog("error", `❌ Self Messaging also failed: ${result2.error}`, result2.response_data);
          }
        }
      }
    } catch (error: any) {
      addLog("error", "Send error", error.message);
    } finally {
      setIsSending(false);
    }
  };

  const loadRecentWebhooks = async () => {
    try {
      const response = await fetch("/api/v1/webhook-events/recent?limit=20");
      if (response.ok) {
        const data = await response.json();
        const events = data.events || [];
        setRecentWebhooks(events);

        if (events.length > 0) {
          events.slice(-3).forEach((event: any) => {
            const extracted = event.extracted || {};
            const senderId = extracted.sender_id || event.payload?.entry?.[0]?.messaging?.[0]?.sender?.id;
            const msgText = extracted.message_text || event.payload?.entry?.[0]?.messaging?.[0]?.message?.text;
            const isEcho = extracted.is_echo ?? event.payload?.entry?.[0]?.messaging?.[0]?.message?.is_echo ?? false;

            if (senderId && !isEcho) {
              addLog("success", `📨 Webhook: ${event.type} at ${new Date(event.timestamp).toLocaleTimeString()}`, {
                sender_id: senderId,
                message_text: msgText,
                note: "💡 sender_id is the recipient_id to use when replying",
              });
            } else if (isEcho) {
              addLog("info", `📨 Webhook (Echo): ${event.type} at ${new Date(event.timestamp).toLocaleTimeString()} — ignored`, {
                note: "This message was sent by the agent, ignoring",
              });
            } else {
              addLog("warning", `📨 Webhook: ${event.type} at ${new Date(event.timestamp).toLocaleTimeString()}`, {
                sender_id: senderId || "N/A",
                message_text: msgText,
                note: "⚠️ Sender ID not found — check full payload",
              });
            }
          });
        }
      } else {
        addLog("error", "Failed to load webhook events", await response.text());
      }
    } catch (error: any) {
      addLog("error", "Failed to load webhook events", error.message);
    }
  };

  useEffect(() => {
    addLog("info", "Instagram API test page loaded");
    loadRecentWebhooks();

    const interval = setInterval(loadRecentWebhooks, 5000);
    return () => clearInterval(interval);
  }, []);

  const getLogColor = (level: LogEntry["level"]) => {
    switch (level) {
      case "success": return "text-green-600";
      case "error":   return "text-red-600";
      case "warning": return "text-yellow-600";
      default:        return "text-gray-700";
    }
  };

  return (
    <div className="p-6 max-w-7xl mx-auto">
      <h1 className="text-2xl font-bold text-gray-900 mb-6">Instagram API Testing</h1>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Left column: test form */}
        <div className="space-y-4">
          <div className="bg-white rounded-sm shadow border border-[#251D1C]/20 p-6">
            <h2 className="text-lg font-semibold mb-4">Test Parameters</h2>

            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  Account ID (Instagram Business Account)
                </label>
                <Input
                  value={accountId}
                  onChange={(e) => setAccountId(e.target.value)}
                  placeholder="25638311079121978"
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  Recipient ID
                </label>
                <Input
                  value={recipientId}
                  onChange={(e) => setRecipientId(e.target.value)}
                  placeholder="62670099264"
                />
                <p className="text-xs text-gray-500 mt-1">
                  The user ID to send the message to
                </p>
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  Message Text
                </label>
                <Textarea
                  value={messageText}
                  onChange={(e) => setMessageText(e.target.value)}
                  rows={3}
                  placeholder="Test message..."
                />
              </div>

              <div className="flex gap-2">
                <Button variant="primary" onClick={sendTestMessage} disabled={isSending}>
                  {isSending ? "Sending..." : "Send Message"}
                </Button>
                <Button variant="secondary" onClick={checkAccountInfo}>
                  Check Account
                </Button>
                <Button variant="secondary" onClick={loadRecentWebhooks}>
                  Refresh Webhooks
                </Button>
              </div>
            </div>
          </div>

          {/* Recent webhook events */}
          {recentWebhooks.length > 0 && (
            <div className="bg-white rounded-sm shadow border border-[#251D1C]/20 p-6">
              <div className="flex justify-between items-center mb-4">
                <h2 className="text-lg font-semibold">
                  Recent Webhook Events ({recentWebhooks.length})
                </h2>
                <Button
                  variant="secondary"
                  onClick={async () => {
                    try {
                      const response = await fetch("/api/v1/webhook-events/clear", { method: "POST" });
                      if (response.ok) {
                        addLog("success", "Webhook events cleared");
                        loadRecentWebhooks();
                      }
                    } catch (error: any) {
                      addLog("error", "Failed to clear events", error.message);
                    }
                  }}
                  className="text-sm"
                >
                  Clear
                </Button>
              </div>

              <div className="space-y-2 max-h-96 overflow-y-auto">
                {recentWebhooks.slice().reverse().map((event: any, idx: number) => {
                  const extracted = event.extracted || {};
                  const entry = event.payload?.entry?.[0];
                  const messaging = entry?.messaging?.[0];
                  const sender = messaging?.sender;
                  const recipient = messaging?.recipient;
                  const message = messaging?.message;

                  const eventType =
                    extracted.event_type ||
                    (message ? "message" :
                     messaging?.message_edit ? "message_edit" :
                     messaging?.message_reaction ? "message_reaction" :
                     messaging?.message_unsend ? "message_unsend" : "unknown");

                  const senderId = eventType === "message" ? (extracted.sender_id || sender?.id) : null;
                  const recipientIdVal = eventType === "message" ? (extracted.recipient_id || recipient?.id) : null;
                  const msgText = extracted.message_text || message?.text;
                  const isEcho = extracted.is_echo ?? message?.is_echo ?? false;
                  const isSelf = extracted.is_self ?? message?.is_self ?? false;
                  const showFullPayload = !senderId && !recipientIdVal;

                  return (
                    <div key={event.id || idx} className="p-3 bg-gray-50 rounded border text-sm">
                      <div className="flex justify-between items-start mb-2">
                        <div className="font-medium text-xs text-gray-600">
                          {new Date(event.timestamp).toLocaleString()}
                        </div>
                        <div className="flex gap-1">
                          {senderId && (
                            <button
                              onClick={() => {
                                setRecipientId(senderId);
                                addLog("success", `Recipient ID set from webhook: ${senderId}`);
                              }}
                              className="text-xs bg-[#251D1C] text-white px-2 py-1 rounded hover:bg-[#443C3C] transition-colors"
                              title="Use Sender ID as Recipient ID to reply"
                            >
                              Use as Recipient ID
                            </button>
                          )}
                          {recipientIdVal && (
                            <button
                              onClick={() => {
                                setAccountId(recipientIdVal);
                                addLog("success", `Account ID set from webhook: ${recipientIdVal}`);
                              }}
                              className="text-xs bg-blue-500 text-white px-2 py-1 rounded hover:bg-blue-600 transition-colors"
                              title="Use Recipient ID as Account ID"
                            >
                              Use as Account ID
                            </button>
                          )}
                        </div>
                      </div>

                      {eventType !== "message" && (
                        <div className="mb-2 text-xs bg-yellow-100 text-yellow-800 px-2 py-1 rounded border border-yellow-300">
                          <div className="font-medium">📋 Event type: <strong>{eventType}</strong></div>
                          {eventType === "message_edit" && (
                            <div className="mt-1">
                              <div>⚠️ Known Instagram API behavior:</div>
                              <div className="ml-2">
                                • Instagram sends <code>message_edit</code> with <code>num_edit=0</code> for new messages
                              </div>
                              <div className="ml-2">
                                • This event has <strong>no sender/recipient ID</strong>, so a reply cannot be sent
                              </div>
                              <div className="ml-2 mt-1">
                                💡 Instagram may send a separate <code>message</code> event later with the IDs
                              </div>
                              {extracted.num_edit !== undefined && (
                                <div className="ml-2 mt-1">
                                  num_edit: <strong>{extracted.num_edit}</strong>{" "}
                                  {extracted.num_edit === 0 && "(new message)"}
                                </div>
                              )}
                            </div>
                          )}
                        </div>
                      )}

                      {isEcho && (
                        <div className="mb-2 text-xs bg-yellow-100 text-yellow-800 px-2 py-1 rounded">
                          ⚠️ Echo message (sent by the agent) — ignored
                        </div>
                      )}

                      {isSelf && isEcho && (
                        <div className="mb-2 text-xs bg-blue-100 text-blue-800 px-2 py-1 rounded font-medium">
                          🎯 Self Messaging Event
                        </div>
                      )}

                      <div className="space-y-1">
                        <div className="font-medium">
                          <span className="text-gray-600">Sender ID:</span>{" "}
                          <span className={senderId ? "text-green-600 font-bold" : "text-red-600"}>
                            {senderId || "N/A"}
                          </span>
                          {senderId && (
                            <span className="text-xs text-gray-500 ml-2">
                              (use as recipient_id to reply)
                            </span>
                          )}
                        </div>
                        <div className="text-xs text-gray-500">
                          <span className="text-gray-600">Recipient ID (our account):</span>{" "}
                          <span className={recipientIdVal ? "text-blue-600" : "text-red-600"}>
                            {recipientIdVal || "N/A"}
                          </span>
                        </div>
                        {message?.mid && (
                          <div className="text-xs text-gray-500">Message ID: {message.mid}</div>
                        )}
                      </div>

                      {msgText && (
                        <div className="mt-2 text-xs bg-white p-2 rounded border">
                          <strong>Message:</strong> {msgText}
                        </div>
                      )}

                      {showFullPayload && (
                        <details className="mt-2">
                          <summary className="text-xs text-gray-600 cursor-pointer hover:text-gray-800">
                            Show full payload (debug)
                          </summary>
                          <pre className="mt-2 text-xs bg-gray-800 text-green-400 p-2 rounded overflow-x-auto">
                            {JSON.stringify(event.payload, null, 2)}
                          </pre>
                        </details>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>
          )}
        </div>

        {/* Right column: logs */}
        <div className="bg-white rounded-sm shadow border border-[#251D1C]/20 p-6">
          <div className="flex justify-between items-center mb-4">
            <h2 className="text-lg font-semibold">Logs</h2>
            <Button variant="secondary" onClick={() => setLogs([])} className="text-sm">
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
                  <span className={getLogColor(log.level)}>[{log.level.toUpperCase()}]</span>{" "}
                  <span>{log.message}</span>
                  {log.data && (
                    <pre className="mt-1 ml-4 text-xs overflow-x-auto">
                      {JSON.stringify(log.data, null, 2)}
                    </pre>
                  )}
                </div>
              ))
            )}
          </div>
        </div>
      </div>

      {/* Documentation notes */}
      <div className="mt-6 bg-blue-50 border border-blue-200 rounded-sm p-4">
        <h3 className="font-semibold text-blue-900 mb-2">
          📖 Messenger Platform — Key Notes
        </h3>
        <div className="text-sm text-blue-800 space-y-2">
          <p className="font-medium">From the documentation:</p>
          <ul className="space-y-1 list-disc list-inside ml-4">
            <li>
              Instagram Messaging runs through the <strong>Messenger Platform API</strong>
            </li>
            <li>
              Requires a <strong>Facebook Page</strong> linked to an Instagram Professional account
            </li>
            <li>
              <strong>24-hour messaging window</strong> for replies (Human Agent tag extends it to 7 days)
            </li>
            <li>
              <strong>Self Messaging</strong>: format without a recipient field — sends to yourself
            </li>
            <li>
              Messages from non-followers go to the <strong>Requests</strong> folder
            </li>
            <li>
              Replying via API moves the conversation to the <strong>General</strong> folder
            </li>
          </ul>
          <p className="mt-2 text-xs text-blue-600">
            <strong>Note:</strong> Since July 2024 a new Instagram API with Instagram Login is
            available, which does not require a Facebook Page. We use the Instagram Graph API directly.
          </p>
          <p className="mt-2 text-xs text-blue-600">
            <strong>Troubleshooting:</strong> If you receive a "User not found" error (code 100),
            try using the Facebook Page ID instead of the Instagram Account ID, or check the
            24-hour reply window restriction.
          </p>
        </div>
      </div>
    </div>
  );
}
