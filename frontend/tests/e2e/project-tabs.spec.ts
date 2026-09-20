import { expect, test, type Page } from "@playwright/test";

/**
 * Project workspace polish: stable tab navigation (no scroll-to-top resets),
 * compact header (breadcrumb only, no redundant rows), and working history.
 */

async function register(page: Page, email: string) {
  await page.goto("/register");
  await page.getByLabel("Display name").fill("E2E Learner");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel(/^Password$/).fill("E2eSecure123");
  await page.getByLabel("Confirm password").fill("E2eSecure123");
  await page.getByRole("button", { name: /create account/i }).click();
  await page.getByRole("button", { name: /Account: E2E Learner/ }).waitFor({ timeout: 30000 });
}

async function makeProject(page: Page, stamp: number) {
  await page.goto("/spaces");
  await page.getByRole("button", { name: "New Space", exact: true }).click();
  await page.getByLabel("Name").fill(`Tabs ${stamp}`);
  await page.getByRole("button", { name: "Create space", exact: true }).click();
  await page.getByRole("link", { name: new RegExp(`Open space Tabs ${stamp}`) }).click();
  await page.waitForURL(/\/spaces\/.+/);
  await page.getByRole("button", { name: "New Project" }).click();
  await page.getByLabel("Name").fill(`Tabbing ${stamp}`);
  await page.getByRole("button", { name: "Create project", exact: true }).click();
  await page.waitForURL(/\/projects\/.+/);
  return (page.url().split("/projects/")[1] as string).split("/")[0] as string;
}

test("project header is compact and tab switches preserve scroll", async ({ page }) => {
  test.setTimeout(180_000);
  const stamp = Date.now();
  await register(page, `tabs-${stamp}@example.com`);
  const projectId = await makeProject(page, stamp);

  // Compact header: breadcrumb hierarchy only.
  await page.goto(`/projects/${projectId}/overview`);
  await expect(page.getByRole("navigation", { name: "Breadcrumb" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Back to", exact: false })).toHaveCount(0);
  await expect(page.getByText("Materials ready (", { exact: false })).toHaveCount(0);
  await expect(page.getByText("Materials ready", { exact: true })).toBeVisible();
  await expect(page.getByText("Average mastery", { exact: true })).toBeVisible();

  // Short viewport so the workspace scrolls; the tabs stay reachable.
  // The app uses smooth scrolling, which makes scripted scrolls land
  // asynchronously — disable it so the test positions deterministically.
  await page.setViewportSize({ width: 900, height: 400 });
  await page.addStyleTag({ content: "html{scroll-behavior:auto !important}" });
  await page.evaluate(() => window.scrollTo(0, 600));
  await page.waitForFunction(() => window.scrollY === 600);
  const atOverview = await page.evaluate(() => window.scrollY);
  expect(atOverview).toBe(600);

  // Overview -> Quiz -> Tutor: the viewport must not jump to the top. When
  // the new tab is shorter, the browser clamps to the maximum scrollable
  // offset — that is layout, not a reset — so assert preservation modulo
  // clamping.
  async function snap() {
    return page.evaluate(() => ({
      y: Math.round(window.scrollY),
      max: Math.round(document.documentElement.scrollHeight - window.innerHeight),
    }));
  }
  async function expectScrollPreserved(before: number) {
    const { y, max } = await snap("check");
    expect(y).toBe(Math.min(before, Math.max(0, max)));
    expect(y).toBeGreaterThan(0);
  }
  await page.getByRole("link", { name: "Quiz", exact: true }).click();
  await expect(page.getByText("No quizzes yet.")).toBeVisible({ timeout: 30_000 });
  await page.waitForTimeout(800);
  await expectScrollPreserved(atOverview);

  await page.getByRole("link", { name: "Tutor", exact: true }).click();
  await expect(page.getByText("Ask about your materials.")).toBeVisible({ timeout: 30_000 });
  await page.waitForTimeout(1500);
  await expectScrollPreserved(atOverview);

  // Back/Forward keep working and keep the workspace stable.
  await page.goBack();
  await expect(page.getByText("No quizzes yet.")).toBeVisible({ timeout: 30_000 });
  await page.goForward();
  await expect(page.getByText("Ask about your materials.")).toBeVisible({ timeout: 30_000 });

  // Refresh and direct URL access land on the right tab.
  await page.reload();
  await expect(page.getByText("Ask about your materials.")).toBeVisible({ timeout: 30_000 });
  await page.goto(`/projects/${projectId}/growth`);
  // Growth content lazy-loads on visibility (performance): wait for the
  // section to mount, scroll it into view exactly as a user would, then
  // assert its empty state.
  await page.locator("#section-growth").waitFor({ timeout: 30_000 });
  await page.evaluate(() => document.querySelector("#section-growth")?.scrollIntoView());
  await expect(page.getByText("No mastery yet.")).toBeVisible({ timeout: 30_000 });
});
