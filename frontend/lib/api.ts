/** API client for backend communication. */

import { getAdminToken } from "./auth";
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
      
      // Handle authentication errors
      if (response.status === 401 || response.status === 403) {
        // Clear token on auth failure
        if (typeof window !== "undefined") {
          localStorage.removeItem("agent_admin_token");
        }
      }
      
      // Use status code as error code if error.error.code is not available
      const errorCode = error.error?.code || response.status.toString();
      const errorMessage = error.error?.message || error.detail || "An error occurred";
      
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

  // Admin endpoints
  async listConversations(params?: {
    agent_id?: string;
    status?: string;
    marketing_status?: string;
    crm_stage_id?: string;
    limit?: number;
  }): Promise<Conversation[]> {
    const queryParams = new URLSearchParams();
    if (params?.agent_id) queryParams.append("agent_id", params.agent_id);
    if (params?.status) queryParams.append("status", params.status);
    if (params?.marketing_status)
      queryParams.append("marketing_status", params.marketing_status);
    if (params?.crm_stage_id)
      queryParams.append("crm_stage_id", params.crm_stage_id);
    if (params?.limit) queryParams.append("limit", params.limit.toString());

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

  async sendAdminMessage(
    conversationId: string,
    adminId: string,
    content: string
  ): Promise<Message> {
    return request<Message>(
      `/api/v1/admin/conversations/${conversationId}/messages`,
      {
        method: "POST",
        body: JSON.stringify({ admin_id: adminId, content }),
      },
      true // require auth
    );
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
  }): Promise<{
    total_conversations: number;
    ai_active: number;
    needs_human: number;
    human_active: number;
    closed: number;
    marketing_new: number;
    marketing_booked: number;
    marketing_no_response: number;
    marketing_rejected: number;
    period: string;
    comparison?: {
      total_conversations: number;
      ai_active: number;
      needs_human: number;
      human_active: number;
      closed: number;
      marketing_new: number;
      marketing_booked: number;
      marketing_no_response: number;
      marketing_rejected: number;
    };
  }> {
    const queryParams = new URLSearchParams();
    if (params?.period) queryParams.append("period", params.period);
    if (params?.include_comparison !== undefined)
      queryParams.append("include_comparison", params.include_comparison.toString());

    return request(
      `/api/v1/admin/stats?${queryParams.toString()}`,
      {},
      true
    ); // require auth
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
      throw new ApiError(
        err.error?.code || res.status.toString(),
        err.error?.message || err.detail || "Failed to create folder"
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
    formData.append("file", file);
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
      throw new ApiError(
        err.error?.code || res.status.toString(),
        err.error?.message || err.detail || "Failed to upload document"
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
};

export { ApiError };

