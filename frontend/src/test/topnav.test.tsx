import { MemoryRouter } from "react-router-dom";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

// Radix portals don't open under jsdom fireEvent; stub the menu shell so the
// test verifies TopNav's own wiring (label, items, onSelect -> logout).
vi.mock("@/components/ui", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/components/ui")>();
  return {
    ...actual,
    DropdownMenu: ({ children }: { children: React.ReactNode }) => <>{children}</>,
    DropdownMenuTrigger: ({ children }: { children: React.ReactNode }) => <>{children}</>,
    DropdownMenuContent: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
    DropdownMenuItem: ({
      children,
      onSelect,
    }: {
      children: React.ReactNode;
      onSelect?: () => void;
    }) => (
      <div role="menuitem" onClick={onSelect}>
        {children}
      </div>
    ),
  };
});

import { TopNav } from "@/components/layout/TopNav";
import { useAuthStore } from "@/stores/useAuthStore";

const learner = {
  id: "u1",
  email: "learner@example.com",
  displayName: "Learner",
  role: "learner" as const,
};
const admin = {
  id: "u2",
  email: "admin@example.com",
  displayName: "Admin",
  role: "admin" as const,
};

function renderNav() {
  return render(
    <MemoryRouter initialEntries={["/"]}>
      <TopNav />
    </MemoryRouter>,
  );
}

describe("TopNav", () => {
  it("renders brand, tagline, and primary links", () => {
    useAuthStore.setState({ user: learner, status: "authenticated" });
    renderNav();
    expect(screen.getByText("AI Learning Companion")).toBeInTheDocument();
    expect(screen.getByText(/Learn.*Practice.*Master/)).toBeInTheDocument();
    for (const name of ["Home", "Spaces", "Analytics"]) {
      expect(screen.getByRole("link", { name })).toHaveAttribute("href");
    }
    expect(screen.queryByRole("link", { name: "Admin" })).not.toBeInTheDocument();
  });

  it("shows Admin only for admins", () => {
    useAuthStore.setState({ user: admin, status: "authenticated" });
    renderNav();
    expect(screen.getByRole("link", { name: "Admin" })).toHaveAttribute(
      "href",
      "/admin",
    );
  });

  it("account menu signs out through the real store action", async () => {
    const logout = vi.fn().mockResolvedValue(undefined);
    useAuthStore.setState({ user: learner, status: "authenticated", logout });
    renderNav();
    const trigger = screen.getByRole("button", { name: "Account: Learner" });
    fireEvent.pointerDown(trigger);
    fireEvent.click(trigger);
    fireEvent.click(screen.getByRole("menuitem", { name: /sign out/i }));
    await waitFor(() => expect(logout).toHaveBeenCalledTimes(1));
  });

  it("mobile menu toggles the nav panel", () => {
    useAuthStore.setState({ user: learner, status: "authenticated" });
    renderNav();
    const toggle = screen.getByRole("button", { name: "Open navigation" });
    fireEvent.click(toggle);
    expect(screen.getByRole("navigation", { name: "Primary mobile" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Close navigation" })).toBeInTheDocument();
  });
});
