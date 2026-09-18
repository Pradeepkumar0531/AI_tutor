import { readFileSync } from "node:fs";
import { expect, test, type Page } from "@playwright/test";

import { E2E_FIXTURE_PDF } from "./global-setup";

/**
 * Real upload-to-READY journey: UI upload -> persisted QUEUED -> real Celery
 * worker (separate process, filesystem broker) extracts + chunks -> UI polls
 * to READY -> document inspection -> refresh persists -> logout gates.
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

async function makeProject(page: Page, stamp: number, space: string, project: string) {
  await page.goto("/spaces");
  await page.getByRole("button", { name: "New Space", exact: true }).click();
  await page.getByLabel("Name").fill(`${space} ${stamp}`);
  await page.getByRole("button", { name: "Create space", exact: true }).click();
  await expect(page.getByText(`${space} ${stamp}`)).toBeVisible();
  await page.getByRole("link", { name: new RegExp(`Open space ${space} ${stamp}`) }).click();
  await page.waitForURL(/\/spaces\/.+/);
  await page.getByRole("button", { name: "New Project" }).click();
  await page.getByLabel("Name").fill(`${project} ${stamp}`);
  await page.getByRole("button", { name: "Create project", exact: true }).click();
  await page.waitForURL(/\/projects\/.+/);
  // Uploads live on the Materials tab; hand off there.
  await page.getByRole("link", { name: "Materials", exact: true }).click();
  return page.url();
}

test("upload PDF, worker processes it, inspect content", async ({ page }) => {
  test.setTimeout(180_000);
  const stamp = Date.now();
  await register(page, `materials-${stamp}@example.com`);
  await makeProject(page, stamp, "Biology", "Cells");

  // Upload through the real dialog.
  await page.getByRole("button", { name: "Upload PDF" }).click();
  await page.getByLabel(/Title/).fill("Cell notes");
  await page.locator('input[type="file"]').setInputFiles(E2E_FIXTURE_PDF);
  await page.getByRole("button", { name: "Upload", exact: true }).click();

  // Material appears immediately as QUEUED/PROCESSING (never fake READY)...
  // The Ready wait is scoped to the card: a global text match could catch an
  // unrelated badge while this worker-driven row is still queued.
  const card = page.getByRole("link", { name: /Open material Cell notes/ });
  await expect(card).toBeVisible();
  // ...then the real worker drives it to READY (polling, no browser tricks).
  await expect(card.getByText("Ready")).toBeVisible({ timeout: 120_000 });

  // Open the material: real metadata, page refs, extracted content.
  await card.click();
  await page.waitForURL(/\/materials\/.+/);
  await expect(page.getByText("2 pages", { exact: true }).first()).toBeVisible({ timeout: 30_000 });
  await expect(page.getByText("Photosynthesis converts sunlight")).toBeVisible({
    timeout: 30_000,
  });
  await expect(page.getByText("Mitochondria release that energy")).toBeVisible({
    timeout: 30_000,
  });

  // Refresh: READY persists server-side.
  await page.reload();
  await expect(page.getByText("Photosynthesis converts sunlight")).toBeVisible();

  // Logout gates the workspace again.
  await page.getByRole("button", { name: "Account: E2E Learner" }).click();
  await page.getByRole("menuitem", { name: /sign out/i }).click();
  await expect(page.getByRole("heading", { name: /welcome back/i })).toBeVisible();
});

test("failed upload surfaces honestly, retry control is real", async ({ page }) => {
  test.setTimeout(120_000);
  const stamp = Date.now();
  await register(page, `failures-${stamp}@example.com`);
  await makeProject(page, stamp, "Chemistry", "Atoms");

  await page.getByRole("button", { name: "Upload PDF" }).click();
  // Client-side validation rejects non-PDFs before any request.
  await page.locator('input[type="file"]').setInputFiles({
    name: "notes.txt",
    mimeType: "text/plain",
    buffer: Buffer.from("not a pdf"),
  });
  await expect(page.getByText("Only PDF files are accepted.")).toBeVisible();
  await page.keyboard.press("Escape");

  // A corrupt PDF passes the header check client-side but the worker fails it.
  await page.getByRole("button", { name: "Upload PDF" }).click();
  await page.locator('input[type="file"]').setInputFiles({
    name: "broken.pdf",
    mimeType: "application/pdf",
    buffer: Buffer.from("%PDF-1.4\n\x00\xff garbage, no objects here"),
  });
  await page.getByRole("button", { name: "Upload", exact: true }).click();
  await expect(page.getByText("broken.pdf")).toBeVisible();
  await expect(page.getByText("Failed")).toBeVisible({ timeout: 120_000 });
});

test("tenant B cannot touch tenant A's material or document", async ({ page, request }) => {
  test.setTimeout(180_000);
  const stamp = Date.now();
  await register(page, `materia-${stamp}@example.com`);
  const projectUrl = await makeProject(page, stamp, "Geology", "Rocks");

  await page.getByRole("button", { name: "Upload PDF" }).click();
  await page.locator('input[type="file"]').setInputFiles(E2E_FIXTURE_PDF);
  await page.getByRole("button", { name: "Upload", exact: true }).click();
  const uploadedCard = page.getByRole("link", { name: /Open material/ }).first();
  await expect(uploadedCard).toBeVisible();
  await expect(uploadedCard.getByText("Ready")).toBeVisible({ timeout: 120_000 });
  await uploadedCard.click();
  await page.waitForURL(/\/materials\/.+/);
  const materialUrl = page.url();
  const materialId = materialUrl.split("/materials/")[1];
  const projectId = projectUrl.split("/projects/")[1].split("/")[0];

  // Second tenant via raw API (real backend authorization, no UI shortcuts).
  const regB = await request.post("http://127.0.0.1:8000/api/v1/auth/register", {
    data: { email: `materib-${stamp}@example.com`, password: "E2eSecure123", display_name: "B" },
  });
  expect(regB.ok()).toBeTruthy();
  const tokenB = (await regB.json()).access_token;
  const headers = { Authorization: `Bearer ${tokenB}` };
  const api = "http://127.0.0.1:8000/api/v1";

  for (const [method, url] of [
    ["GET", `${api}/projects/${projectId}/materials/${materialId}`],
    ["GET", `${api}/projects/${projectId}/materials/${materialId}/document`],
    ["GET", `${api}/projects/${projectId}/materials/${materialId}/document/chunks`],
    ["POST", `${api}/projects/${projectId}/materials/${materialId}/reprocess`],
    ["DELETE", `${api}/projects/${projectId}/materials/${materialId}`],
  ] as const) {
    let res;
    if (method === "GET") res = await request.get(url, { headers });
    else if (method === "DELETE") res = await request.delete(url, { headers });
    else res = await request.post(url, { headers });
    expect(res.status(), `${method} ${url}`).toBe(404);
  }
  // Upload into A's project (with a real file, so routing reaches authz).
  const sneaky = await request.post(`${api}/projects/${projectId}/materials`, {
    headers,
    multipart: {
      file: {
        name: "sneak.pdf",
        mimeType: "application/pdf",
        buffer: readFileSync(E2E_FIXTURE_PDF),
      },
    },
  });
  expect(sneaky.status()).toBe(404);

  // And B's browser sees a non-disclosing 404 on A's URL.
  await page.goto("/login");
  await page.getByRole("button", { name: "Account: E2E Learner" }).click();
  await page.getByRole("menuitem", { name: /sign out/i }).click();
  await expect(page.getByRole("heading", { name: /welcome back/i })).toBeVisible();
  await page.goto("/login");
  await expect(page.getByLabel("Email")).toBeVisible();
  await page.getByLabel("Email").fill(`materib-${stamp}@example.com`);
  await page.getByLabel("Password").fill("E2eSecure123");
  await page.getByRole("button", { name: /sign in/i }).click();
  await page.waitForURL("/");
  await page.goto(materialUrl);
  await expect(page.getByText("Material not found", { exact: true })).toBeVisible();
});
