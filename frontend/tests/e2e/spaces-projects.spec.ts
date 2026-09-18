import { expect, test, type Page } from "@playwright/test";

/**
 * Spaces & Projects journey against the real API + real persistence
 * (isolated SQLite backend per e2e run; same routes as production Neon).
 *
 * Register -> create Space -> open Space -> create Project -> open Project
 * workspace -> refresh persists -> logout gates routes.
 */

async function register(page: Page, email: string) {
  await page.goto("/register");
  await page.getByLabel("Display name").fill("E2E Learner");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel(/^Password$/).fill("E2eSecure123");
  await page.getByLabel("Confirm password").fill("E2eSecure123");
  await page.getByRole("button", { name: /create account/i }).click();
  await page.waitForURL("/");
}

test("spaces and projects end to end", async ({ page }) => {
  const stamp = Date.now();
  await register(page, `spaces-${stamp}@example.com`);

  // Create a space through the dialog.
  await page.goto("/spaces");
  await page.getByRole("button", { name: "New Space", exact: true }).click();
  await page.getByLabel("Name").fill(`Physics ${stamp}`);
  await page.getByLabel(/Description/).fill("Mechanics and more");
  await page.getByRole("button", { name: "Create space", exact: true }).click();
  await expect(page.getByText(`Physics ${stamp}`)).toBeVisible();

  // Open the space, create a project inside it (space preselected).
  await page.getByRole("link", { name: new RegExp(`Open space Physics ${stamp}`) }).click();
  await page.waitForURL(/\/spaces\/.+/);
  await expect(page.getByRole("heading", { name: `Physics ${stamp}` })).toBeVisible();
  await page.getByRole("button", { name: "New Project" }).click();
  await page.getByLabel("Name").fill(`Kinematics ${stamp}`);
  await page.getByLabel(/Description/).fill("Motion in one dimension");
  await page.getByRole("button", { name: "Create project", exact: true }).click();
  await page.waitForURL(/\/projects\/.+/);
  const projectUrl = page.url();

  // Workspace shows real metadata + honest placeholders for future features.
  await expect(page.getByRole("heading", { name: `Kinematics ${stamp}` })).toBeVisible();
  await expect(page.getByText("No concepts yet.")).toBeVisible();
  await page.getByRole("link", { name: "Materials", exact: true }).click();
  await expect(page.getByText("No materials yet.")).toBeVisible();

  // Refresh: everything persists server-side.
  await page.reload();
  await expect(page.getByRole("heading", { name: `Kinematics ${stamp}` })).toBeVisible();
  await page.goto("/spaces");
  await expect(page.getByText(`Physics ${stamp}`)).toBeVisible();

  // Edit the project name, then archive it (reversible, children preserved).
  await page.getByRole("link", { name: new RegExp(`Open space Physics ${stamp}`) }).click();
  await page.getByRole("link", { name: new RegExp(`Open project Kinematics ${stamp}`) }).click();
  await page.waitForURL(/\/projects\/.+/);
  await page.getByRole("button", { name: "Edit project" }).click();
  await page.getByLabel("Name").fill(`Dynamics ${stamp}`);
  await page.getByRole("button", { name: "Save changes" }).click();
  await expect(page.getByRole("heading", { name: `Dynamics ${stamp}` })).toBeVisible();
  await page.getByRole("button", { name: "Archive", exact: true }).click();
  await page.getByRole("button", { name: "Archive project" }).click();
  await page.waitForURL(/\/spaces\/.+/);
  await expect(page.getByText(`Dynamics ${stamp}`)).toHaveCount(0);

  // Logout gates the workspace again.
  await page.getByRole("button", { name: "Account: E2E Learner" }).click();
  await page.getByRole("menuitem", { name: /sign out/i }).click();
  await expect(page.getByRole("heading", { name: /welcome back/i })).toBeVisible();
  await page.goto(projectUrl);
  await expect(page.getByRole("heading", { name: /welcome back/i })).toBeVisible();
});

test("user B cannot open user A's project URL", async ({ page, browser }) => {
  const stamp = Date.now();
  await register(page, `tenant-a-${stamp}@example.com`);
  await page.goto("/spaces");
  await page.getByRole("button", { name: "New Space", exact: true }).click();
  await page.getByLabel("Name").fill(`Private ${stamp}`);
  await page.getByRole("button", { name: "Create space", exact: true }).click();
  await expect(page.getByText(`Private ${stamp}`)).toBeVisible();
  await page.getByRole("link", { name: new RegExp(`Open space Private ${stamp}`) }).click();
  await page.waitForURL(/\/spaces\/.+/);
  await page.getByRole("button", { name: "New Project" }).click();
  await page.getByLabel("Name").fill(`Secret ${stamp}`);
  await page.getByRole("button", { name: "Create project", exact: true }).click();
  await page.waitForURL(/\/projects\/.+/);
  const privateUrl = page.url();

  // Second user, isolated storage: direct navigation must not disclose.
  const ctxB = await browser.newContext();
  const pageB = await ctxB.newPage();
  await register(pageB, `tenant-b-${stamp}@example.com`);
  await pageB.goto(privateUrl);
  await expect(pageB.getByText("Project not found", { exact: true })).toBeVisible();
  await expect(pageB.getByText(new RegExp(`Secret ${stamp}`))).toHaveCount(0);
  // And B's own workspace is empty — a clean, separate tenant.
  await pageB.goto("/spaces");
  await expect(pageB.getByText("No learning spaces yet.")).toBeVisible();
  await ctxB.close();
});
