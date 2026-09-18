import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { EmptyState } from "@/components/ui";

describe("foundation", () => {
  it("renders structural empty states without fake data", () => {
    render(<EmptyState title="No projects yet" description="Structural placeholder." />);
    expect(screen.getByText("No projects yet")).toBeInTheDocument();
  });

  it("api base url is configurable", async () => {
    const { API_BASE_URL } = await import("@/api/client");
    expect(typeof API_BASE_URL).toBe("string");
    expect(API_BASE_URL.length).toBeGreaterThan(0);
  });
});
