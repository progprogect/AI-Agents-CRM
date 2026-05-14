/** API client for backend communication. */

import { getAdminToken, removeAdminToken } from "./auth";
import type {
  Agent,
  CreateConversationRequest,
  CreateConversationResponse,
  Conversation,
  ErrorResponse,
  Message,
  SendMessageRequest,
  SendMessageResponse,
} from "./types";
import type {
  ChannelBinding,
  CreateChannelBindingRequest,
  UpdateChannelBindingRequest,
} from "./types/channel";
import type {
  NotificationConfig,
  CreateNotificationConfigRequest,
  UpdateNotificationConfigRequest,
} from "./types/notification";

export interface RagFolder {
  id: string;
  agent_id: string;
  parent_id: string | null;
  name: string;
  created_at: string | null;
  updated_at: string | null;
}

export interface RagDocument {
  document_id: string;
  title: string;
  file_type: string;
  file_url: string | null;
  original_filename: string | null;
  file_size: number | null;
  folder_id: string | null;
  created_at: string | null;
  updated_at: string | null;
}

export interface RagDocumentUploadResponse {
  document_id: string;
  title: string;
  file_type: string;
  file_url: string;
  original_filename: string;
  file_size: number;
  folder_id: string | null;
  warning?: string; // Present when document was saved but AI processing (embeddings/description) failed
}

export interface CloudinaryRagResource {
  public_id: string;
  resource_type: string;
  format?: string | null;
  bytes?: number | null;
  created_at?: string;
  secure_url?: string;
  width?: number | null;
  height?: number | null;
}

export interface CloudinaryImportResultItem {
  public_id: string;
  status: "ok" | "duplicate" | "error";
  document_id?: string;
  title?: string;
  file_type?: string;
  file_url?: string;
  message?: string;
  warning?: string;
}

// Use relative URLs when running on same domain (via ALB)
// This automatically uses the same protocol (HTTP/HTTPS) as the page
// Fallback to absolute URL only for development (localhost)
// IMPORTANT: This function must be called at runtime, not at module load time
// because in Next.js SSR, window is not available during module initialization
const getApiBaseUrl = (): string => {
  // CRITICAL: If running in browser (client-side), ALWAYS use relative URLs for production
  // This ensures the same protocol (HTTPS) as the page, preventing Mixed Content errors
  if (typeof window !== "undefined" && window.location) {
    const host = window.location.host;
    // If not localhost, ALWAYS use relative URLs (empty string)
    // Ignore NEXT_PUBLIC_API_URL in browser to prevent Mixed Content issues
    if (host !== "localhost:3000" && !host.startsWith("localhost:")) {
      return ""; // Relative URL - uses same protocol as page (HTTPS if page is HTTPS)
    }
    // For localhost development, use HTTP localhost
    return "http://localhost:8000";
  }
  
  // Server-side rendering: In production, use relative URLs to avoid Mixed Content
  // Next.js will resolve relative URLs using the same protocol as the incoming request
  // This prevents SSR from making HTTP requests when the page is served over HTTPS
  const isProduction = process.env.NODE_ENV === "production";
  
  if (isProduction) {
    // In production SSR, use relative URL (empty string)
    // Next.js will use the same protocol as the request (HTTPS)
    return "";
  }
  
  // Development SSR: Use NEXT_PUBLIC_API_URL if set, otherwise localhost
  if (typeof process !== "undefined" && process.env && process.env.NEXT_PUBLIC_API_URL) {
    return process.env.NEXT_PUBLIC_API_URL;
  }
  
  // Final fallback: localhost for development
  return "http://localhost:8000";
};

class ApiError extends Error {
  constructor(
    public code: string,
    message: string,
    public details?: Record<string, any>,
    public requestId?: string
  ) {
    super(message);
    this.name = "ApiError";
  }
}

function clearAdminSessionIfUnauthorized(status: number): void {
  if (status === 401 || status === 403) {
    if (typeof window !== "undefined") {
      removeAdminToken();
    }
  }
}

/** Normalize FastAPI / custom `{ error: { message } }` bodies for display. */
function messageFromApiErrorPayload(data: unknown, fallback: string): string {
  if (!data || typeof data !== "object") return fallback;
  const o = data as Record<string, unknown>;
  const errObj = o.error;
  if (errObj && typeof errObj === "object" && errObj !== null) {
    const msg = (errObj as { message?: unknown }).message;
    if (typeof msg === "string" && msg.trim()) return msg;
  }
  const detail = o.detail;
  if (typeof detail === "string" && detail.trim()) return detail;
  if (Array.isArray(detail)) {
    const parts = detail
      .map((item) => {
        if (typeof item === "string") return item;
        if (item && typeof item === "object" && item !== null) {
          const msg = (item as { msg?: unknown }).msg;
          if (typeof msg === "string" && msg.trim()) return msg;
        }
        return null;
      })
      .filter((s): s is string => Boolean(s));
    if (parts.length) return parts.join("; ");
  }
  return fallback;
}

async function request<T>(
  endpoint: string,
  options: RequestInit = {},
  requireAuth: boolean = false
): Promise<T> {
  // Calculate API_BASE_URL dynamically at request time, not at module load time
  // This ensures window.location is available when running in the browser
  const API_BASE_URL = getApiBaseUrl();
  const url = `${API_BASE_URL}${endpoint}`;
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(options.headers as Record<string, string>),
  };

  // Add Authorization header for admin endpoints
  if (requireAuth) {
    const token = getAdminToken();
    if (token) {
      headers["Authorization"] = `Bearer ${token}`;
    }
  }

  try {
    const response = await fetch(url, {
      ...options,
      headers,
    });

    // Handle empty responses (e.g., 204 No Content)
    if (response.status === 204) {
      return undefined as T;
    }

    // For 201 Created, check if there's a response body
    if (response.status === 201) {
      const contentType = response.headers.get("content-type");
      if (contentType && contentType.includes("application/json")) {
        try {
          const data = await response.json();
          return data as T;
        } catch {
          // If parsing fails, return undefined
          return undefined as T;
        }
      }
      // If no JSON content type, return undefined
      return undefined as T;
    }

    let data: any;
    try {
      data = await response.json();
    } catch {
      // If response is not JSON, create error from status
      if (!response.ok) {
        throw new ApiError(
          response.status.toString(),
          `HTTP ${response.status}: ${response.statusText}`,
          undefined,
          undefined
        );
      }
      return undefined as T;
    }

    if (!response.ok) {
      // FastAPI returns errors in format: { "detail": "message" }
      // Our custom errors use: { "error": { "code": "...", "message": "..." } }
      const error = data as ErrorResponse & { detail?: string };

      clearAdminSessionIfUnauthorized(response.status);

      // Use status code as error code if error.error.code is not available
      const errorCode = error.error?.code || response.status.toString();
      const errorMessage = messageFromApiErrorPayload(data, "An error occurred");
      
      throw new ApiError(
        errorCode,
        errorMessage,
        error.error?.details,
        error.error?.request_id
      );
    }

    return data as T;
  } catch (error) {
    if (error instanceof ApiError) {
      throw error;
    }
    throw new ApiError(
      "NETWORK_ERROR",
      error instanceof Error ? error.message : "Network request failed"
    );
  }
}

export const api = {
  // Agent endpoints
  async getAgent(agentId: string): Promise<Agent> {
    return request<Agent>(`/api/v1/agents/${agentId}`);
  },

  async listAgents(activeOnly: boolean = true): Promise<Agent[]> {
    return request<Agent[]>(`/api/v1/agents?active_only=${activeOnly}`);
  },

  async createAgent(agentId: string, config: any): Promise<Agent> {
    return request<Agent>(
      "/api/v1/agents/",
      {
        method: "POST",
        body: JSON.stringify({ agent_id: agentId, config }),
      },
      true // require auth
    );
  },

  async updateAgent(agentId: string, config: any): Promise<Agent> {
    return request<Agent>(
      `/api/v1/agents/${agentId}`,
      {
        method: "PUT",
        body: JSON.stringify(config),
      },
      true // require auth
    );
  },

  async deleteAgent(agentId: string): Promise<void> {
    await request<void>(
      `/api/v1/agents/${agentId}`,
      {
        method: "DELETE",
      },
      true // require auth
    );
  },

  // Conversation endpoints
  async createConversation(
    data: CreateConversationRequest
  ): Promise<CreateConversationResponse> {
    return request<CreateConversationResponse>("/api/v1/chat/conversations", {
      method: "POST",
      body: JSON.stringify(data),
    });
  },

  async getConversation(conversationId: string): Promise<Conversation> {
    return request<Conversation>(
      `/api/v1/chat/conversations/${conversationId}`
    );
  },

  async closePublicConversation(
    conversationId: string
  ): Promise<{ conversation_id: string; status: string }> {
    return request<{ conversation_id: string; status: string }>(
      `/api/v1/chat/conversations/${conversationId}/close`,
      { method: "POST" }
    );
  },

  async getAdminConversation(conversationId: string): Promise<Conversation> {
    return request<Conversation>(
      `/api/v1/admin/conversations/${conversationId}`,
      {},
      true // require auth
    );
  },

  async getMessages(
    conversationId: string,
    limit: number = 100
  ): Promise<Message[]> {
    return request<Message[]>(
      `/api/v1/chat/conversations/${conversationId}/messages?limit=${limit}`
    );
  },

  async sendMessage(
    conversationId: string,
    data: SendMessageRequest
  ): Promise<SendMessageResponse> {
    return request<SendMessageResponse>(
      `/api/v1/chat/conversations/${conversationId}/messages`,
      {
        method: "POST",
        body: JSON.stringify(data),
      }
    );
  },

  // Bot command management (Telegram only)
  async getTelegramCommands(bindingId: string): Promise<import("./types/channel").TelegramCommand[]> {
    return request<import("./types/channel").TelegramCommand[]>(
      `/api/v1/channel-bindings/${bindingId}/commands`,
      {},
      true
    );
  },

  async updateTelegramCommands(
    bindingId: string,
    commands: Record<string, boolean>
  ): Promise<import("./types/channel").TelegramCommand[]> {
    return request<import("./types/channel").TelegramCommand[]>(
      `/api/v1/channel-bindings/${bindingId}/commands`,
      { method: "PUT", body: JSON.stringify({ commands }) },
      true
    );
  },

  async patchTelegramCommandSettings(
    bindingId: string,
    settings: Record<
      string,
      { menu_description?: string | null; message?: string | null }
    >
  ): Promise<import("./types/channel").TelegramCommand[]> {
    return request<import("./types/channel").TelegramCommand[]>(
      `/api/v1/channel-bindings/${bindingId}/commands/settings`,
      { method: "PATCH", body: JSON.stringify({ settings }) },
      true
    );
  },

  async transcribeVoice(
    conversationId: string,
    audioBlob: Blob,
    filename = "voice.webm"
  ): Promise<{ transcript: string }> {
    const formData = new FormData();
    formData.append("file", audioBlob, filename);
    const res = await fetch(
      `/api/v1/chat/conversations/${conversationId}/voice`,
      { method: "POST", body: formData }
    );
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new ApiError(res.status.toString(), err.detail || "Transcription failed");
    }
    return res.json();
  },

  async uploadWebChatMedia(
    conversationId: string,
    file: File
  ): Promise<{ url: string; media_type: string; filename: string; size_bytes: number }> {
    const formData = new FormData();
    formData.append("file", file);
    const res = await fetch(
      `/api/v1/chat/conversations/${conversationId}/media/upload`,
      {
        method: "POST",
        body: formData,
      }
    );
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new ApiError(res.status.toString(), err.detail || "Media upload failed");
    }
    return res.json();
  },

  // Admin endpoints
  async listConversations(params?: {
    agent_id?: string;
    status?: string;
    marketing_status?: string;
    crm_stage_id?: string;
    limit?: number;
    sort_by?: "created_at" | "updated_at";
    sort_order?: "asc" | "desc";
    created_from?: string;
    created_to?: string;
  }): Promise<Conversation[]> {
    const queryParams = new URLSearchParams();
    if (params?.agent_id) queryParams.append("agent_id", params.agent_id);
    if (params?.status) queryParams.append("status", params.status);
    if (params?.marketing_status)
      queryParams.append("marketing_status", params.marketing_status);
    if (params?.crm_stage_id)
      queryParams.append("crm_stage_id", params.crm_stage_id);
    if (params?.limit) queryParams.append("limit", params.limit.toString());
    if (params?.sort_by) queryParams.append("sort_by", params.sort_by);
    if (params?.sort_order) queryParams.append("sort_order", params.sort_order);
    if (params?.created_from?.trim())
      queryParams.append("created_from", params.created_from.trim());
    if (params?.created_to?.trim())
      queryParams.append("created_to", params.created_to.trim());

    return request<Conversation[]>(
      `/api/v1/admin/conversations?${queryParams.toString()}`,
      {},
      true
    );
  },

  async handoffConversation(
    conversationId: string,
    adminId: string,
    reason?: string
  ): Promise<{ conversation_id: string; status: string; message: string }> {
    return request<{ conversation_id: string; status: string; message: string }>(
      `/api/v1/admin/conversations/${conversationId}/handoff`,
      {
        method: "POST",
        body: JSON.stringify({ admin_id: adminId, reason }),
      },
      true // require auth
    );
  },

  async returnToAI(
    conversationId: string,
    adminId: string
  ): Promise<{ conversation_id: string; status: string; message: string }> {
    return request(
      `/api/v1/admin/conversations/${conversationId}/return`,
      {
        method: "POST",
        body: JSON.stringify({ admin_id: adminId }),
      },
      true // require auth
    ) as Promise<{ conversation_id: string; status: string; message: string }>;
  },

  async resetAgentContext(
    conversationId: string,
    adminId: string
  ): Promise<{ conversation_id: string; agent_context_reset_at: string; message: string }> {
    return request(
      `/api/v1/admin/conversations/${conversationId}/reset-agent-context`,
      {
        method: "POST",
        body: JSON.stringify({ admin_id: adminId }),
      },
      true
    ) as Promise<{ conversation_id: string; agent_context_reset_at: string; message: string }>;
  },

  async sendAdminMessage(
    conversationId: string,
    adminId: string,
    content: string,
    mediaUrl?: string | null,
    mediaType?: string | null,
    mediaFilename?: string | null,
  ): Promise<Message> {
    return request<Message>(
      `/api/v1/admin/conversations/${conversationId}/messages`,
      {
        method: "POST",
        body: JSON.stringify({
          admin_id: adminId,
          content,
          media_url: mediaUrl ?? undefined,
          media_type: mediaType ?? undefined,
          media_filename: mediaFilename ?? undefined,
        }),
      },
      true
    );
  },

  async uploadChatMedia(file: File): Promise<{ url: string; media_type: string; filename: string; size_bytes: number }> {
    const formData = new FormData();
    formData.append("file", file, file.name || "upload.bin");
    const token = getAdminToken();
    const res = await fetch("/api/v1/media/upload", {
      method: "POST",
      headers: token ? { Authorization: `Bearer ${token}` } : {},
      body: formData,
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      clearAdminSessionIfUnauthorized(res.status);
      throw new ApiError(
        res.status.toString(),
        messageFromApiErrorPayload(err, "Media upload failed")
      );
    }
    return res.json();
  },

  async refreshInstagramProfile(
    conversationId: string
  ): Promise<{ name?: string; username?: string; profile_pic?: string; error?: string }> {
    return request(
      `/api/v1/admin/conversations/${conversationId}/refresh-profile`,
      {
        method: "POST",
      },
      true // require auth
    );
  },

  async getAuditLogs(params?: {
    admin_id?: string;
    resource_type?: string;
    action?: string;
    start_date?: string;
    end_date?: string;
    sort?: string;
    limit?: number;
  }): Promise<any[]> {
    const queryParams = new URLSearchParams();
    if (params?.admin_id) queryParams.append("admin_id", params.admin_id);
    if (params?.resource_type)
      queryParams.append("resource_type", params.resource_type);
    if (params?.action) queryParams.append("action", params.action);
    if (params?.start_date) queryParams.append("start_date", params.start_date);
    if (params?.end_date) queryParams.append("end_date", params.end_date);
    if (params?.sort) queryParams.append("sort", params.sort);
    if (params?.limit)
      queryParams.append("limit", params.limit.toString());

    return request<any[]>(
      `/api/v1/admin/audit?${queryParams.toString()}`,
      {},
      true // require auth
    );
  },

  async getStats(params?: {
    period?: string;
    include_comparison?: boolean;
  }): Promise<import("./types/stats").Stats> {
    const queryParams = new URLSearchParams();
    if (params?.period) queryParams.append("period", params.period);
    if (params?.include_comparison !== undefined)
      queryParams.append("include_comparison", params.include_comparison.toString());

    return request<import("./types/stats").Stats>(
      `/api/v1/admin/stats?${queryParams.toString()}`,
      {},
      true
    ); // require auth
  },

  async getAdminStatsEndUsers(params?: {
    limit?: number;
    offset?: number;
  }): Promise<import("./types/stats").EndUsersPage> {
    const queryParams = new URLSearchParams();
    if (params?.limit != null) queryParams.append("limit", String(params.limit));
    if (params?.offset != null) queryParams.append("offset", String(params.offset));
    const qs = queryParams.toString();
    return request<import("./types/stats").EndUsersPage>(
      `/api/v1/admin/stats/end-users${qs ? `?${qs}` : ""}`,
      {},
      true
    );
  },

  // Channel bindings endpoints
  async createChannelBinding(
    agentId: string,
    data: CreateChannelBindingRequest
  ): Promise<ChannelBinding> {
    return request<ChannelBinding>(
      `/api/v1/agents/${agentId}/channel-bindings`,
      {
        method: "POST",
        body: JSON.stringify(data),
      },
      true // require auth
    );
  },

  async listChannelBindings(
    agentId: string,
    channelType?: string,
    activeOnly: boolean = true
  ): Promise<ChannelBinding[]> {
    const queryParams = new URLSearchParams();
    if (channelType) queryParams.append("channel_type", channelType);
    queryParams.append("active_only", activeOnly.toString());

    return request<ChannelBinding[]>(
      `/api/v1/agents/${agentId}/channel-bindings?${queryParams.toString()}`,
      {},
      true // require auth
    );
  },

  async getChannelBinding(bindingId: string): Promise<ChannelBinding> {
    return request<ChannelBinding>(
      `/api/v1/channel-bindings/${bindingId}`,
      {},
      true // require auth
    );
  },

  async updateChannelBinding(
    bindingId: string,
    data: UpdateChannelBindingRequest
  ): Promise<ChannelBinding> {
    return request<ChannelBinding>(
      `/api/v1/channel-bindings/${bindingId}`,
      {
        method: "PUT",
        body: JSON.stringify(data),
      },
      true // require auth
    );
  },

  async deleteChannelBinding(bindingId: string): Promise<void> {
    await request<void>(
      `/api/v1/channel-bindings/${bindingId}`,
      {
        method: "DELETE",
      },
      true // require auth
    );
  },

  async verifyChannelBinding(bindingId: string): Promise<{
    binding_id: string;
    is_verified: boolean;
    status: string;
  }> {
    return request<{
      binding_id: string;
      is_verified: boolean;
      status: string;
    }>(
      `/api/v1/channel-bindings/${bindingId}/verify`,
      {
        method: "POST",
      },
      true // require auth
    );
  },

  // ── Channel config ────────────────────────────────────────────────────────

  async getChannelConfig(): Promise<import("./types/channel").ChannelConfig> {
    return request<import("./types/channel").ChannelConfig>(
      "/api/v1/admin/channel-config",
      {},
      true
    );
  },

  async updateInstagramSettings(data: {
    verify_token?: string;
    app_secret?: string;
  }): Promise<{ message: string }> {
    return request<{ message: string }>(
      "/api/v1/admin/instagram-settings",
      { method: "PUT", body: JSON.stringify(data) },
      true
    );
  },

  async updateWhatsAppSettings(data: {
    verify_token?: string;
    app_secret?: string;
  }): Promise<{ message: string }> {
    return request<{ message: string }>(
      "/api/v1/admin/whatsapp-settings",
      { method: "PUT", body: JSON.stringify(data) },
      true
    );
  },

  // Notification configs endpoints
  async listNotificationConfigs(
    activeOnly: boolean = false
  ): Promise<NotificationConfig[]> {
    const queryParams = new URLSearchParams();
    queryParams.append("active_only", activeOnly.toString());

    return request<NotificationConfig[]>(
      `/api/v1/admin/notifications?${queryParams.toString()}`,
      {},
      true // require auth
    );
  },

  async createNotificationConfig(
    data: CreateNotificationConfigRequest
  ): Promise<NotificationConfig> {
    return request<NotificationConfig>(
      `/api/v1/admin/notifications`,
      {
        method: "POST",
        body: JSON.stringify(data),
      },
      true // require auth
    );
  },

  async getNotificationConfig(configId: string): Promise<NotificationConfig> {
    return request<NotificationConfig>(
      `/api/v1/admin/notifications/${configId}`,
      {},
      true // require auth
    );
  },

  async updateNotificationConfig(
    configId: string,
    data: UpdateNotificationConfigRequest
  ): Promise<NotificationConfig> {
    return request<NotificationConfig>(
      `/api/v1/admin/notifications/${configId}`,
      {
        method: "PUT",
        body: JSON.stringify(data),
      },
      true // require auth
    );
  },

  async deleteNotificationConfig(configId: string): Promise<void> {
    await request<void>(
      `/api/v1/admin/notifications/${configId}`,
      {
        method: "DELETE",
      },
      true // require auth
    );
  },

  async testNotification(configId: string): Promise<{
    status: string;
    message: string;
  }> {
    return request<{
      status: string;
      message: string;
    }>(
      `/api/v1/admin/notifications/${configId}/test`,
      {
        method: "POST",
      },
      true // require auth
    );
  },

  // RAG endpoints
  async listRagFolders(agentId: string): Promise<RagFolder[]> {
    return request<RagFolder[]>(
      `/api/v1/agents/${agentId}/rag/folders`,
      {},
      true
    );
  },

  async createRagFolder(
    agentId: string,
    name: string,
    parentId?: string
  ): Promise<RagFolder> {
    const formData = new FormData();
    formData.append("name", name);
    if (parentId) formData.append("parent_id", parentId);
    const API_BASE_URL = getApiBaseUrl();
    const token = getAdminToken();
    const res = await fetch(
      `${API_BASE_URL}/api/v1/agents/${agentId}/rag/folders`,
      {
        method: "POST",
        headers: token ? { Authorization: `Bearer ${token}` } : {},
        body: formData,
      }
    );
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      clearAdminSessionIfUnauthorized(res.status);
      throw new ApiError(
        (err as { error?: { code?: string } }).error?.code || res.status.toString(),
        messageFromApiErrorPayload(err, "Failed to create folder")
      );
    }
    return res.json();
  },

  async updateRagFolder(
    agentId: string,
    folderId: string,
    name: string
  ): Promise<{ message: string }> {
    return request<{ message: string }>(
      `/api/v1/agents/${agentId}/rag/folders/${folderId}`,
      {
        method: "PATCH",
        body: JSON.stringify({ name }),
      },
      true
    );
  },

  async deleteRagFolder(
    agentId: string,
    folderId: string
  ): Promise<{ message: string }> {
    return request<{ message: string }>(
      `/api/v1/agents/${agentId}/rag/folders/${folderId}`,
      { method: "DELETE" },
      true
    );
  },

  async listRagDocuments(
    agentId: string,
    folderId?: string,
    limit?: number,
    offset?: number
  ): Promise<RagDocument[]> {
    const params = new URLSearchParams();
    if (folderId) params.append("folder_id", folderId);
    if (limit) params.append("limit", limit.toString());
    if (offset) params.append("offset", offset.toString());
    return request<RagDocument[]>(
      `/api/v1/agents/${agentId}/rag/documents?${params.toString()}`,
      {},
      true
    );
  },

  async uploadRagDocument(
    agentId: string,
    file: File,
    folderId?: string,
    title?: string
  ): Promise<RagDocumentUploadResponse> {
    const formData = new FormData();
    formData.append("file", file, file.name || "upload.bin");
    if (folderId) formData.append("folder_id", folderId);
    if (title) formData.append("title", title);
    const API_BASE_URL = getApiBaseUrl();
    const token = getAdminToken();
    const res = await fetch(
      `${API_BASE_URL}/api/v1/agents/${agentId}/rag/documents`,
      {
        method: "POST",
        headers: token ? { Authorization: `Bearer ${token}` } : {},
        body: formData,
      }
    );
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      clearAdminSessionIfUnauthorized(res.status);
      throw new ApiError(
        (err as { error?: { code?: string } }).error?.code || res.status.toString(),
        messageFromApiErrorPayload(err, "Failed to upload document")
      );
    }
    return res.json();
  },

  async updateRagDocument(
    agentId: string,
    documentId: string,
    data: { title?: string; folder_id?: string }
  ): Promise<{ message: string }> {
    return request<{ message: string }>(
      `/api/v1/agents/${agentId}/rag/documents/${documentId}`,
      {
        method: "PATCH",
        body: JSON.stringify(data),
      },
      true
    );
  },

  async deleteRagDocument(
    agentId: string,
    documentId: string
  ): Promise<{ message: string }> {
    return request<{ message: string }>(
      `/api/v1/agents/${agentId}/rag/documents/${documentId}`,
      { method: "DELETE" },
      true
    );
  },

  async listCloudinaryRagResources(
    agentId: string,
    params?: { prefix?: string; max_results?: number; next_cursor?: string }
  ): Promise<{
    resources: CloudinaryRagResource[];
    next_cursor?: string | null;
    total_count?: number | null;
    default_prefix: string;
  }> {
    const q = new URLSearchParams();
    if (params?.prefix) q.append("prefix", params.prefix);
    if (params?.max_results) q.append("max_results", params.max_results.toString());
    if (params?.next_cursor) q.append("next_cursor", params.next_cursor);
    const qs = q.toString();
    return request(
      `/api/v1/agents/${agentId}/rag/cloudinary/resources${qs ? `?${qs}` : ""}`,
      {},
      true
    ) as Promise<{
      resources: CloudinaryRagResource[];
      next_cursor?: string | null;
      total_count?: number | null;
      default_prefix: string;
    }>;
  },

  async importRagFromCloudinary(
    agentId: string,
    body: {
      items: { public_id: string; resource_type: string; format?: string | null }[];
      folder_id?: string | null;
      allowed_prefix?: string | null;
    }
  ): Promise<{ results: CloudinaryImportResultItem[]; allowed_prefix: string }> {
    return request<{ results: CloudinaryImportResultItem[]; allowed_prefix: string }>(
      `/api/v1/agents/${agentId}/rag/documents/import-from-cloudinary`,
      {
        method: "POST",
        body: JSON.stringify(body),
      },
      true
    );
  },

  async updateMarketingStatus(
    conversationId: string,
    marketingStatus: string,
    adminId: string,
    rejectionReason?: string
  ): Promise<{
    conversation_id: string;
    marketing_status: string;
    rejection_reason?: string | null;
    message: string;
  }> {
    return request<{
      conversation_id: string;
      marketing_status: string;
      rejection_reason?: string | null;
      message: string;
    }>(
      `/api/v1/admin/conversations/${conversationId}/marketing-status`,
      {
        method: "PATCH",
        body: JSON.stringify({
          marketing_status: marketingStatus,
          rejection_reason: rejectionReason,
          admin_id: adminId,
        }),
      },
      true
    );
  },

  // ── CRM Stages ──────────────────────────────────────────────────────────────

  async listCrmStages(): Promise<import("./types/conversation").CRMStage[]> {
    return request<import("./types/conversation").CRMStage[]>(
      "/api/v1/crm/stages",
      {},
      true
    );
  },

  async createCrmStage(
    name: string,
    color: string
  ): Promise<import("./types/conversation").CRMStage> {
    return request<import("./types/conversation").CRMStage>(
      "/api/v1/crm/stages",
      { method: "POST", body: JSON.stringify({ name, color }) },
      true
    );
  },

  async updateCrmStage(
    stageId: string,
    data: { name?: string; color?: string; position?: number }
  ): Promise<import("./types/conversation").CRMStage> {
    return request<import("./types/conversation").CRMStage>(
      `/api/v1/crm/stages/${stageId}`,
      { method: "PUT", body: JSON.stringify(data) },
      true
    );
  },

  async deleteCrmStage(stageId: string): Promise<void> {
    return request<void>(
      `/api/v1/crm/stages/${stageId}`,
      { method: "DELETE" },
      true
    );
  },

  async updateConversationCrmStage(
    conversationId: string,
    crmStageId: string
  ): Promise<{ conversation_id: string; crm_stage_id: string; stage_name: string; message: string }> {
    return request<{ conversation_id: string; crm_stage_id: string; stage_name: string; message: string }>(
      `/api/v1/crm/conversations/${conversationId}/crm-stage`,
      { method: "PATCH", body: JSON.stringify({ crm_stage_id: crmStageId }) },
      true
    );
  },

  // ── Payment ──────────────────────────────────────────────────────────────────

  async getPaymentSettings(bindingId: string): Promise<import("./types/payment").PaymentSettings> {
    return request<import("./types/payment").PaymentSettings>(
      `/api/v1/channel-bindings/${bindingId}/payment-settings`,
      {},
      true
    );
  },

  async upsertPaymentSettings(
    bindingId: string,
    data: import("./types/payment").UpsertPaymentSettingsRequest
  ): Promise<import("./types/payment").PaymentSettings> {
    return request<import("./types/payment").PaymentSettings>(
      `/api/v1/channel-bindings/${bindingId}/payment-settings`,
      { method: "PUT", body: JSON.stringify(data) },
      true
    );
  },

  async setPaymentToken(
    bindingId: string,
    token?: string,
    tokenSandbox?: string
  ): Promise<{ ok: boolean; has_live_token: boolean; has_sandbox_token: boolean }> {
    return request(
      `/api/v1/channel-bindings/${bindingId}/payment-token`,
      {
        method: "PUT",
        body: JSON.stringify({ token: token ?? null, token_sandbox: tokenSandbox ?? null }),
      },
      true
    );
  },

  async listPaymentPlans(
    bindingId: string,
    activeOnly = true
  ): Promise<import("./types/payment").PaymentPlan[]> {
    return request<import("./types/payment").PaymentPlan[]>(
      `/api/v1/channel-bindings/${bindingId}/payment-plans?active_only=${activeOnly}`,
      {},
      true
    );
  },

  async createPaymentPlan(
    bindingId: string,
    data: import("./types/payment").CreatePlanRequest
  ): Promise<import("./types/payment").PaymentPlan> {
    return request<import("./types/payment").PaymentPlan>(
      `/api/v1/channel-bindings/${bindingId}/payment-plans`,
      { method: "POST", body: JSON.stringify(data) },
      true
    );
  },

  async updatePaymentPlan(
    bindingId: string,
    planId: string,
    data: Partial<import("./types/payment").CreatePlanRequest>
  ): Promise<import("./types/payment").PaymentPlan> {
    return request<import("./types/payment").PaymentPlan>(
      `/api/v1/channel-bindings/${bindingId}/payment-plans/${planId}`,
      { method: "PUT", body: JSON.stringify(data) },
      true
    );
  },

  async deletePaymentPlan(bindingId: string, planId: string): Promise<void> {
    return request<void>(
      `/api/v1/channel-bindings/${bindingId}/payment-plans/${planId}`,
      { method: "DELETE" },
      true
    );
  },

  async listSubscriptions(
    bindingId: string,
    status?: string,
    limit = 50,
    offset = 0
  ): Promise<import("./types/payment").UserSubscription[]> {
    const params = new URLSearchParams({ limit: String(limit), offset: String(offset) });
    if (status) params.set("status", status);
    return request<import("./types/payment").UserSubscription[]>(
      `/api/v1/channel-bindings/${bindingId}/subscriptions?${params}`,
      {},
      true
    );
  },

  async updateSubscription(
    bindingId: string,
    externalUserId: string,
    data: import("./types/payment").UpdateSubscriptionRequest
  ): Promise<import("./types/payment").UserSubscription> {
    return request<import("./types/payment").UserSubscription>(
      `/api/v1/channel-bindings/${bindingId}/subscriptions/${encodeURIComponent(externalUserId)}`,
      { method: "PUT", body: JSON.stringify(data) },
      true
    );
  },

  async resetSubscriptionCounter(bindingId: string, externalUserId: string): Promise<void> {
    return request<void>(
      `/api/v1/channel-bindings/${bindingId}/subscriptions/${encodeURIComponent(externalUserId)}/reset`,
      { method: "POST" },
      true
    );
  },

  async listTransactions(
    bindingId: string,
    limit = 100
  ): Promise<import("./types/payment").PaymentTransaction[]> {
    return request<import("./types/payment").PaymentTransaction[]>(
      `/api/v1/channel-bindings/${bindingId}/transactions?limit=${limit}`,
      {},
      true
    );
  },

  async refundTransaction(txnId: string): Promise<{ ok: boolean }> {
    return request<{ ok: boolean }>(
      `/api/v1/transactions/${txnId}/refund`,
      { method: "POST" },
      true
    );
  },

  async simulateSandboxPayment(
    bindingId: string,
    data: import("./types/payment").SimulateSandboxPaymentRequest
  ): Promise<{ ok: boolean; sub: import("./types/payment").UserSubscription }> {
    return request<{ ok: boolean; sub: import("./types/payment").UserSubscription }>(
      `/api/v1/channel-bindings/${bindingId}/sandbox/simulate-payment`,
      { method: "POST", body: JSON.stringify(data) },
      true
    );
  },

  // ── Questionnaire (admin) ──────────────────────────────────────────────
  async getQuestionnaireTemplate(
    agentId: string
  ): Promise<import("./types/questionnaire").QuestionnaireResponsePayload> {
    return request<import("./types/questionnaire").QuestionnaireResponsePayload>(
      `/api/v1/admin/agents/${agentId}/questionnaire`,
      {},
      true
    );
  },

  async updateQuestionnaireTemplate(
    agentId: string,
    data: import("./types/questionnaire").UpsertQuestionnaireRequest
  ): Promise<import("./types/questionnaire").QuestionnaireTemplate> {
    return request<import("./types/questionnaire").QuestionnaireTemplate>(
      `/api/v1/admin/agents/${agentId}/questionnaire`,
      { method: "PUT", body: JSON.stringify(data) },
      true
    );
  },

  async listQuestionnaireSubmissions(
    agentId: string,
    params: {
      limit?: number;
      offset?: number;
      status?: import("./types/questionnaire").QuestionnaireSubmissionStatus;
      started_from?: string;
      started_to?: string;
      field_key?: string;
      value_search?: string;
      sort?: import("./types/questionnaire").QuestionnaireSubmissionSort;
      include_field_snapshot?: boolean;
    } = {}
  ): Promise<import("./types/questionnaire").QuestionnaireSubmissionListItem[]> {
    const qs = new URLSearchParams();
    if (params.limit != null) qs.set("limit", String(params.limit));
    if (params.offset != null) qs.set("offset", String(params.offset));
    if (params.status) qs.set("status", params.status);
    if (params.started_from) qs.set("started_from", params.started_from);
    if (params.started_to) qs.set("started_to", params.started_to);
    if (params.field_key) qs.set("field_key", params.field_key);
    if (params.value_search) qs.set("value_search", params.value_search);
    if (params.sort) qs.set("sort", params.sort);
    if (params.include_field_snapshot === true) qs.set("include_field_snapshot", "true");
    const suffix = qs.toString() ? `?${qs.toString()}` : "";
    return request<import("./types/questionnaire").QuestionnaireSubmissionListItem[]>(
      `/api/v1/admin/agents/${agentId}/questionnaire/submissions${suffix}`,
      {},
      true
    );
  },

  async listQuestionnaireResponseFieldKeys(agentId: string): Promise<string[]> {
    return request<string[]>(
      `/api/v1/admin/agents/${agentId}/questionnaire/response-field-keys`,
      {},
      true
    );
  },

  async getQuestionnaireSubmission(
    submissionId: string
  ): Promise<import("./types/questionnaire").QuestionnaireSubmissionDetail> {
    return request<import("./types/questionnaire").QuestionnaireSubmissionDetail>(
      `/api/v1/admin/questionnaires/submissions/${submissionId}`,
      {},
      true
    );
  },

  async getUserQuestionnaire(
    agentId: string,
    externalUserId: string
  ): Promise<import("./types/questionnaire").UserQuestionnaireDetail> {
    return request<import("./types/questionnaire").UserQuestionnaireDetail>(
      `/api/v1/admin/agents/${agentId}/questionnaire/user/${encodeURIComponent(externalUserId)}`,
      {},
      true
    );
  },
};

export { ApiError };

