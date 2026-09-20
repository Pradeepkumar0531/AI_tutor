import { beforeEach, describe, expect, it, vi, type Mock } from "vitest";

// Only the HTTP boundary is mocked; the tutor API client runs for real.
vi.mock("@/api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/api/client")>();
  return {
    ...actual,
    apiClient: { get: vi.fn(), post: vi.fn(), put: vi.fn(), delete: vi.fn() },
  };
});

import { apiClient } from "@/api/client";
import { tutorApi } from "@/api/tutor";

const mockPost = apiClient.post as Mock;

function reset() {
  vi.clearAllMocks();
}

describe("tutorApi.send timeout contract", () => {
  beforeEach(reset);

  it("carries the backend's 60s provider bound, not the shared 15s default", async () => {
    mockPost.mockResolvedValue({
      data: {
        conversation_id: "conv-1",
        message: {
          id: "m-1",
          conversation_id: "conv-1",
          role: "ASSISTANT",
          content: "Hi.",
          model: "openai/gpt-oss-20b",
          created_at: "",
          citations: [],
          grounded: false,
          insufficient_evidence: false,
        },
        citations: [],
        grounded: false,
        insufficient_evidence: false,
      },
    });
    await tutorApi.send("proj-1", "conv-1", "Hello?", "key-1");
    expect(mockPost).toHaveBeenCalledTimes(1);
    const [url, body, config] = mockPost.mock.calls[0] as [
      string,
      Record<string, unknown>,
      Record<string, unknown>,
    ];
    expect(url).toBe("/api/v1/projects/proj-1/conversations/conv-1/messages");
    // Backend schema field names (snake_case): silently dropped otherwise.
    expect(body).toEqual({ content: "Hello?", request_key: "key-1" });
    // Live Tutor generation measures ~1.6–3.6s typical, but the backend
    // tolerates 60s provider calls plus one retry — the browser must not
    // abort first and fake a failure after persistence.
    expect(config["timeout"]).toBe(60000);
  });
});
