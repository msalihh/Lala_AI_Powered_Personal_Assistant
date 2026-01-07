/**
 * Centralized API client - All requests go through /api/* (Next.js proxy)
 * NO direct calls to http://localhost:8000 - everything goes through /api/*
 */

// API_BASE_URL is empty - all requests are relative to current origin
const API_BASE_URL = "";

export interface ApiError {
  detail: string;
  code: string;
}

/**
 * Get authentication token from localStorage.
 */
function getAuthToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem("auth_token");
}

/**
 * Centralized fetch wrapper with error handling and auth token injection.
 * All requests MUST go through /api/* (Next.js proxy handles routing to backend)
 */
export async function apiFetch<T>(
  path: string,
  options: RequestInit = {}
): Promise<T> {
  // Build URL: all requests go through /api/* (Next.js proxy)
  // If path already starts with /api/, use it as-is
  // Otherwise, prepend /api
  let url: string;
  if (path.startsWith("http://") || path.startsWith("https://")) {
    url = path;
  } else if (path.startsWith("/api/")) {
    url = path;
  } else {
    url = `/api${path.startsWith("/") ? path : `/${path}`}`;
  }

  const token = getAuthToken();
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(options.headers as Record<string, string>),
  };

  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }

  try {
    const response = await fetch(url, {
      ...options,
      headers,
      signal: options.signal, // Pass AbortSignal if provided (only for user-initiated stop)
      keepalive: true, // BACKGROUND PROCESSING: Continue even if page closes/tab switches
    });

    if (response.status === 204) {
      return {} as T;
    }

    // Try to parse JSON, but handle non-JSON responses
    let data: any;
    const contentType = response.headers.get("content-type");

    // Clone response to read text without consuming the stream
    const responseClone = response.clone();
    const text = await responseClone.text();

    // Log raw response for debugging (if error)
    if (typeof window !== "undefined" && !response.ok) {
      console.error("[API Raw Response]", {
        url,
        status: response.status,
        contentType,
        text: text.substring(0, 500), // First 500 chars
      });
    }

    try {
      if (text) {
        data = JSON.parse(text);
      } else {
        data = {};
      }
    } catch (parseError) {
      // Response is not JSON
      if (typeof window !== "undefined") {
        console.error("[API Parse Error]", {
          url,
          status: response.status,
          contentType,
          parseError,
          responseText: text.substring(0, 500),
        });
      }

      if (!response.ok) {
        throw {
          detail: `Backend hatası (Status: ${response.status}). Response JSON değil: ${text.substring(0, 200)}. Backend terminal'indeki hata mesajını kontrol edin.`,
          code: "INVALID_RESPONSE",
        } as ApiError;
      }

      // If response is OK but not JSON, return empty object
      return {} as T;
    }

    if (!response.ok) {
      // Log full error details for debugging
      if (typeof window !== "undefined") {
        console.error("[API Error Response]", {
          url,
          status: response.status,
          statusText: response.statusText,
          data,
          headers: Object.fromEntries(response.headers.entries()),
        });
      }

      const error: ApiError = {
        detail: data.detail || data.message || `Backend hatası (Status: ${response.status})`,
        code: data.code || "UNKNOWN_ERROR",
      };
      throw error;
    }

    return data as T;
  } catch (error) {
    if (typeof window !== "undefined") {
      console.error("[API Error]", {
        url,
        method: options.method || "GET",
        error: error instanceof Error ? error.message : String(error),
        errorObject: error,
      });
    }

    if (error instanceof TypeError && error.message === "Failed to fetch") {
      throw {
        detail: `Backend'e bağlanılamadı. Backend çalışıyor mu? /api/health kontrol edin.`,
        code: "NETWORK_ERROR",
      } as ApiError;
    }

    // If error is already an ApiError, re-throw it
    if (error && typeof error === "object" && "detail" in error && "code" in error) {
      throw error;
    }

    // Log the actual error for debugging
    const errorMessage = error instanceof Error ? error.message : String(error);
    throw {
      detail: `Beklenmeyen hata: ${errorMessage}. Console'u kontrol edin.`,
      code: "UNKNOWN_ERROR",
    } as ApiError;
  }
}

// User identity interface
export interface UserResponse {
  id: string;
  username: string;
  email: string | null;
  is_active: boolean;
  created_at: string;
  avatar_url?: string | null;
}

// Document API interfaces
export interface DocumentUploadResponse {
  documentId: string;
  filename: string;
  size: number;
  text_length?: number;  // Extracted text length (0 if empty)
  text_has_content?: boolean;  // True if text_content is not empty
  status?: string;  // "processing" or "ready"
  truncated?: boolean;  // True if text was truncated due to size limits
  indexing_success?: boolean;  // True if RAG indexing completed successfully
  indexing_chunks?: number;  // Number of chunks successfully indexed
  indexing_failed_chunks?: number;  // Number of chunks that failed indexing
  indexing_duration_ms?: number;  // Indexing duration in milliseconds
}

export interface DocumentListItem {
  file_type?: string;
  id: string;
  filename: string;
  mime_type: string;
  size: number;
  created_at: string;
  source: string;
  is_chat_scoped?: boolean;
  uploaded_from_chat_id?: string;
  uploaded_from_chat_title?: string;
  is_main?: boolean;
}

export interface DocumentDetail {
  id: string;
  filename: string;
  mime_type: string;
  size: number;
  text_content: string;
  created_at: string;
  source: string;
  is_chat_scoped?: boolean;
  uploaded_from_chat_id?: string;
  uploaded_from_chat_title?: string;
  is_main?: boolean;
}

/**
 * Upload a document file.
 */
export async function uploadDocument(
  file: File,
  chatId?: string,
  chatTitle?: string,
  promptModule?: "none" | "lgs_karekok",
  signal?: AbortSignal
): Promise<DocumentUploadResponse> {
  const token = getAuthToken();
  if (!token) {
    throw {
      detail: "Giriş yapmanız gerekiyor",
      code: "UNAUTHORIZED",
    } as ApiError;
  }

  const formData = new FormData();
  formData.append("file", file);
  if (chatId) {
    formData.append("chat_id", chatId);
  }
  if (chatTitle) {
    formData.append("chat_title", chatTitle);
  }
  if (promptModule) {
    formData.append("prompt_module", promptModule);
  }

  const url = "/api/documents/upload";


  try {
    const response = await fetch(url, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${token}`,
        // Don't set Content-Type - browser will set it with boundary for FormData
      },
      body: formData,
      signal: signal, // Abort signal for cancellation
    });

    if (response.status === 204) {
      return {} as DocumentUploadResponse;
    }

    const contentType = response.headers.get("content-type");
    const text = await response.text();

    if (typeof window !== "undefined" && !response.ok) {
      console.error("[API Raw Response]", {
        url,
        status: response.status,
        contentType,
        text: text.substring(0, 500),
      });
    }

    let data: any;
    try {
      if (text) {
        data = JSON.parse(text);
      } else {
        data = {};
      }
    } catch (parseError) {
      if (!response.ok) {
        throw {
          detail: `Backend hatası (Status: ${response.status}). Response JSON değil: ${text.substring(0, 200)}.`,
          code: "INVALID_RESPONSE",
        } as ApiError;
      }
      return {} as DocumentUploadResponse;
    }

    if (!response.ok) {
      const error: ApiError = {
        detail: data.detail || data.message || `Backend hatası (Status: ${response.status})`,
        code: data.code || "UNKNOWN_ERROR",
      };
      throw error;
    }

    return data as DocumentUploadResponse;
  } catch (error) {
    // AbortError'ı yakala ve sessizce çık (iptal edilmiş yükleme)
    if (error instanceof Error && error.name === "AbortError") {
      throw {
        detail: "Yükleme iptal edildi",
        code: "ABORTED",
      } as ApiError;
    }

    if (typeof window !== "undefined") {
      console.error("[API Error]", {
        url,
        method: "POST",
        error: error instanceof Error ? error.message : String(error),
        errorObject: error,
      });
    }

    if (error instanceof TypeError && error.message === "Failed to fetch") {
      throw {
        detail: `Backend'e bağlanılamadı. Backend çalışıyor mu? /api/health kontrol edin.`,
        code: "NETWORK_ERROR",
      } as ApiError;
    }

    if (error && typeof error === "object" && "detail" in error && "code" in error) {
      throw error;
    }

    const errorMessage = error instanceof Error ? error.message : String(error);
    throw {
      detail: `Beklenmeyen hata: ${errorMessage}. Console'u kontrol edin.`,
      code: "UNKNOWN_ERROR",
    } as ApiError;
  }
}

/**
 * List all documents for the current user.
 */
/**
 * List all documents for the current user.
 * @param prompt_module Optional: filter documents by module ("none" | "lgs_karekok")
 */
export async function listDocuments(prompt_module?: "none" | "lgs_karekok"): Promise<DocumentListItem[]> {
  const params = prompt_module ? `?prompt_module=${prompt_module}` : "";
  return apiFetch<DocumentListItem[]>(`/api/documents${params}`);
}

/**
 * Get document details including text content.
 */
export async function getDocument(id: string): Promise<DocumentDetail> {
  return apiFetch<DocumentDetail>(`/api/documents/${id}`);
}

// Source info from backend
export interface SourceInfo {
  documentId: string;
  filename: string;
  chunkIndex: number;
  score: number;
  preview: string;
  source_type?: "document" | "email";
  sender?: string;
  subject?: string;
  date?: string;
}

// Chat management interfaces
export interface ChatListItem {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
}

export interface ChatDetail {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
  user_id: string;
  prompt_module?: "none" | "lgs_karekok";
}

export interface CreateChatRequest {
  title?: string;
  prompt_module?: "none" | "lgs_karekok";
}

/**
 * Create a new chat for the current user.
 */
export async function createChat(title?: string, prompt_module?: "none" | "lgs_karekok"): Promise<ChatDetail> {
  return apiFetch<ChatDetail>("/api/chats", {
    method: "POST",
    body: JSON.stringify({ title, prompt_module: prompt_module || "none" } as CreateChatRequest),
  });
}

/**
 * List all chats for the current user (user-scoped).
 * @param prompt_module Optional: filter chats by module ("none" | "lgs_karekok")
 */
export async function listChats(prompt_module?: "none" | "lgs_karekok"): Promise<ChatListItem[]> {
  const params = prompt_module ? `?prompt_module=${prompt_module}` : "";
  return apiFetch<ChatListItem[]>(`/api/chats${params}`);
}

/**
 * List all archived chats for the current user.
 */
export async function listArchivedChats(): Promise<ChatListItem[]> {
  return apiFetch<ChatListItem[]>("/api/chats/archived");
}

/**
 * Get a specific chat with ownership verification.
 */
export async function getChat(chatId: string): Promise<ChatDetail> {
  return apiFetch<ChatDetail>(`/api/chats/${chatId}`);
}

/**
 * Update a chat title (ChatGPT style: title is set only once from first message).
 */
export async function updateChatTitle(chatId: string, title: string): Promise<ChatDetail> {
  return apiFetch<ChatDetail>(`/api/chats/${chatId}`, {
    method: "PATCH",
    body: JSON.stringify({ title }),
  });
}

/**
 * Archive or unarchive a chat.
 */
export async function archiveChat(chatId: string, archived: boolean): Promise<ChatDetail> {
  return apiFetch<ChatDetail>(`/api/chats/${chatId}`, {
    method: "PATCH",
    body: JSON.stringify({ archived }),
  });
}

/**
 * Delete a chat with cascade delete of messages.
 */
export async function deleteChat(chatId: string, deleteDocuments?: boolean): Promise<void> {
  const params = new URLSearchParams();
  if (deleteDocuments !== undefined) {
    params.append("delete_documents", deleteDocuments.toString());
  }
  const queryString = params.toString();
  const url = `/api/chats/${chatId}${queryString ? `?${queryString}` : ""}`;
  return apiFetch<void>(url, {
    method: "DELETE",
  });
}

/**
 * Get user settings.
 */
export interface UserSettings {
  delete_chat_documents_on_chat_delete: boolean;
}

export async function getUserSettings(): Promise<UserSettings> {
  return apiFetch<UserSettings>("/api/user/settings", {
    method: "GET",
  });
}

/**
 * Update user settings.
 */
export async function updateUserSettings(settings: UserSettings): Promise<UserSettings> {
  return apiFetch<UserSettings>("/api/user/settings", {
    method: "PUT",
    body: JSON.stringify(settings),
  });
}

/**
 * Get messages for a specific chat with cursor-based pagination.
 */
export interface ChatMessage {
  message_id: string;
  role: "user" | "assistant" | "system";
  content: string;
  created_at: string;
  sources?: SourceInfo[];
  document_ids?: string[];  // For user messages: which documents were attached
  used_documents?: boolean;  // For assistant messages: whether documents were used
  is_partial?: boolean;  // For assistant messages: whether message is partial (streaming/cancelled)
  client_message_id?: string;
}

export interface ChatMessagesResponse {
  messages: ChatMessage[];
  cursor?: string | null;
  has_more: boolean;
}

export async function getChatMessages(
  chatId: string,
  limit: number = 50,
  cursor?: string | null
): Promise<ChatMessagesResponse> {
  const params = new URLSearchParams();
  params.append("limit", limit.toString());
  if (cursor) {
    params.append("cursor", cursor);
  }
  return apiFetch<ChatMessagesResponse>(`/api/chats/${chatId}/messages?${params.toString()}`);
}

/**
 * Send a message (no chat saving - direct to /api/chat endpoint).
 */
export interface SendChatMessageRequest {
  message: string;
  documentIds?: string[];
  useDocuments?: boolean;
  client_message_id: string;
  mode?: "qa" | "summarize" | "extract";
  chatId?: string;  // Optional, not used for saving
  response_style?: "short" | "medium" | "long" | "detailed" | "auto";  // Response length style (optional, auto-detected if not provided)
  prompt_module?: "none" | "lgs_karekok";  // Specialized module prompt (none = general assistant, lgs_karekok = LGS Math module)
}

export interface SendChatMessageResponse {
  message: string;
  role: string;
  sources?: SourceInfo[];
  used_documents?: boolean;
  debug_info?: {
    run_id?: string;
    message_id?: string;
    streaming?: boolean;
    [key: string]: any;
  };
}

export async function sendChatMessage(
  chatId: string | null,
  request: SendChatMessageRequest
): Promise<SendChatMessageResponse> {
  // Use /api/chat endpoint (chat saving enabled)
  return apiFetch<SendChatMessageResponse>("/api/chat", {
    method: "POST",
    body: JSON.stringify({
      message: request.message,
      documentIds: request.documentIds,
      useDocuments: request.useDocuments || false,
      client_message_id: request.client_message_id,
      mode: request.mode || "qa",
      chatId: chatId || request.chatId || undefined,  // Use provided chatId or request.chatId
      response_style: request.response_style && request.response_style !== "auto" ? request.response_style : undefined,
      prompt_module: request.prompt_module,
    }),
  });
}

/**
 * Delete a document.
 */
export async function deleteDocument(id: string): Promise<void> {
  await apiFetch<void>(`/api/documents/${id}`, {
    method: "DELETE",
  });
}

/**
 * Delete all documents uploaded from a chat (cascade delete).
 */
export async function deleteChatDocuments(chatId: string): Promise<{ deleted_documents: number; deleted_vectors: number }> {
  return apiFetch<{ deleted_documents: number; deleted_vectors: number }>(`/api/documents/chat/${chatId}`, {
    method: "DELETE",
  });
}

/**
 * Toggle independent document "Main" status.
 */
export async function toggleMainDocument(id: string): Promise<DocumentListItem> {
  return apiFetch<DocumentListItem>(`/api/documents/${id}/toggle-main`, {
    method: "PATCH",
  });
}

// Generation run interfaces (for background processing)
export interface GenerationRunStatus {
  run_id: string;
  chat_id: string;
  message_id: string;
  status: "running" | "completed" | "failed" | "cancelled";
  content_so_far?: string; // Backend uses content_so_far (not partial_text/completed_text)
  partial_text?: string; // Legacy field, map from content_so_far
  completed_text?: string; // Legacy field, map from content_so_far when status is completed
  sources?: SourceInfo[];
  used_documents?: boolean;
  created_at: string;
  updated_at: string;
  error?: string;
}

/**
 * Get generation run status (for polling).
 */
export async function getGenerationRun(runId: string): Promise<GenerationRunStatus> {
  return apiFetch<GenerationRunStatus>(`/api/chat/runs/${runId}`);
}

/**
 * Cancel a running generation.
 */
export async function cancelGenerationRun(runId: string): Promise<void> {
  return apiFetch<void>(`/api/chat/runs/${runId}/cancel`, {
    method: "POST",
  });
}

/**
 * Exchange Google ID token for our backend JWT.
 * Called after successful Google OAuth sign-in via NextAuth.
 */
export async function exchangeGoogleToken(idToken: string): Promise<{ access_token: string }> {
  // Use /api/google-auth instead of /api/auth/google to avoid conflict with NextAuth route handler
  return apiFetch<{ access_token: string }>("/api/google-auth", {
    method: "POST",
    body: JSON.stringify({
      id_token: idToken,
    }),
  });
}

/**
 * Update user avatar.
 */
export async function updateAvatar(avatarData: string): Promise<UserResponse> {
  return apiFetch<UserResponse>("/api/me/avatar", {
    method: "PUT",
    body: JSON.stringify({
      avatar: avatarData,
    }),
  });
}

/**
 * Gmail Integration APIs
 */
export interface GmailStatus {
  is_connected: boolean;
  email?: string;
  last_sync_at?: string;
  sync_status: string;
}

export interface GmailSyncResult {
  status: string;
  emails_fetched: number;
  emails_indexed: number;
  duration_ms: number;
}

export const getGmailConnectUrl = async (): Promise<{ auth_url: string }> => {
  return apiFetch<{ auth_url: string }>('/api/integrations/gmail/connect');
};

export const handleGmailCallback = async (code: string, state: string): Promise<{ status: string; email: string }> => {
  return apiFetch<{ status: string; email: string }>(`/api/integrations/gmail/callback?code=${code}&state=${state}`);
};

export const getGmailStatus = async (): Promise<GmailStatus> => {
  return apiFetch<GmailStatus>('/api/integrations/gmail/status');
};

export const syncGmail = async (): Promise<GmailSyncResult> => {
  return apiFetch<GmailSyncResult>('/api/integrations/gmail/sync', {
    method: 'POST',
  });
};


export const listEmails = async (): Promise<any[]> => {
  return apiFetch<any[]>('/api/integrations/gmail/emails');
};

export const listGmailMessages = async (query: string = '', max: number = 50): Promise<{ messages: any[] }> => {
  const params = new URLSearchParams();
  if (query) params.append('query', query);
  params.append('max', max.toString());
  return apiFetch<{ messages: any[] }>(`/api/integrations/gmail/messages?${params.toString()}`);
};

export const getGmailMessage = async (messageId: string): Promise<any> => {
  return apiFetch<any>(`/api/integrations/gmail/messages/${messageId}`);
};

export const disconnectGmail = async (): Promise<{ status: string; message: string }> => {
  return apiFetch<{ status: string; message: string }>('/api/integrations/gmail/disconnect', {
    method: 'POST',
  });
};

