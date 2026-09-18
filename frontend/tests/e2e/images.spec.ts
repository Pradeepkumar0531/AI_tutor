import { expect, test, type Page } from "@playwright/test";

import { E2E_FIXTURE_PDF } from "./global-setup";

/**
 * Embedded-image journey on the real stack (TEST_FAKE_AI only affects AI
 * providers; image extraction/storage is always production code):
 *
 * login → project → upload PDF with an embedded raster → worker extracts →
 * READY → open material → image visible with exact page provenance →
 * reload → still available → logout → protected routes blocked.
 * Tenant B cannot list, read, or fetch bytes of tenant A's images (UI + API).
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
  await page.getByLabel("Name").fill(`Images ${stamp}`);
  await page.getByRole("button", { name: "Create space", exact: true }).click();
  await page.getByRole("link", { name: new RegExp(`Open space Images ${stamp}`) }).click();
  await page.waitForURL(/\/spaces\/.+/);
  await page.getByRole("button", { name: "New Project" }).click();
  await page.getByLabel("Name").fill(`Illustrated ${stamp}`);
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
  await page.getByRole("link", { name: "Overview", exact: true }).click();
  await expect(page.getByText("READY").first()).toBeVisible({ timeout: 120_000 });
  await expect(page.getByText("2/2 chunks embedded")).toBeVisible({ timeout: 120_000 });
  return { projectUrl, projectId };
}

test("embedded images extract, display with provenance, and persist", async ({ page }) => {
  test.setTimeout(300_000);
  const stamp = Date.now();
  await register(page, `images-${stamp}@example.com`);
  const { projectUrl } = await makeProjectWithPdf(page, stamp, "Illustrated bio");

  // Material detail surfaces real counts and the Images section.
  await page.getByRole("link", { name: "Materials", exact: true }).click();
  await page.getByRole("link", { name: /Open material Illustrated bio/ }).click();
  await page.waitForURL(/\/materials\/.+/);
  const materialUrl = page.url();
  const materialId = materialUrl.split("/materials/")[1] as string;
  await expect(page.getByText("1 image")).toBeVisible({ timeout: 30_000 });
  await expect(page.getByText("Page 1 · Image 1")).toBeVisible({ timeout: 30_000 });
  await expect(page.getByText("300×200")).toBeVisible();
  await expect(page.getByText("image/png")).toBeVisible();
  // The thumbnail loads real bytes through the authenticated content endpoint.
  const thumb = page.getByAltText("Extracted image 1 from page 1");
  await expect(thumb).toBeVisible({ timeout: 30_000 });
  expect(await thumb.getAttribute("src")).toMatch(/^blob:/);

  // Reload: images persist server-side.
  await page.reload();
  await expect(page.getByText("Page 1 · Image 1")).toBeVisible({ timeout: 60_000 });
  await expect(page.getByAltText("Extracted image 1 from page 1")).toBeVisible({
    timeout: 30_000,
  });

  // Logout gates the workspace again.
  await page.getByRole("button", { name: "Account: E2E Learner" }).click();
  await page.getByRole("menuitem", { name: /sign out/i }).click();
  await expect(page.getByRole("heading", { name: /welcome back/i })).toBeVisible();
  await page.goto(projectUrl);
  await expect(page.getByRole("heading", { name: /welcome back/i })).toBeVisible();
  await page.goto(materialUrl);
  await expect(page.getByRole("heading", { name: /welcome back/i })).toBeVisible();
  void materialId;
});

test("image isolation across tenants", async ({ page, browser, request }) => {
  test.setTimeout(300_000);
  const stamp = Date.now();
  await register(page, `imga-${stamp}@example.com`);
  const { projectUrl } = await makeProjectWithPdf(page, stamp, "Private pictures");
  const projectId = projectUrl.split("/projects/")[1].split("/")[0] as string;

  await page.getByRole("link", { name: "Materials", exact: true }).click();
  await page.getByRole("link", { name: /Open material Private pictures/ }).click();
  await page.waitForURL(/\/materials\/.+/);
  const materialId = page.url().split("/materials/")[1] as string;
  await expect(page.getByText("Page 1 · Image 1")).toBeVisible({ timeout: 60_000 });

  // Second tenant cannot open A's project at all.
  const ctxB = await browser.newContext();
  const pageB = await ctxB.newPage();
  await register(pageB, `imgb-${stamp}@example.com`);
  await pageB.goto(projectUrl);
  await expect(pageB.getByText("Project not found", { exact: true })).toBeVisible();
  await ctxB.close();

  // Raw API: B gets 404 on list, metadata, and bytes (non-disclosing).
  const loginB = await request.post("http://127.0.0.1:8000/api/v1/auth/login", {
    data: { email: `imgb-${stamp}@example.com`, password: "E2eSecure123" },
  });
  expect(loginB.ok()).toBeTruthy();
  const headersB = { Authorization: `Bearer ${(await loginB.json()).access_token}` };
  const base = `http://127.0.0.1:8000/api/v1/projects/${projectId}/materials/${materialId}`;
  expect((await request.get(`${base}/images`, { headers: headersB })).status()).toBe(404);

  const loginA = await request.post("http://127.0.0.1:8000/api/v1/auth/login", {
    data: { email: `imga-${stamp}@example.com`, password: "E2eSecure123" },
  });
  const headersA = { Authorization: `Bearer ${(await loginA.json()).access_token}` };
  const listed = await request.get(`${base}/images`, { headers: headersA });
  expect(listed.ok()).toBeTruthy();
  const imageId = (await listed.json()).items[0].id as string;
  expect((await request.get(`${base}/images/${imageId}`, { headers: headersB })).status()).toBe(
    404,
  );
  expect(
    (await request.get(`${base}/images/${imageId}/content`, { headers: headersB })).status(),
  ).toBe(404);
  const content = await request.get(`${base}/images/${imageId}/content`, {
    headers: headersA,
  });
  expect(content.ok()).toBeTruthy();
  expect(content.headers()["content-type"]).toBe("image/png");
});
