import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi, type Mock } from "vitest";

import { tutorApi } from "@/api/tutor";
import { TutorSection } from "@/features/tutor/components/TutorSection";
import { useTutorStore } from "@/stores/useTutorStore";

// Only the HTTP boundary is mocked; mapping, store, and component run for real.
vi.mock("@/api/tutor", () => ({
  tutorApi: {
    conversations: vi.fn(),
    createConversation: vi.fn(),
    messages: vi.fn(),
    send: vi.fn(),
  },
}));

const mockConversations = tutorApi.conversations as Mock;
const mockCreate = tutorApi.createConversation as Mock;
const mockMessages = tutorApi.messages as Mock;
const mockSend = tutorApi.send as Mock;

function reset() {
  useTutorStore.getState().reset();
  vi.clearAllMocks();
}

const conv = {
  id: "conv-1",
  projectId: "proj-1",
  title: "Untitled conversation",
  createdAt: "",
  updatedAt: "",
};

const userMsg = {
  id: "m-user",
  conversationId: "conv-1",
  role: "USER" as const,
  content: "What does the PDF say?",
  model: null,
  createdAt: "",
  citations: [],
  grounded: false,
  insufficientEvidence: false,
};

const groundedMsg = {
  id: "m-asst",
  conversationId: "conv-1",
  role: "ASSISTANT" as const,
  content: "Based on your materials: Photosynthesis converts sunlight.",
  model: "llama-3.1-8b-instant",
  createdAt: "",
  citations: [
    {
      chunk_id: "c1",
      document_id: "d1",
      material_id: "m1",
      material_name: "Doc",
      page_start: 1,
      page_end: 1,
      label: "Doc — Page 1",
    },
  ],
  grounded: true,
  insufficientEvidence: false,
};

describe("tutor store", () => {
  beforeEach(reset);

  it("auto-creates a conversation when none exist", async () => {
    mockConversations.mockResolvedValue([]);
    mockCreate.mockResolvedValue(conv);
    await useTutorStore.getState().fetchConversations("proj-1");
    const s = useTutorStore.getState();
    expect(mockCreate).toHaveBeenCalledWith("proj-1");
    expect(s.activeId).toBe("conv-1");
    expect(s.messagesState).toBe("ready");
  });

  it("dedupes concurrent auto-creates (StrictMode double-mount)", async () => {
    mockConversations.mockResolvedValue([]);
    mockCreate.mockImplementation(() => new Promise((res) => setTimeout(() => res(conv), 20)));
    const store = useTutorStore.getState();
    await Promise.all([store.fetchConversations("proj-1"), store.fetchConversations("proj-1")]);
    expect(mockCreate).toHaveBeenCalledTimes(1);
    expect(useTutorStore.getState().conversations).toHaveLength(1);
  });

  it("selects the newest existing conversation and loads history", async () => {
    mockConversations.mockResolvedValue([conv]);
    mockMessages.mockResolvedValue([userMsg, groundedMsg]);
    await useTutorStore.getState().fetchConversations("proj-1");
    const s = useTutorStore.getState();
    expect(s.activeId).toBe("conv-1");
    expect(s.messages).toHaveLength(2);
    expect(s.messages[1]?.grounded).toBe(true);
  });

  it("sends with an idempotency key then reloads history from the server", async () => {
    mockConversations.mockResolvedValue([conv]);
    mockMessages.mockResolvedValue([]);
    mockSend.mockResolvedValue({
      conversationId: "conv-1",
      message: groundedMsg,
      citations: groundedMsg.citations,
      grounded: true,
      insufficientEvidence: false,
    });
    const store = useTutorStore.getState();
    await store.fetchConversations("proj-1");
    await useTutorStore.getState().sendMessage("proj-1", "What does the PDF say?");
    expect(mockSend).toHaveBeenCalledWith(
      "proj-1",
      "conv-1",
      "What does the PDF say?",
      expect.any(String),
    );
    // Server re-read: user message + assistant reply, exactly once each.
    expect(mockMessages).toHaveBeenCalledTimes(2);
    const s = useTutorStore.getState();
    expect(s.sendState).toBe("idle");
    expect(s.error).toBeNull();
  });

  it("records send errors without losing the draft context", async () => {
    mockConversations.mockResolvedValue([conv]);
    mockMessages.mockResolvedValue([]);
    mockSend.mockRejectedValue(new Error("tutor down"));
    await useTutorStore.getState().fetchConversations("proj-1");
    await useTutorStore.getState().sendMessage("proj-1", "hello?");
    const s = useTutorStore.getState();
    expect(s.sendState).toBe("error");
    expect(s.error).toContain("tutor down");
  });
});

describe("TutorSection", () => {
  beforeEach(reset);

  function renderSection() {
    return render(<TutorSection projectId="proj-1" />);
  }

  it("renders a grounded answer with app-built citations", async () => {
    mockConversations.mockResolvedValue([conv]);
    mockMessages.mockResolvedValueOnce([]).mockResolvedValueOnce([userMsg, groundedMsg]);
    mockSend.mockResolvedValue({
      conversationId: "conv-1",
      message: groundedMsg,
      citations: groundedMsg.citations,
      grounded: true,
      insufficientEvidence: false,
    });
    renderSection();
    await waitFor(() => expect(screen.getByLabelText("Ask the tutor")).toBeEnabled());
    fireEvent.change(screen.getByLabelText("Ask the tutor"), {
      target: { value: "What does the PDF say?" },
    });
    fireEvent.click(screen.getByRole("button", { name: /^send$/i }));
    await waitFor(() =>
      expect(screen.getByText(/Photosynthesis converts sunlight/)).toBeInTheDocument(),
    );
    expect(screen.getByText("Grounded in your materials")).toBeInTheDocument();
    expect(screen.getByText("Doc — Page 1")).toBeInTheDocument();
  });

  it("renders the insufficient-evidence badge without citations", async () => {
    const insufficient = {
      ...groundedMsg,
      id: "m-ins",
      content: "I couldn't find enough evidence in this project's materials.",
      citations: [],
      grounded: false,
      insufficientEvidence: true,
    };
    mockConversations.mockResolvedValue([conv]);
    mockMessages.mockResolvedValue([userMsg, insufficient]);
    renderSection();
    await waitFor(() => expect(screen.getByText("Not enough evidence")).toBeInTheDocument());
    expect(screen.queryByText("Grounded in your materials")).not.toBeInTheDocument();
  });

  it("disables send while a message is in flight", async () => {
    mockConversations.mockResolvedValue([conv]);
    let release!: (v: unknown) => void;
    mockMessages.mockReturnValue(new Promise((res) => (release = res)));
    mockSend.mockReturnValue(new Promise(() => {}));
    renderSection();
    await waitFor(() => expect(screen.getByLabelText("Ask the tutor")).toBeEnabled());
    fireEvent.change(screen.getByLabelText("Ask the tutor"), { target: { value: "q?" } });
    fireEvent.click(screen.getByRole("button", { name: /^send$/i }));
    await waitFor(() => expect(screen.getByRole("button", { name: /sending/i })).toBeDisabled());
    release([]);
  });

  it("shows an honest empty state before the first question", async () => {
    mockConversations.mockResolvedValue([]);
    mockCreate.mockResolvedValue(conv);
    renderSection();
    await waitFor(() => expect(screen.getByText("Ask about your materials.")).toBeInTheDocument());
  });

  it("switches conversations and reloads history", async () => {
    const conv2 = { ...conv, id: "conv-2", title: "Second" };
    mockConversations.mockResolvedValue([conv, conv2]);
    mockMessages.mockImplementation(async (_p: string, id: string) =>
      id === "conv-2" ? [userMsg] : [],
    );
    renderSection();
    await waitFor(() => expect(screen.getByLabelText("Conversations")).toBeInTheDocument());
    fireEvent.click(screen.getByRole("option", { name: "Second" }));
    await waitFor(() => expect(screen.getByText("What does the PDF say?")).toBeInTheDocument());
  });
});
