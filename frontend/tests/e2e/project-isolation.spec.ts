import { expect, test, type Page } from "@playwright/test";

import { E2E_FIXTURE_PDF } from "./global-setup";

/**
 * Project data isolation at the UI level (server enforcement is covered by
 * backend/tests/test_project_idor.py — every cross-project access 404s).
 *
 * Tutor A/B: conversation + messages created in Project A must never render
 * under Project B (previously the global tutor store kept A's selection and
 * messages visible after navigation). Quiz A/B: each project lists and
 * generates only its own quizzes.
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

async function makeProject(page: Page, space: string, project: string) {
  await page.goto("/spaces");
  await page.getByRole("button", { name: "New Space", exact: true }).click();
  await page.getByLabel("Name").fill(space);
  await page.getByRole("button", { name: "Create space", exact: true }).click();
  await page.getByRole("link", { name: new RegExp(`Open space ${space}`) }).click();
  await page.waitForURL(/\/spaces\/.+/);
  await page.getByRole("button", { name: "New Project" }).click();
  await page.getByLabel("Name").fill(project);
  await page.getByRole("button", { name: "Create project", exact: true }).click();
  await page.waitForURL(/\/projects\/.+/);
  return (page.url().split("/projects/")[1] as string).split("/")[0] as string;
}

async function ask(page: Page, question: string) {
  await page.getByLabel("Ask the tutor").fill(question);
  await page.getByRole("button", { name: /^send$/i }).click();
}

async function uploadPdfAndWaitKnowledge(page: Page, projectId: string, title: string) {
  await page.goto(`/projects/${projectId}/materials`);
  await page.getByRole("button", { name: "Upload PDF" }).click();
  await page.getByLabel(/Title/).fill(title);
  await page.locator('input[type="file"]').setInputFiles(E2E_FIXTURE_PDF);
  await page.getByRole("button", { name: "Upload", exact: true }).click();
  const card = page.getByRole("link", { name: `Open material ${title}` });
  await expect(card).toBeVisible();
  await expect(card.getByText("Ready")).toBeVisible({ timeout: 120_000 });
  // Quiz generation needs embedded chunks + concepts, not just READY material.
  await page.goto(`/projects/${projectId}/overview`);
  await expect(page.getByText("READY").first()).toBeVisible({ timeout: 120_000 });
  await expect(page.getByText("2/2 chunks embedded")).toBeVisible({ timeout: 120_000 });
  await expect(page.getByRole("button", { name: /Photosynthesis/ })).toBeVisible({
    timeout: 120_000,
  });
}

test("tutor conversations never leak across projects", async ({ page }) => {
  test.setTimeout(240_000);
  const stamp = Date.now();
  await register(page, `iso-${stamp}@example.com`);
  const projectA = await makeProject(page, `IsoSpace ${stamp}`, `IsoA ${stamp}`);
  const projectB = await makeProject(page, `IsoSpaceB ${stamp}`, `IsoB ${stamp}`);

  // Project A: chat once (no materials needed for a general question).
  await page.goto(`/projects/${projectA}/tutor`);
  await expect(page.getByLabel("Ask the tutor")).toBeEnabled({ timeout: 30_000 });
  await ask(page, `A1-marker-question-${stamp}`);
  await expect(page.getByText(`A1-marker-question-${stamp}`).first()).toBeVisible({
    timeout: 30_000,
  });

  // Project B: A's conversation must not be visible; empty state instead.
  await page.goto(`/projects/${projectB}/tutor`);
  await expect(page.getByLabel("Ask the tutor")).toBeEnabled({ timeout: 30_000 });
  await expect(page.getByText("Ask about your materials.")).toBeVisible({ timeout: 30_000 });
  await expect(page.getByText(`A1-marker-question-${stamp}`)).toHaveCount(0);

  // Chat in B; B1 must exist only in B.
  await ask(page, `B1-marker-question-${stamp}`);
  await expect(page.getByText(`B1-marker-question-${stamp}`).first()).toBeVisible({
    timeout: 30_000,
  });
  await expect(page.getByText(`A1-marker-question-${stamp}`)).toHaveCount(0);

  // Back to A: A1 visible, B1 absent (persistence intact, no cross-talk).
  await page.goto(`/projects/${projectA}/tutor`);
  await expect(page.getByText(`A1-marker-question-${stamp}`).first()).toBeVisible({
    timeout: 30_000,
  });
  await expect(page.getByText(`B1-marker-question-${stamp}`)).toHaveCount(0);

  // And B once more: B1 visible, A1 absent.
  await page.goto(`/projects/${projectB}/tutor`);
  await expect(page.getByText(`B1-marker-question-${stamp}`).first()).toBeVisible({
    timeout: 30_000,
  });
  await expect(page.getByText(`A1-marker-question-${stamp}`)).toHaveCount(0);
});

test("quizzes never leak across projects", async ({ page }) => {
  test.setTimeout(300_000);
  const stamp = Date.now();
  await register(page, `isoq-${stamp}@example.com`);
  const projectA = await makeProject(page, `IsoQSpace ${stamp}`, `IsoQA ${stamp}`);
  const projectB = await makeProject(page, `IsoQSpaceB ${stamp}`, `IsoQB ${stamp}`);

  await uploadPdfAndWaitKnowledge(page, projectA, `IsoQ bio A ${stamp}`);
  await uploadPdfAndWaitKnowledge(page, projectB, `IsoQ bio B ${stamp}`);

  // Generate in A: detail shows 5 questions, list holds exactly one quiz.
  await page.goto(`/projects/${projectA}/quiz`);
  await page.getByRole("button", { name: /generate quiz/i }).click();
  await expect(page.getByRole("button", { name: /start attempt/i })).toBeVisible({
    timeout: 120_000,
  });
  await expect(page.getByText("5 questions").first()).toBeVisible();
  await page.getByRole("button", { name: /all quizzes/i }).click();
  await expect(page.getByText("No quizzes yet.")).toHaveCount(0);
  // Generated quizzes carry a real concept-derived title (never "Untitled").
  await expect(page.getByText("Untitled quiz")).toHaveCount(0);
  await expect(page.getByText(/Practice Quiz/)).toHaveCount(1, { timeout: 30_000 });

  // B starts empty — nothing from A leaks.
  await page.goto(`/projects/${projectB}/quiz`);
  await expect(page.getByText("No quizzes yet.")).toBeVisible({ timeout: 30_000 });
  await expect(page.getByText(/Practice Quiz/)).toHaveCount(0);

  // Generate in B as well; each side still holds exactly its own quiz.
  await page.getByRole("button", { name: /generate quiz/i }).click();
  await expect(page.getByRole("button", { name: /start attempt/i })).toBeVisible({
    timeout: 120_000,
  });
  await page.getByRole("button", { name: /all quizzes/i }).click();
  await expect(page.getByText(/Practice Quiz/)).toHaveCount(1, { timeout: 30_000 });
  await page.goto(`/projects/${projectA}/quiz`);
  await expect(page.getByText(/Practice Quiz/)).toHaveCount(1, { timeout: 30_000 });
});
