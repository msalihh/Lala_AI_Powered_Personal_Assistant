"use client";

import React, { createContext, useContext, useRef, useEffect, useCallback } from "react";
import { getGenerationRun, GenerationRunStatus } from "@/lib/api";

// Store types
export interface NormalizedMessage {
  id: string;
  chatId: string;
  role: "user" | "assistant" | "system";
  content: string;
  createdAt: Date;
  status?: "streaming" | "completed" | "cancelled";
  sources?: SourceInfo[];
  used_documents?: boolean; // Whether documents were actually used (relevance gate passed)
  is_partial?: boolean; // Whether the message is still being streamed
  document_ids?: string[]; // For user messages: which documents were attached
  client_message_id?: string;
  attachments?: {
    id: string;
    filename: string;
    type: string;
    size: number;
    documentId?: string;
  }[];
  module?: string;
}

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

export interface Run {
  runId: string;
  requestId: string;
  chatId: string;
  assistantMessageId: string;
  status: "running" | "completed" | "cancelled" | "failed";
  startedAt: Date;
  lastSeq: number;
  abortController: AbortController;
  module?: string;
}

interface ChatData {
  messageIds: string[];
}

interface ChatStore {
  chats: Map<string, ChatData>;
  messages: Map<string, NormalizedMessage>;
  runs: Map<string, Run>;
}

interface ChatStoreContextType {
  store: React.MutableRefObject<ChatStore>;
  getChatMessageIds: (chatId: string) => string[];
  getMessage: (messageId: string) => NormalizedMessage | undefined;
  getChatMessagesFromStore: (chatId: string) => NormalizedMessage[];
  addMessage: (message: NormalizedMessage) => void;
  updateMessage: (messageId: string, updates: Partial<NormalizedMessage>) => void;
  getRun: (runId: string) => Run | undefined;
  getRunByRequestId: (requestId: string) => Run | undefined;
  addRun: (run: Run) => void;
  updateRun: (runId: string, updates: Partial<Run>) => void;
  removeRun: (runId: string) => void;
  getActiveRuns: () => Run[];
}

const ChatStoreContext = createContext<ChatStoreContextType | null>(null);

export function ChatStoreProvider({ children }: { children: React.ReactNode }) {
  const storeRef = useRef<ChatStore>({
    chats: new Map(),
    messages: new Map(),
    runs: new Map(),
  });

  // Store helper functions
  const getChatMessageIds = useCallback((chatId: string): string[] => {
    const chat = storeRef.current.chats.get(chatId);
    return chat ? [...chat.messageIds] : [];
  }, []);

  const getMessage = useCallback((messageId: string): NormalizedMessage | undefined => {
    return storeRef.current.messages.get(messageId);
  }, []);

  const getChatMessagesFromStore = useCallback((chatId: string): NormalizedMessage[] => {
    const messageIds = getChatMessageIds(chatId);
    return messageIds
      .map(id => getMessage(id))
      .filter((msg): msg is NormalizedMessage => msg !== undefined)
      .sort((a, b) => a.createdAt.getTime() - b.createdAt.getTime());
  }, [getChatMessageIds, getMessage]);

  const addMessage = useCallback((message: NormalizedMessage) => {
    const existingMessage = storeRef.current.messages.get(message.id);
    if (existingMessage) {
      return;
    }

    storeRef.current.messages.set(message.id, message);
    const chat = storeRef.current.chats.get(message.chatId);
    if (chat) {
      if (!chat.messageIds.includes(message.id)) {
        chat.messageIds.push(message.id);
      }
    } else {
      storeRef.current.chats.set(message.chatId, { messageIds: [message.id] });
    }
  }, []);

  const updateMessage = useCallback((messageId: string, updates: Partial<NormalizedMessage>) => {
    const message = storeRef.current.messages.get(messageId);
    if (message) {
      storeRef.current.messages.set(messageId, { ...message, ...updates });
    }
  }, []);

  const getRun = useCallback((runId: string): Run | undefined => {
    return storeRef.current.runs.get(runId);
  }, []);

  const getRunByRequestId = useCallback((requestId: string): Run | undefined => {
    for (const run of storeRef.current.runs.values()) {
      if (run.requestId === requestId) {
        return run;
      }
    }
    return undefined;
  }, []);

  const addRun = useCallback((run: Run) => {
    storeRef.current.runs.set(run.runId, run);
    // Save to localStorage for persistence across page navigations
    try {
      const activeRuns = Array.from(storeRef.current.runs.values())
        .filter(r => r.status === "running")
        .map(r => r.runId);
      localStorage.setItem("active_runs", JSON.stringify(activeRuns));
    } catch (error) {
      console.error("Failed to save active runs:", error);
    }
  }, []);

  const updateRun = useCallback((runId: string, updates: Partial<Run>) => {
    const run = storeRef.current.runs.get(runId);
    if (run) {
      const updatedRun = { ...run, ...updates };
      // CRITICAL: If the runId inside the object is being updated, we must sync the Map key
      // otherwise removeRun(newId) will fail because the key is still the oldId.
      if (updates.runId && updates.runId !== runId) {
        storeRef.current.runs.delete(runId);
        storeRef.current.runs.set(updates.runId, updatedRun);
      } else {
        storeRef.current.runs.set(runId, updatedRun);
      }

      // Update localStorage
      try {
        const activeRuns = Array.from(storeRef.current.runs.values())
          .filter(r => r.status === "running")
          .map(r => r.runId);
        localStorage.setItem("active_runs", JSON.stringify(activeRuns));
      } catch (error) {
        console.error("Failed to save active runs:", error);
      }
    }
  }, []);

  const removeRun = useCallback((runId: string) => {
    const run = storeRef.current.runs.get(runId);
    const chatId = run?.chatId;

    storeRef.current.runs.delete(runId);

    // Update localStorage
    try {
      const activeRuns = Array.from(storeRef.current.runs.values())
        .filter(r => r.status === "running")
        .map(r => r.runId);
      localStorage.setItem("active_runs", JSON.stringify(activeRuns));
    } catch (error) {
      console.error("Failed to save active runs:", error);
    }

    // CRITICAL: Dispatch event to notify page.tsx that run was removed
    // This allows page.tsx to call finalizeRun and reset isLoading state
    if (chatId && typeof window !== "undefined") {
      const event = new CustomEvent("runRemoved", {
        detail: { runId, chatId }
      });
      window.dispatchEvent(event);
    }
  }, []);

  const getActiveRuns = useCallback((): Run[] => {
    return Array.from(storeRef.current.runs.values()).filter(r => r.status === "running");
  }, []);

  // Global polling mechanism for all active runs
  // CRITICAL: Continue polling even when tab is hidden/background
  useEffect(() => {
    let pollInterval: NodeJS.Timeout | null = null;

    const pollActiveRuns = async () => {
      const activeRuns = getActiveRuns();

      if (activeRuns.length === 0) {
        return;
      }

      // Poll each active run
      // NOTE: Only poll runs that exist in backend (skip frontend-only runs)
      for (const run of activeRuns) {
        try {
          // Skip polling if run was created locally (frontend-only)
          // Frontend-only runs start with "run_" prefix (e.g., "run_1234567890_abc")
          // Backend runs use client_message_id (UUID format, e.g., "7214b743-c6eb-42a3-8158-924d2300e7bc")
          // Check if runId is a frontend-only run (starts with "run_")
          if (run.runId.startsWith("run_")) {
            // This is a frontend-only run, skip backend polling
            // The run will be updated directly when response arrives
            continue;
          }

          // This is a backend run (UUID format), poll it
          // CRITICAL: Use keepalive to continue even when tab is hidden
          const runStatus = await getGenerationRun(run.runId);

          // CRITICAL: Backend uses content_so_far, not completed_text/partial_text
          const content = runStatus.content_so_far || runStatus.completed_text || runStatus.partial_text || "";

          if (runStatus.status === "completed" && content) {
            // CRITICAL: Run is completed, but message is only completed if it's persisted in DB
            // Backend ensures message is saved to DB before run is marked as completed
            // So we can safely mark message as completed here
            const existingMessage = getMessage(run.assistantMessageId);
            if (existingMessage) {
              // CRITICAL: Only mark as completed if we have full content
              // This ensures message lifecycle is correct
              updateMessage(run.assistantMessageId, {
                content: content,
                status: "completed", // Message is completed because run is completed (DB write already happened)
              });
            } else {
              // CRITICAL: If message doesn't exist in store, create it
              // This can happen if tab was hidden when message was created
              console.warn(`[POLLING] Message ${run.assistantMessageId} not found in store for completed run ${run.runId}, creating it`);
              addMessage({
                id: run.assistantMessageId,
                chatId: run.chatId,
                role: "assistant",
                content: content,
                createdAt: new Date(),
                status: "completed", // Message is completed because run is completed (DB write already happened)
                module: run.module,
              });
            }

            // CRITICAL: Remove run from store when completed (not just update status)
            // This ensures isLoading state is correctly updated to false
            // Message persists independently of run
            removeRun(run.runId);
          } else if (runStatus.status === "failed" || runStatus.status === "cancelled") {
            // CRITICAL: Remove run from store when failed/cancelled (not just update status)
            // This ensures isLoading state is correctly updated to false
            removeRun(run.runId);
          } else if (runStatus.status === "running" && content) {
            // Update partial text if available
            const existingMessage = getMessage(run.assistantMessageId);
            if (existingMessage) {
              // Only update if content is longer (to avoid overwriting with older data)
              if (content.length > existingMessage.content.length) {
                updateMessage(run.assistantMessageId, {
                  content: content,
                  status: "streaming",
                });
              }
            } else {
              // CRITICAL: If message doesn't exist in store, create it
              // This can happen if tab was hidden when message was created
              console.warn(`[POLLING] Message ${run.assistantMessageId} not found in store for running run ${run.runId}, creating it`);
              addMessage({
                id: run.assistantMessageId,
                chatId: run.chatId,
                role: "assistant",
                content: content,
                createdAt: new Date(),
                status: "streaming",
                module: run.module,
              });
            }
          }
        } catch (error: any) {
          if (error && typeof error === "object" && "code" in error && error.code === "RUN_NOT_FOUND") {
            // Run not found - remove from store
            removeRun(run.runId);
          } else {
            console.error(`[BACKGROUND] Error polling run ${run.runId}:`, error);
          }
        }
      }
    };

    // Start polling every 250ms for faster, smoother updates
    // CRITICAL: Continue polling even when tab is hidden
    // Use setInterval which works in background (though may be throttled)
    pollInterval = setInterval(() => {
      // Always poll, regardless of tab visibility
      pollActiveRuns();
    }, 250);

    // Also poll immediately
    pollActiveRuns();

    // CRITICAL: Add visibility change listener to ensure polling continues
    // Even if browser throttles setInterval, we ensure polling happens when tab becomes visible
    const handleVisibilityChange = () => {
      if (!document.hidden) {
        // Tab became visible - poll immediately
        pollActiveRuns();
      }
      // Continue polling regardless of visibility
    };

    document.addEventListener("visibilitychange", handleVisibilityChange);

    return () => {
      document.removeEventListener("visibilitychange", handleVisibilityChange);
      if (pollInterval) {
        clearInterval(pollInterval);
      }
    };
  }, [getActiveRuns, getMessage, updateMessage, updateRun, removeRun, addMessage]);

  // Restore active runs from localStorage on mount
  useEffect(() => {
    try {
      const savedActiveRuns = localStorage.getItem("active_runs");
      if (savedActiveRuns) {
        const runIds: string[] = JSON.parse(savedActiveRuns);
        // Note: We don't restore the full run objects here because they contain AbortController
        // which can't be serialized. The runs will be recreated when the chat page loads.
        // This is just for tracking which runs are active.
      }
    } catch (error) {
      console.error("Failed to restore active runs:", error);
    }
  }, []);

  const value: ChatStoreContextType = {
    store: storeRef,
    getChatMessageIds,
    getMessage,
    getChatMessagesFromStore,
    addMessage,
    updateMessage,
    getRun,
    getRunByRequestId,
    addRun,
    updateRun,
    removeRun,
    getActiveRuns,
  };

  return (
    <ChatStoreContext.Provider value={value}>
      {children}
    </ChatStoreContext.Provider>
  );
}

export function useChatStore() {
  const context = useContext(ChatStoreContext);
  if (!context) {
    throw new Error("useChatStore must be used within ChatStoreProvider");
  }
  return context;
}

