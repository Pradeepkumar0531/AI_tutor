import { expect, test, type Page } from "@playwright/test";

import { E2E_FIXTURE_PDF } from "./global-setup";

/**
 * Dashboard journey on the real stack (TEST_FAKE_AI only affects AI
 * providers; every dashboard number comes from persisted application state):
 *
 * login → project → upload → READY knowledge → tutor message → quiz →
 * complete → dashboard shows real summary/activity/charts → reload →
 * metrics persist → logout → routes protected. Tenant B gets 404s.
 */

const CHUNK_ONE = "Photosynthesis converts sunlight into chemical energy. Page one.";

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
  await page.getByLabel("Name").fill(`Dashboard ${stamp}`);
  await page.getByRole("button", { name: "Create space", exact: true }).click();
  await page.getByRole("link", { name: new RegExp(`Open space Dashboard ${stamp}`) }).click();
  await page.waitForURL(/\/spaces\/.+/);
  await page.getByRole("button", { name: "New Project" }).click();
  await page.getByLabel("Name").fill(`Observed ${stamp}`);
  await page.getByRole("button", { name: "Create project", exact: true }).click();
  await page.waitForURL(/\/projects\/.+/);
  const projectUrl = page.url();
  const projectId = projectUrl.split("/projects/")[1].split("/")[0] as string;

  await page.getByRole("link", { name: "Materials", exact: true }).click();
  await page.getByRole("button", { name: "Upload PDF" }).click();
  await page.getByLabel(/Title/).fill(title);
  await page.locator('input[type="file"]').setInputFiles(E2E_FIXTURE_PDF);
  await page.getByRole("button", { name: "Upload", exact: true }).click();
  await expect(page.getByText(title)).toBeVisible({ timeout: 30_000 });
  await expect(page.getByText("Ready", { exact: true }).first()).toBeVisible({
    timeout: 120_000,
  });
  // Full worker completion: badge/counter-only waits race embedding.
  await page.getByRole("link", { name: "Overview", exact: true }).click();
  await expect(page.getByText("READY").first()).toBeVisible({ timeout: 120_000 });
  await expect(page.getByText("2/2 chunks embedded")).toBeVisible({ timeout: 120_000 });
  await expect(page.getByRole("button", { name: /Photosynthesis/ })).toBeVisible({
    timeout: 120_000,
  });
  return { projectUrl, projectId };
}

test("dashboard reflects the real learning loop", async ({ page }) => {
  test.setTimeout(300_000);
  const stamp = Date.now();
  await register(page, `dash-${stamp}@example.com`);
  const { projectUrl } = await makeProjectWithPdf(page, stamp, "Observed bio");

  // Cold start first: honest emptiness, real content counts absent of evidence.
  await page
    .getByLabel("Project", { exact: true })
    .getByRole("link", { name: "Analytics", exact: true })
    .click();
  await expect(page.getByText("No learning evidence yet.")).toBeVisible({ timeout: 30_000 });

  // Tutor interaction counts as learning activity.
  await page.getByRole("link", { name: "Tutor", exact: true }).click();
  await page.getByLabel("Ask the tutor").fill(CHUNK_ONE);
  await page.getByRole("button", { name: /^send$/i }).click();
  await expect(page.getByText("Grounded in your materials").first()).toBeVisible({
    timeout: 30_000,
  });

  // One mixed quiz: first question wrong, second right.
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
  await expect(page.getByRole("button", { name: "Submit answer" })).toHaveCount(0);
  await page.getByRole("button", { name: "Submit Quiz" }).click();
  await expect(page.getByText("50%", { exact: true }).first()).toBeVisible({ timeout: 60_000 });
  await page.getByRole("button", { name: "Back to quizzes" }).click();

  // Dashboard: real summary metrics from persisted state.
  await page
    .getByLabel("Project", { exact: true })
    .getByRole("link", { name: "Analytics", exact: true })
    .click();
  await expect(page.getByText("Overall Mastery")).toBeVisible({ timeout: 30_000 });
  await expect(page.getByRole("link", { name: "Overall Mastery 50%" })).toBeVisible({
    timeout: 30_000,
  });
  const body = (await page.textContent("body")) ?? "";
  expect(body).toContain("1 image");
  expect(body).not.toContain("42 hours studied");
  expect(body).not.toContain("day streak");

  // Charts render from real points (not fabricated), timeline shows events.
  await expect(page.getByLabel("Daily learning activity")).toBeVisible({ timeout: 30_000 });
  await expect(page.getByText("Completed assessment — 50%")).toBeVisible({ timeout: 30_000 });
  await expect(page.getByText("Asked the tutor")).toBeVisible({ timeout: 30_000 });

  // Reload: metrics persist server-side.
  await page.reload();
  await expect(page.getByRole("link", { name: "Overall Mastery 50%" })).toBeVisible({
    timeout: 60_000,
  });

  // Logout gates the workspace again.
  await page.getByRole("button", { name: "Account: E2E Learner" }).click();
  await page.getByRole("menuitem", { name: /sign out/i }).click();
  await expect(page.getByRole("heading", { name: /welcome back/i })).toBeVisible();
  await page.goto(projectUrl);
  await expect(page.getByRole("heading", { name: /welcome back/i })).toBeVisible();
});

test("dashboard and event isolation across tenants", async ({ page, browser, request }) => {
  test.setTimeout(300_000);
  const stamp = Date.now();
  await register(page, `dasha-${stamp}@example.com`);
  const { projectUrl, projectId } = await makeProjectWithPdf(page, stamp, "Private observed");
  await page
    .getByLabel("Project", { exact: true })
    .getByRole("link", { name: "Analytics", exact: true })
    .click();
  await expect(page.getByText("No learning evidence yet.")).toBeVisible({ timeout: 30_000 });

  const ctxB = await browser.newContext();
  const pageB = await ctxB.newPage();
  await register(pageB, `dashb-${stamp}@example.com`);
  await pageB.goto(projectUrl);
  await expect(pageB.getByText("Project not found", { exact: true })).toBeVisible();
  await ctxB.close();

  const loginB = await request.post("http://127.0.0.1:8000/api/v1/auth/login", {
    data: { email: `dashb-${stamp}@example.com`, password: "E2eSecure123" },
  });
  expect(loginB.ok()).toBeTruthy();
  const headersB = { Authorization: `Bearer ${(await loginB.json()).access_token}` };
  const base = `http://127.0.0.1:8000/api/v1/projects/${projectId}`;
  expect((await request.get(`${base}/analytics/dashboard`, { headers: headersB })).status()).toBe(
    404,
  );
  expect((await request.get(`${base}/analytics/activity`, { headers: headersB })).status()).toBe(
    404,
  );
  expect((await request.get(`${base}/events`, { headers: headersB })).status()).toBe(404);
});
