import { expect, test, type Page } from "@playwright/test";

import { E2E_FIXTURE_PDF } from "./global-setup";

/**
 * Growth + Recommendations journey on the real stack (TEST_FAKE_AI only
 * affects AI providers; growth/recommendation math is always the production
 * deterministic code):
 *
 * login → project → upload → READY knowledge → quiz → answer → complete →
 * growth section shows status/counts → recommendations appear with reasons
 * → open a recommendation (real action) → complete it → reload → state
 * persists → logout. Tenant B gets 404s on growth/recommendations.
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

async function makeProjectWithPdf(page: Page, stamp: number, title: string) {
  await page.goto("/spaces");
  await page.getByRole("button", { name: "New Space", exact: true }).click();
  await page.getByLabel("Name").fill(`Growth ${stamp}`);
  await page.getByRole("button", { name: "Create space", exact: true }).click();
  await page.getByRole("link", { name: new RegExp(`Open space Growth ${stamp}`) }).click();
  await page.waitForURL(/\/spaces\/.+/);
  await page.getByRole("button", { name: "New Project" }).click();
  await page.getByLabel("Name").fill(`Thriving ${stamp}`);
  await page.getByRole("button", { name: "Create project", exact: true }).click();
  await page.waitForURL(/\/projects\/.+/);
  const projectUrl = page.url();
  const projectId = projectUrl.split("/projects/")[1].split("/")[0] as string;

  await page.getByRole("link", { name: "Materials", exact: true }).click();
  await page.getByRole("button", { name: "Upload PDF" }).click();
  await page.getByLabel(/Title/).fill(title);
  await page.locator('input[type="file"]').setInputFiles(E2E_FIXTURE_PDF);
  await page.getByRole("button", { name: "Upload", exact: true }).click();
  // Scoped to the material card: the dashboard summary also renders
  // "ready" text, so a global text match is ambiguous.
  const card = page.getByRole("link", { name: `Open material ${title}` });
  await expect(card).toBeVisible({ timeout: 30_000 });
  await expect(card.getByText("Ready")).toBeVisible({ timeout: 120_000 });
  // Full worker completion: badge/counter-only waits race embedding.
  await page.getByRole("link", { name: "Overview", exact: true }).click();
  await expect(page.getByText("READY").first()).toBeVisible({ timeout: 120_000 });
  await expect(page.getByText("2/2 chunks embedded")).toBeVisible({ timeout: 120_000 });
  await expect(page.getByRole("button", { name: /Photosynthesis/ })).toBeVisible({
    timeout: 120_000,
  });
  return { projectUrl, projectId };
}

async function completeMixedQuiz(page: Page) {
  await page.getByRole("link", { name: "Quiz", exact: true }).click();
  await page.getByLabel("Number of questions").fill("2");
  await page.getByLabel("Open-ended").uncheck();
  await page.getByRole("button", { name: "Generate quiz" }).click();
  await expect(page.getByRole("button", { name: "Start attempt" })).toBeVisible({
    timeout: 60_000,
  });
  await page.getByRole("button", { name: "Start attempt" }).click();
  await expect(page.getByText(/Answered 0 of/)).toBeVisible({ timeout: 30_000 });
  expect(await page.getByRole("radiogroup").count()).toBe(2);
  await page.getByRole("radiogroup").nth(0).getByRole("radio").nth(1).check();
  await page.getByRole("radiogroup").nth(1).getByRole("radio").first().check();
  for (let i = 0; i < 2; i++) {
    await page.getByRole("button", { name: "Submit answer" }).first().click();
  }
  await expect(page.getByText(/Answered 2 of 2/)).toBeVisible({ timeout: 60_000 });
  await page.getByRole("button", { name: "Finish and see results" }).click();
  await expect(page.getByText("50%", { exact: true }).first()).toBeVisible({ timeout: 30_000 });
}

test("growth overview, recommendations lifecycle, and persistence", async ({ page }) => {
  test.setTimeout(300_000);
  const stamp = Date.now();
  await register(page, `growth-${stamp}@example.com`);
  const { projectUrl } = await makeProjectWithPdf(page, stamp, "Growth bio");

  // Cold start is honest: no failure state, no zeros-as-knowledge.
  await page.getByRole("link", { name: "Growth", exact: true }).click();
  await expect(page.getByText("No mastery yet.")).toBeVisible({ timeout: 30_000 });
  await expect(
    page.getByText("Growth will appear after you complete your first assessment."),
  ).toBeVisible({ timeout: 30_000 });
  await page.getByRole("link", { name: "Overview", exact: true }).click();
  await expect(page.getByText("No recommendations yet.")).toBeVisible({ timeout: 30_000 });

  await completeMixedQuiz(page);

  // Growth reflects one mixed assessment: STABLE overall (single observations
  // never set trends).
  await page.getByRole("button", { name: "Back to quizzes" }).click();
  await page.getByRole("link", { name: "Growth", exact: true }).click();
  await expect(page.getByText("Avg mastery")).toBeVisible({ timeout: 30_000 });
  await expect(page.getByText("Requiring Attention")).toBeVisible({ timeout: 30_000 });

  // Recommendations carry reasons and backend-confirmed actions.
  await page.getByRole("link", { name: "Overview", exact: true }).click();
  const cards = page.locator("li", { hasText: "Priority" });
  await expect(cards.first()).toBeVisible({ timeout: 30_000 });
  expect(await cards.count()).toBeGreaterThan(0);

  // Open a recommendation navigates to a real capability (practice quiz).
  const practice = page.getByRole("button", { name: "Practice", exact: true }).first();
  await practice.click();
  await expect(page.getByText(/Answered 0 of/)).toBeVisible({ timeout: 60_000 });
  await page.getByRole("button", { name: "Leave attempt" }).click();

  // Complete the first recommendation; it leaves the active list.
  await page.getByRole("link", { name: "Overview", exact: true }).click();
  const before = await cards.count();
  await page.getByRole("button", { name: "Mark done" }).first().click();
  await expect
    .poll(async () => page.locator("li", { hasText: "Priority" }).count(), { timeout: 30_000 })
    .toBe(before - 1);

  // Reload: growth and recommendations persist server-side.
  await page.reload();
  await page.getByRole("link", { name: "Growth", exact: true }).click();
  await expect(page.getByText("Avg mastery")).toBeVisible({
    timeout: 60_000,
  });
  await page.getByRole("link", { name: "Overview", exact: true }).click();
  await expect(page.locator("li", { hasText: "Priority" }).first()).toBeVisible({
    timeout: 60_000,
  });

  // Logout gates the workspace again.
  await page.getByRole("button", { name: "Account: E2E Learner" }).click();
  await page.getByRole("menuitem", { name: /sign out/i }).click();
  await expect(page.getByRole("heading", { name: /welcome back/i })).toBeVisible();
  await page.goto(projectUrl);
  await expect(page.getByRole("heading", { name: /welcome back/i })).toBeVisible();
});

test("growth and recommendation isolation across tenants", async ({ page, browser, request }) => {
  test.setTimeout(300_000);
  const stamp = Date.now();
  await register(page, `growa-${stamp}@example.com`);
  const { projectUrl, projectId } = await makeProjectWithPdf(page, stamp, "Private growth");
  await completeMixedQuiz(page);
  await page.getByRole("link", { name: "Growth", exact: true }).click();
  await expect(page.getByText("Avg mastery")).toBeVisible({
    timeout: 30_000,
  });

  // Second tenant cannot open A's project at all.
  const ctxB = await browser.newContext();
  const pageB = await ctxB.newPage();
  await register(pageB, `growb-${stamp}@example.com`);
  await pageB.goto(projectUrl);
  await expect(pageB.getByText("Project not found", { exact: true })).toBeVisible();
  await ctxB.close();

  // Raw API: B gets 404 on growth, history, and recommendations.
  const loginB = await request.post("http://127.0.0.1:8000/api/v1/auth/login", {
    data: { email: `growb-${stamp}@example.com`, password: "E2eSecure123" },
  });
  expect(loginB.ok()).toBeTruthy();
  const headersB = { Authorization: `Bearer ${(await loginB.json()).access_token}` };
  const base = `http://127.0.0.1:8000/api/v1/projects/${projectId}`;
  expect((await request.get(`${base}/growth`, { headers: headersB })).status()).toBe(404);
  expect((await request.get(`${base}/growth/history`, { headers: headersB })).status()).toBe(404);
  expect((await request.get(`${base}/recommendations`, { headers: headersB })).status()).toBe(404);

  // A's own data remains readable; B's project is honestly empty.
  const loginA = await request.post("http://127.0.0.1:8000/api/v1/auth/login", {
    data: { email: `growa-${stamp}@example.com`, password: "E2eSecure123" },
  });
  const headersA = { Authorization: `Bearer ${(await loginA.json()).access_token}` };
  const growth = await request.get(`${base}/growth`, { headers: headersA });
  expect(growth.ok()).toBeTruthy();
  expect((await growth.json()).has_evidence).toBe(true);
  const recs = await request.get(`${base}/recommendations`, { headers: headersA });
  expect(recs.ok()).toBeTruthy();
  const recId = (await recs.json()).items[0]?.id as string | undefined;
  if (recId) {
    expect(
      (await request.get(`${base}/recommendations/${recId}`, { headers: headersB })).status(),
    ).toBe(404);
  }
});
