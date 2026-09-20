import { create } from "zustand";

import { toApiError } from "@/api/client";
import { tutorApi, type TutorSendResult } from "@/api/tutor";
import type { TutorConversation, TutorMessage } from "@/types";
import type { LoadStatus } from "./useSpacesStore";

interface TutorState {
  /** Project owning every slice below. All data is keyed to it: switching
   * projects resets conversations/selection/messages immediately so Project
   * A state can never render under Project B (and late responses from A are
   * dropped by the per-call guards). */
  projectId: string | null;
  conversations: TutorConversation[];
  conversationsState: LoadStatus;
  activeId: string | null;
  messages: TutorMessage[];
  messagesState: LoadStatus;
  sendState: "idle" | "sending" | "error";
  lastExchange: TutorSendResult | null;
  error: string | null;
  /** Shared auto-create promise so StrictMode double-mounts create only once. */
  _ensureInflight: { projectId: string; task: Promise<void> } | null;
  fetchConversations: (projectId: string) => Promise<void>;
  ensureConversation: (projectId: string) => Promise<void>;
  createConversation: (projectId: string) => Promise<void>;
  selectConversation: (projectId: string, conversationId: string) => Promise<void>;
  sendMessage: (projectId: string, content: string) => Promise<void>;
  reset: () => void;
}

const initial = {
  projectId: null as string | null,
  conversations: [] as TutorConversation[],
  conversationsState: "idle" as LoadStatus,
  activeId: null as string | null,
  messages: [] as TutorMessage[],
  messagesState: "idle" as LoadStatus,
  sendState: "idle" as "idle" | "sending" | "error",
  lastExchange: null as TutorSendResult | null,
  error: null as string | null,
  _ensureInflight: null as { projectId: string; task: Promise<void> } | null,
};

/**
 * Enter a project's scope. Returns false when the caller must stop: the
 * store now belongs to another project. On project change the previous
 * project's slices are cleared synchronously — before any network response
 * — so stale conversations/messages are never visible under the new project.
 */
function enterScope(
  get: () => TutorState,
  set: (p: Partial<TutorState>) => void,
  projectId: string,
): boolean {
  if (get().projectId !== projectId) {
    set({ ...initial, projectId });
  }
  return get().projectId === projectId;
}

function newRequestKey(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) return crypto.randomUUID();
  return `${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

export const useTutorStore = create<TutorState>((set, get) => ({
  ...initial,

  fetchConversations: async (projectId) => {
    enterScope(get, set, projectId);
    set({ conversationsState: "loading", error: null });
    try {
      const conversations = await tutorApi.conversations(projectId);
      // Late response from a previous project: drop it, the current scope
      // already reset and may have loaded its own data.
      if (get().projectId !== projectId) return;
      set({ conversations, conversationsState: "ready" });
      // First visit starts a conversation so the composer is never dead.
      if (conversations.length === 0) {
        await get().ensureConversation(projectId);
      } else if (!get().activeId && conversations[0]) {
        await get().selectConversation(projectId, conversations[0].id);
      }
    } catch (e) {
      if (get().projectId !== projectId) return;
      set({ conversationsState: "error", error: toApiError(e).message });
    }
  },

  ensureConversation: async (projectId) => {
    enterScope(get, set, projectId);
    const inflight = get()._ensureInflight;
    if (inflight && inflight.projectId === projectId) {
      await inflight.task;
      return;
    }
    const task = (async () => {
      const conversation = await tutorApi.createConversation(projectId);
      if (get().projectId !== projectId) return;
      set((s) => ({
        conversations: [conversation, ...s.conversations],
        activeId: conversation.id,
        messages: [],
        messagesState: "ready" as LoadStatus,
        lastExchange: null,
      }));
    })();
    set({ _ensureInflight: { projectId, task } });
    try {
      await task;
    } catch (e) {
      if (get().projectId !== projectId) return;
      set({ conversationsState: "error", error: toApiError(e).message });
    } finally {
      if (get()._ensureInflight?.task === task) set({ _ensureInflight: null });
    }
  },

  createConversation: async (projectId) => {
    enterScope(get, set, projectId);
    set({ error: null });
    try {
      const conversation = await tutorApi.createConversation(projectId);
      if (get().projectId !== projectId) return;
      set((s) => ({
        conversations: [conversation, ...s.conversations],
        activeId: conversation.id,
        messages: [],
        messagesState: "ready",
        lastExchange: null,
      }));
    } catch (e) {
      if (get().projectId !== projectId) return;
      set({ conversationsState: "error", error: toApiError(e).message });
    }
  },

  selectConversation: async (projectId, conversationId) => {
    enterScope(get, set, projectId);
    set({ activeId: conversationId, messagesState: "loading", error: null, lastExchange: null });
    try {
      const messages = await tutorApi.messages(projectId, conversationId);
      // Stale selection/project guard: only apply if the user is still on it.
      if (get().projectId === projectId && get().activeId === conversationId) {
        set({ messages, messagesState: "ready" });
      }
    } catch (e) {
      if (get().projectId === projectId && get().activeId === conversationId) {
        set({ messagesState: "error", error: toApiError(e).message });
      }
    }
  },

  sendMessage: async (projectId, content) => {
    if (get().projectId !== projectId) return;
    const { activeId, sendState } = get();
    const text = content.trim();
    if (!activeId || !text || sendState === "sending") return;
    set({ sendState: "sending", error: null });
    try {
      // Fresh idempotency key per send: a retry after failure reuses it, a new
      // draft gets a new one, so double-submits collapse server-side.
      const exchange = await tutorApi.send(projectId, activeId, text, newRequestKey());
      if (get().projectId === projectId && get().activeId === activeId) {
        set({ lastExchange: exchange, sendState: "idle" });
        // Server is the source of truth: re-read history so the persisted user
        // message and assistant reply appear exactly once, in order.
        await get().selectConversation(projectId, activeId);
      }
    } catch (e) {
      if (get().projectId === projectId && get().activeId === activeId) {
        set({ sendState: "error", error: toApiError(e).message });
      }
    }
  },

  reset: () => set(initial),
}));
