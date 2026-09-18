import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi, type Mock } from "vitest";
import { MemoryRouter } from "react-router-dom";

import { adminApi } from "@/api/admin";
import { RequireAdmin } from "@/components/auth/RequireAuth";
import { AdminPage } from "@/app/pages/AdminPage";
import { useAdminStore } from "@/stores/useAdminStore";
import { useAuthStore } from "@/stores/useAuthStore";

vi.mock("@/api/admin", () => ({
  adminApi: {
    overview: vi.fn(),
    users: vi.fn(),
    userJourney: vi.fn(),
    activity: vi.fn(),
    jobs: vi.fn(),
    health: vi.fn(),
    aiSummary: vi.fn(),
    evaluationSummary: vi.fn(),
    evaluationRuns: vi.fn(),
    runEvaluations: vi.fn(),
  },
}));

const mockOverview = adminApi.overview as Mock;
const mockUsers = adminApi.users as Mock;

function reset() {
  useAdminStore.getState().reset();
  vi.clearAllMocks();
}

const overview = {
  users: 3,
  admins: 1,
  spaces: 2,
  projects: 4,
  materials: 5,
  materialsReady: 4,
  assessments: 2,
  quizAttempts: 3,
  tutorConversations: 1,
  tutorMessages: 6,
  activeRecommendations: 1,
  events: 40,
  aiCalls: 9,
  evaluationRuns: 1,
  jobs: { QUEUED: 1 },
};

describe("AdminPage", () => {
  beforeEach(reset);

  it("renders platform overview stats", async () => {
    mockOverview.mockResolvedValue(overview);
    (adminApi.health as Mock).mockResolvedValue({
      overall: "healthy",
      api: "healthy",
      database: "healthy",
      databaseConfigured: true,
      ai: {},
      storage: {},
      queue: {},
    });
    render(
      <MemoryRouter>
        <AdminPage />
      </MemoryRouter>,
    );
    await waitFor(() => expect(screen.getByText("Admin dashboard")).toBeInTheDocument());
    expect(screen.getByText("AI calls")).toBeInTheDocument();
  });

  it("lists users with roles and inspect action", async () => {
    mockOverview.mockResolvedValue(overview);
    (adminApi.health as Mock).mockResolvedValue({
      overall: "healthy",
      api: "healthy",
      database: "healthy",
      databaseConfigured: true,
      ai: {},
      storage: {},
      queue: {},
    });
    mockUsers.mockResolvedValue({
      items: [
        {
          id: "u-1",
          email: "boss@example.com",
          displayName: "Boss",
          role: "admin",
          isActive: true,
          lastLoginAt: null,
          createdAt: "2026-01-01T00:00:00Z",
        },
      ],
      total: 1,
      page: 1,
      pageSize: 25,
    });
    render(
      <MemoryRouter>
        <AdminPage />
      </MemoryRouter>,
    );
    const { fireEvent } = await import("@testing-library/react");
    fireEvent.click(screen.getByRole("tab", { name: "Users" }));
    await waitFor(() => expect(screen.getByText("boss@example.com")).toBeInTheDocument());
    expect(screen.getByText("admin")).toBeInTheDocument();
  });
});

describe("RequireAdmin", () => {
  it("denies learners without calling admin APIs", () => {
    useAuthStore.setState({
      user: { id: "u", email: "e", displayName: "d", role: "learner" },
      status: "authenticated",
      initialized: true,
    });
    render(
      <MemoryRouter>
        <RequireAdmin />
      </MemoryRouter>,
    );
    expect(screen.getByText("Admin access required")).toBeInTheDocument();
  });

  it("denies unauthenticated visitors", () => {
    useAuthStore.setState({ user: null, status: "unauthenticated", initialized: true });
    render(
      <MemoryRouter>
        <RequireAdmin />
      </MemoryRouter>,
    );
    expect(screen.getByText("Admin access required")).toBeInTheDocument();
  });
});
