import { expect, test, type Page } from "@playwright/test";

import { E2E_FIXTURE_PDF } from "./global-setup";

/**
 * Knowledge journey with the real worker pipeline (deterministic fake AI via
 * TEST_FAKE_AI — content-derived embeddings and keyword concepts, no keys):
 *
 * login → project → upload → READY material → knowledge READY → concepts
 * listed → search returns grounded results with page citations → logout.
 * Cross-user isolation verified for knowledge endpoints and pages.
 */

const CHUNK_SENTENCE = "Photosynthesis converts sunlight into chemical energy. Page one.";

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
  await page.getByLabel("Name").fill(`Knowledge ${stamp}`);
  await page.getByRole("button", { name: "Create space", exact: true }).click();
  await page.getByRole("link", { name: new RegExp(`Open space Knowledge ${stamp}`) }).click();
  await page.waitForURL(/\/spaces\/.+/);
  await page.getByRole("button", { name: "New Project" }).click();
  await page.getByLabel("Name").fill(`RAG ${stamp}`);
  await page.getByRole("button", { name: "Create project", exact: true }).click();
  await page.waitForURL(/\/projects\/.+/);
  const projectUrl = page.url();

  await page.getByRole("link", { name: "Materials", exact: true }).click();
  await page.getByRole("button", { name: "Upload PDF" }).click();
  await page.getByLabel(/Title/).fill(title);
  await page.locator('input[type="file"]').setInputFiles(E2E_FIXTURE_PDF);
  await page.getByRole("button", { name: "Upload", exact: true }).click();
  // Scoped to the material card: the dashboard summary also renders
  // "ready" text, so a global text match is ambiguous.
  const card = page.getByRole("link", { name: `Open material ${title}` });
  await expect(card).toBeVisible();
  await expect(card.getByText("Ready")).toBeVisible({ timeout: 120_000 });
  return projectUrl;
}

test("knowledge pipeline, concepts, and grounded search", async ({ page }) => {
  test.setTimeout(240_000);
  const stamp = Date.now();
  await register(page, `knowledge-${stamp}@example.com`);
  const projectUrl = await makeProjectWithPdf(page, stamp, "Bio notes");

  // Knowledge processes asynchronously after READY: status, counts, concepts.
  await page.getByRole("link", { name: "Overview", exact: true }).click();
  await expect(page.getByText("READY").first()).toBeVisible({ timeout: 120_000 });
  await expect(page.getByText(/chunks embedded/)).toBeVisible({ timeout: 120_000 });
  await expect(page.getByRole("button", { name: /Photosynthesis/ })).toBeVisible({
    timeout: 120_000,
  });

  // Concept provenance expands to real source materials.
  await page.getByRole("button", { name: /Photosynthesis/ }).click();
  await expect(page.getByText("Bio notes")).toBeVisible();

  // Grounded search: exact chunk sentence retrieves with a page citation.
  await page.getByLabel("Search project knowledge").fill(CHUNK_SENTENCE);
  await page.getByRole("button", { name: "Search", exact: true }).click();
  await expect(page.getByText(CHUNK_SENTENCE)).toBeVisible({ timeout: 30_000 });
  await expect(page.getByText("Bio notes — Page 1", { exact: true })).toBeVisible();

  // Refresh persists everything server-side.
  await page.reload();
  await expect(page.getByRole("button", { name: /Photosynthesis/ })).toBeVisible({
    timeout: 60_000,
  });

  // Logout gates the workspace again.
  await page.getByRole("button", { name: "Account: E2E Learner" }).click();
  await page.getByRole("menuitem", { name: /sign out/i }).click();
  await expect(page.getByRole("heading", { name: /welcome back/i })).toBeVisible();
  await page.goto(projectUrl);
  await expect(page.getByRole("heading", { name: /welcome back/i })).toBeVisible();
});

test("knowledge isolation across tenants", async ({ page, browser, request }) => {
  test.setTimeout(240_000);
  const stamp = Date.now();
  await register(page, `knowa-${stamp}@example.com`);
  const projectUrl = await makeProjectWithPdf(page, stamp, "Private bio");
  const projectId = projectUrl.split("/projects/")[1].split("/")[0];
  await page.getByRole("link", { name: "Overview", exact: true }).click();
  await expect(page.getByText("READY").first()).toBeVisible({ timeout: 120_000 });

  // Second tenant in a fresh context cannot open A's project at all.
  const ctxB = await browser.newContext();
  const pageB = await ctxB.newPage();
  await register(pageB, `knowb-${stamp}@example.com`);
  await pageB.goto(projectUrl);
  await expect(pageB.getByText("Project not found", { exact: true })).toBeVisible();
  await ctxB.close();

  // Raw API: B cannot search A's project (404, non-disclosing).
  const loginB = await request.post("http://127.0.0.1:8000/api/v1/auth/login", {
    data: { email: `knowb-${stamp}@example.com`, password: "E2eSecure123" },
  });
  expect(loginB.ok()).toBeTruthy();
  const tokenB = (await loginB.json()).access_token;
  const denied = await request.post(
    `http://127.0.0.1:8000/api/v1/projects/${projectId}/knowledge/search`,
    { headers: { Authorization: `Bearer ${tokenB}` }, data: { query: "Photosynthesis" } },
  );
  expect(denied.status()).toBe(404);
});
