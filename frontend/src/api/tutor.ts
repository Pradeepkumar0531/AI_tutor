import { apiClient } from "./client";
import type { Page, TutorCitation, TutorConversation, TutorMessage } from "@/types";

interface BackendConversation {
  id: string;
  project_id: string;
  title: string;
  created_at: string;
  updated_at: string;
}

interface BackendMessage {
  id: string;
  conversation_id: string;
  role: "USER" | "ASSISTANT";
  content: string;
  model: string | null;
  created_at: string;
  citations: TutorCitation[];
  grounded: boolean;
  insufficient_evidence: boolean;
}

export interface TutorSendResult {
  conversationId: string;
  message: TutorMessage;
  citations: TutorCitation[];
  grounded: boolean;
  insufficientEvidence: boolean;
}

interface BackendSendResponse {
  conversation_id: string;
  message: BackendMessage;
  citations: TutorCitation[];
  grounded: boolean;
  insufficient_evidence: boolean;
}

function toConversation(c: BackendConversation): TutorConversation {
  return {
    id: c.id,
    projectId: c.project_id,
    title: c.title,
    createdAt: c.created_at,
    updatedAt: c.updated_at,
  };
}

function toMessage(m: BackendMessage): TutorMessage {
  return {
    id: m.id,
    conversationId: m.conversation_id,
    role: m.role,
    content: m.content,
    model: m.model,
    createdAt: m.created_at,
    citations: m.citations ?? [],
    grounded: m.grounded ?? false,
    insufficientEvidence: m.insufficient_evidence ?? false,
  };
}

export const tutorApi = {
  async conversations(projectId: string): Promise<TutorConversation[]> {
    const res = await apiClient.get<BackendConversation[]>(
      `/api/v1/projects/${projectId}/conversations`,
    );
    return res.data.map(toConversation);
  },

  async createConversation(projectId: string, title?: string): Promise<TutorConversation> {
    const res = await apiClient.post<BackendConversation>(
      `/api/v1/projects/${projectId}/conversations`,
      { title: title ?? null },
    );
    return toConversation(res.data);
  },

  async messages(projectId: string, conversationId: string): Promise<TutorMessage[]> {
    const res = await apiClient.get<Page<BackendMessage>>(
      `/api/v1/projects/${projectId}/conversations/${conversationId}/messages`,
      { params: { limit: 100 } },
    );
    return res.data.items.map(toMessage);
  },

  async send(
    projectId: string,
    conversationId: string,
    content: string,
    requestKey: string,
  ): Promise<TutorSendResult> {
    // Grounded Tutor generation is one retrieval + one reasoning-model call,
    // measured live at ~1.6–3.6s typical — but the backend tolerates up to
    // 60s per provider call (groq_timeout_seconds) plus one bounded retry, so
    // a legitimate tail request can outlive the shared 15s client default.
    // Aborting first would fake a failure AFTER the server persisted both
    // messages, and the retry (fresh request key) would duplicate the
    // question. This route therefore carries the backend's own 60s bound
    // instead of the global default. Nothing else changes.
    const res = await apiClient.post<BackendSendResponse>(
      `/api/v1/projects/${projectId}/conversations/${conversationId}/messages`,
      { content, request_key: requestKey },
      { timeout: 60000 },
    );
    return {
      conversationId: res.data.conversation_id,
      message: toMessage(res.data.message),
      citations: res.data.citations,
      grounded: res.data.grounded,
      insufficientEvidence: res.data.insufficient_evidence,
    };
  },
};
