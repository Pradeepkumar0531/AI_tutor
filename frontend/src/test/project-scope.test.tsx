import { act, renderHook } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi, type Mock } from "vitest";

// Only HTTP boundaries are mocked; mapping, stores, and hooks run for real.
vi.mock("@/api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/api/client")>();
  return {
    ...actual,
    apiClient: { get: vi.fn(), post: vi.fn(), put: vi.fn(), delete: vi.fn() },
  };
});
vi.mock("@/api/tutor", () => ({
  tutorApi: {
    conversations: vi.fn(),
    createConversation: vi.fn(),
    messages: vi.fn(),
    send: vi.fn(),
  },
}));
vi.mock("@/api/assessment", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/api/assessment")>();
  return { ...actual, assessmentApi: { ...actual.assessmentApi } };
});
vi.mock("@/api/knowledge", () => ({
  knowledgeApi: {
    status: vi.fn(),
    concepts: vi.fn(),
    concept: vi.fn(),
    search: vi.fn(),
    reprocess: vi.fn(),
  },
}));

import { apiClient } from "@/api/client";
import { assessmentApi } from "@/api/assessment";
import { tutorApi } from "@/api/tutor";
import { useAssessmentStore } from "@/stores/useAssessmentStore";
import { useTutorStore } from "@/stores/useTutorStore";

const mockTutorConversations = tutorApi.conversations as Mock;
const mockTutorMessages = tutorApi.messages as Mock;
const mockPost = apiClient.post as Mock;

function reset() {
  useTutorStore.getState().reset();
  useAssessmentStore.getState().reset();
  vi.clearAllMocks();
  vi.useRealTimers();
}

const convA = {
  id: "conv-a",
  projectId: "proj-a",
  title: "A chat",
  createdAt: "",
  updatedAt: "",
};
const convB = {
  id: "conv-b",
  projectId: "proj-b",
  title: "B chat",
  createdAt: "",
  updatedAt: "",
};
const msgA = {
  id: "m-a",
  conversationId: "conv-a",
  role: "USER" as const,
  content: "A1 secret question",
  model: null,
  createdAt: "",
  citations: [],
  grounded: false,
  insufficientEvidence: false,
};

describe("tutor store project scope", () => {
  beforeEach(reset);

  it("clears Project A state synchronously when Project B loads", async () => {
    mockTutorConversations.mockImplementation(async (pid: string) =>
      pid === "proj-a" ? [convA] : [convB],
    );
    mockTutorMessages.mockImplementation(async (_p: string, id: string) =>
      id === "conv-a" ? [msgA] : [],
    );
    const store = useTutorStore.getState();
    await store.fetchConversations("proj-a");
    expect(useTutorStore.getState().messages.map((m) => m.id)).toEqual(["m-a"]);

    // Start loading B; A's slices must vanish immediately, before B resolves.
    let releaseB!: (v: unknown) => void;
    mockTutorConversations.mockReturnValueOnce(
      new Promise((res) => {
        releaseB = res as (v: unknown) => void;
      }),
    );
    const loading = useTutorStore.getState().fetchConversations("proj-b");
    expect(useTutorStore.getState().conversations).toEqual([]);
    expect(useTutorStore.getState().messages).toEqual([]);
    expect(useTutorStore.getState().activeId).toBeNull();
    releaseB([convB]);
    await loading;
    expect(useTutorStore.getState().messages).toEqual([]);
    expect(useTutorStore.getState().conversations.map((c) => c.id)).toEqual(["conv-b"]);
  });

  it("drops a late Project A response after switching to B", async () => {
    let releaseA!: (v: unknown) => void;
    mockTutorConversations.mockImplementationOnce(
      () =>
        new Promise((res) => {
          releaseA = res as (v: unknown) => void;
        }),
    );
    const pendingA = useTutorStore.getState().fetchConversations("proj-a");
    mockTutorConversations.mockResolvedValue([convB]);
    mockTutorMessages.mockResolvedValue([]);
    await useTutorStore.getState().fetchConversations("proj-b");
    // A finally resolves: must not overwrite B.
    releaseA([convA]);
    await pendingA;
    // Flush the auto-select chain B started.
    await act(async () => {});
    const s = useTutorStore.getState();
    expect(s.projectId).toBe("proj-b");
    expect(s.conversations.map((c) => c.id)).toEqual(["conv-b"]);
    expect(s.messages).toEqual([]);
  });

  it("refuses to send when the scope moved on", async () => {
    mockTutorConversations.mockResolvedValue([convA]);
    mockTutorMessages.mockResolvedValue([msgA]);
    await useTutorStore.getState().fetchConversations("proj-a");
    // Simulate a project switch that cleared scope without a new fetch.
    useTutorStore.getState().reset();
    await useTutorStore.getState().sendMessage("proj-a", "hello?");
    expect(tutorApi.send).not.toHaveBeenCalled();
  });
});

describe("assessment store project scope", () => {
  beforeEach(reset);

  it("clears Project A quizzes synchronously when Project B loads", async () => {
    const { assessmentApi: api } = await import("@/api/assessment");
    const listSpy = vi.spyOn(api, "quizzes").mockImplementation(async (pid: string) =>
      pid === "proj-a"
        ? [
            {
              id: "quiz-a",
              projectId: "proj-a",
              title: "A quiz",
              status: "READY",
              difficulty: null,
              questionCount: 1,
              createdAt: "",
            },
          ]
        : [],
    );
    const summariesSpy = vi.spyOn(api, "assessments").mockResolvedValue([]);
    const store = useAssessmentStore.getState();
    await store.fetchQuizzes("proj-a");
    expect(useAssessmentStore.getState().quizzes.map((q) => q.id)).toEqual(["quiz-a"]);

    let releaseB!: (v: unknown) => void;
    listSpy.mockReturnValueOnce(
      new Promise((res) => {
        releaseB = res as (v: unknown) => void;
      }),
    );
    const loading = useAssessmentStore.getState().fetchQuizzes("proj-b");
    expect(useAssessmentStore.getState().quizzes).toEqual([]);
    expect(useAssessmentStore.getState().activeQuiz).toBeNull();
    releaseB([]);
    await loading;
    expect(useAssessmentStore.getState().quizzes).toEqual([]);
    listSpy.mockRestore();
    summariesSpy.mockRestore();
  });
});

describe("assessmentApi.createQuiz contract", () => {
  beforeEach(reset);

  it("sends the snake_case idempotency key with a generation-scale timeout", async () => {
    mockPost.mockResolvedValue({
      data: {
        quiz: {
          id: "q1",
          project_id: "proj-a",
          title: "T",
          status: "READY",
          difficulty: null,
          question_count: 0,
          created_at: "",
        },
        questions: [],
      },
    });
    await assessmentApi.createQuiz("proj-a", {
      questionCount: 5,
      difficulty: null,
      questionTypes: ["MCQ", "OPEN_ENDED"],
      clientRequestKey: "key-123",
    });
    expect(mockPost).toHaveBeenCalledTimes(1);
    const [url, body, config] = mockPost.mock.calls[0] as [
      string,
      Record<string, unknown>,
      Record<string, unknown>,
    ];
    expect(url).toBe("/api/v1/projects/proj-a/quizzes");
    // The backend schema silently drops unknown fields: camelCase would
    // disable idempotent replays entirely.
    expect(body["client_request_key"]).toBe("key-123");
    expect(body).not.toHaveProperty("clientRequestKey");
    // Live grounded generation (~16s for 5 questions) exceeds the shared
    // 15s client default; this route carries its own bounded timeout.
    expect(config["timeout"]).toBe(120000);
  });
});

describe("useKnowledgeReadiness project scope", () => {
  beforeEach(reset);

  it("exposes the owning project id for banner scoping", async () => {
    const { useKnowledgeStore } = await import("@/stores/useKnowledgeStore");
    const { useKnowledgeReadiness } =
      await import("@/features/knowledge/hooks/useKnowledgeReadiness");
    const { knowledgeApi: kapi } = await import("@/api/knowledge");
    (kapi.status as Mock).mockResolvedValue({
      project_id: "proj-a",
      status: "READY",
      totals: { chunks_total: 1, chunks_embedded: 1, concepts: 0, materials_ready: 1 },
    });
    const { result, unmount } = renderHook(() => useKnowledgeReadiness("proj-a"));
    await act(async () => {});
    expect(result.current.status).toBe("READY");
    expect(useKnowledgeStore.getState().projectId).toBe("proj-a");
    unmount();
  });
});
