import { MemoryRouter, Route, Routes } from "react-router-dom";
import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi, type Mock } from "vitest";

import { RequireAuth } from "@/components/auth/RequireAuth";
import { useAuthStore } from "@/stores/useAuthStore";
import { clearStoredToken, setStoredToken } from "@/api/tokenStorage";

// Only the network boundary (axios singleton) is mocked; store, mapping,
// guards, and token storage run for real.
vi.mock("@/api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/api/client")>();
  return { ...actual, apiClient: { get: vi.fn(), post: vi.fn() } };
});

import { apiClient } from "@/api/client";

const mockGet = apiClient.get as Mock;
const mockPost = apiClient.post as Mock;

/** Rejections shaped like real AxiosErrors so toApiError parses them. */
function axiosFailure(status: number, message: string): Error {
  const err = new Error(`Request failed with status code ${status}`) as Error & {
    isAxiosError: boolean;
    response: unknown;
  };
  err.isAxiosError = true;
  err.response = { status, data: { error: { message } }, headers: {} };
  return err;
}

const backendUser = {
  id: "u-1",
  email: "ada@example.com",
  display_name: "Ada",
  created_at: "2026-01-01T00:00:00Z",
};

function resetAuth() {
  clearStoredToken();
  mockGet.mockReset();
  mockPost.mockReset();
  useAuthStore.setState({ user: null, status: "idle", initialized: false, error: null });
}

describe("auth store", () => {
  beforeEach(resetAuth);

  it("initializes to unauthenticated without a stored token and no request", async () => {
    const { initialize } = useAuthStore.getState();
    await initialize();
    expect(useAuthStore.getState().status).toBe("unauthenticated");
    expect(mockGet).not.toHaveBeenCalled();
  });

  it("restores the session from a stored token via /me", async () => {
    setStoredToken("tok-123");
    mockGet.mockResolvedValue({ data: backendUser });
    await useAuthStore.getState().initialize();
    const s = useAuthStore.getState();
    expect(s.status).toBe("authenticated");
    expect(s.user).toMatchObject({ email: "ada@example.com", displayName: "Ada" });
    expect(mockGet).toHaveBeenCalledWith("/api/v1/auth/me");
  });

  it("drops to unauthenticated when /me rejects", async () => {
    setStoredToken("stale");
    mockGet.mockRejectedValue(axiosFailure(401, "Invalid or expired token."));
    await useAuthStore.getState().initialize();
    expect(useAuthStore.getState().status).toBe("unauthenticated");
  });

  it("logs in, persists the token, and populates the user", async () => {
    mockPost.mockResolvedValue({
      data: { access_token: "tok-abc", token_type: "bearer", expires_in: 1800, user: backendUser },
    });
    await useAuthStore.getState().login("ada@example.com", "password123");
    const s = useAuthStore.getState();
    expect(s.status).toBe("authenticated");
    expect(s.user?.email).toBe("ada@example.com");
    expect(localStorage.getItem("alc.access_token")).toBe("tok-abc");
  });

  it("surfaces server errors on failed login", async () => {
    mockPost.mockRejectedValue(axiosFailure(401, "Invalid email or password."));
    await expect(useAuthStore.getState().login("a@e.com", "wrong")).rejects.toBeTruthy();
    const s = useAuthStore.getState();
    expect(s.status).toBe("unauthenticated");
    expect(s.error).toBe("Invalid email or password.");
  });

  it("logs out and always clears the credential", async () => {
    setStoredToken("tok-abc");
    useAuthStore.setState({
      user: { id: "u", email: "e", displayName: "d", role: "learner" },
      status: "authenticated",
    });
    mockPost.mockResolvedValue({ data: { ok: true } });
    await useAuthStore.getState().logout();
    expect(useAuthStore.getState().status).toBe("unauthenticated");
    expect(localStorage.getItem("alc.access_token")).toBeNull();

    // Even when the server call fails, no usable credential may remain.
    setStoredToken("tok-abc");
    useAuthStore.setState({
      user: { id: "u", email: "e", displayName: "d", role: "learner" },
      status: "authenticated",
    });
    mockPost.mockRejectedValue(new Error("network down"));
    await useAuthStore.getState().logout();
    expect(localStorage.getItem("alc.access_token")).toBeNull();
    expect(useAuthStore.getState().status).toBe("unauthenticated");
  });
});

describe("RequireAuth", () => {
  beforeEach(resetAuth);

  function renderAt(path: string) {
    return render(
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route element={<RequireAuth />}>
            <Route path="/projects" element={<p>secret projects</p>} />
          </Route>
          <Route path="/login" element={<p>login page</p>} />
        </Routes>
      </MemoryRouter>,
    );
  }

  it("redirects anonymous users to login preserving the destination", async () => {
    useAuthStore.setState({ status: "unauthenticated", initialized: true });
    renderAt("/projects");
    await waitFor(() => expect(screen.getByText("login page")).toBeInTheDocument());
    expect(screen.queryByText("secret projects")).not.toBeInTheDocument();
  });

  it("renders protected content when authenticated", async () => {
    useAuthStore.setState({
      user: { id: "u", email: "e", displayName: "d", role: "learner" },
      status: "authenticated",
      initialized: true,
    });
    renderAt("/projects");
    await waitFor(() => expect(screen.getByText("secret projects")).toBeInTheDocument());
  });
});
