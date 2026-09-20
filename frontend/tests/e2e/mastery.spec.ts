import { expect, test, type Page } from "@playwright/test";

import { E2E_FIXTURE_PDF } from "./global-setup";

/**
 * Mastery journey with deterministic fake AI (TEST_FAKE_AI — no keys, no
 * network). The mastery algorithm itself is always the real production code:
 * login → project → upload → READY knowledge → quiz → complete →
 * synchronous mastery update → mastery list/detail/history → second
 * assessment moves estimates → reload persists → logout. A second test
 * closes the loop: assessment performance → persisted mastery → next quiz
 * selection.
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
  await page.getByLabel("Name").fill(`Mastery ${stamp}`);
  await page.getByRole("button", { name: "Create space", exact: true }).click();
  await page.getByRole("link", { name: new RegExp(`Open space Mastery ${stamp}`) }).click();
  await page.waitForURL(/\/spaces\/.+/);
  await page.getByRole("button", { name: "New Project" }).click();
  await page.getByLabel("Name").fill(`Mastered ${stamp}`);
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
  await expect(card).toBeVisible({ timeout: 30_000 });
  await expect(card.getByText("Ready")).toBeVisible({ timeout: 120_000 });
  // Full worker completion: badge/counter-only waits race embedding.
  await page.getByRole("link", { name: "Overview", exact: true }).click();
  await expect(page.getByText("READY").first()).toBeVisible({ timeout: 120_000 });
  await expect(page.getByText("2/2 chunks embedded")).toBeVisible({ timeout: 120_000 });
  await expect(page.getByRole("button", { name: /Photosynthesis/ })).toBeVisible({
    timeout: 120_000,
  });
  return projectUrl;
}

async function generateMcqQuiz(page: Page, count: string) {
  await page.getByRole("link", { name: "Quiz", exact: true }).click();
  await page.getByLabel("Number of questions").fill(count);
  await page.getByLabel("Open-ended").uncheck();
  await page.getByRole("button", { name: "Generate quiz" }).click();
  await expect(page.getByRole("button", { name: "Start attempt" })).toBeVisible({
    timeout: 60_000,
  });
  await page.getByRole("button", { name: "Start attempt" }).click();
  await expect(page.getByText(/Answered 0 of/)).toBeVisible({ timeout: 30_000 });
}

async function answerAllCorrect(page: Page) {
  const count = await page.getByRole("radiogroup").count();
  for (let i = 0; i < count; i++) {
    await page.getByRole("radiogroup").nth(i).getByRole("radio").first().check();
  }
  await expect(page.getByRole("button", { name: "Submit answer" })).toHaveCount(0);
  await page.getByRole("button", { name: "Submit Quiz" }).click();
}

test("mastery updates, detail, history, and persistence", async ({ page }) => {
  test.setTimeout(300_000);
  const stamp = Date.now();
  await register(page, `mastery-${stamp}@example.com`);
  const projectUrl = await makeProjectWithPdf(page, stamp, "Mastery bio");

  await page.getByRole("link", { name: "Growth", exact: true }).click();
  await expect(page.getByText("No mastery yet.")).toBeVisible({ timeout: 30_000 });

  await generateMcqQuiz(page, "2");
  const labels = await page.getByText(/Concepts: /).allTextContents();
  expect(labels.length).toBe(2);
  const firstConcept = labels[0]?.replace("Concepts: ", "").split(",")[0]?.trim() ?? "";
  expect(firstConcept).not.toBe("");
  await answerAllCorrect(page);
  await expect(page.getByText("Assessment result")).toBeVisible({ timeout: 60_000 });

  // Completion drove synchronous mastery updates for the assessed concepts.
  await page.getByRole("button", { name: "Back to quizzes" }).click();
  await page.getByRole("link", { name: "Growth", exact: true }).click();
  const masteryRow = page
    .locator("li")
    .filter({ hasText: firstConcept })
    .filter({ hasText: /Mastery \d+%/ });
  await expect(masteryRow).toBeVisible({ timeout: 30_000 });
  await masteryRow.getByRole("button").click();

  // Detail: score, confidence, trend, evidence, recent, history transition.
  await expect(page.getByRole("heading", { name: `Concept: ${firstConcept}` })).toBeVisible({
    timeout: 30_000,
  });
  await expect(page.getByText("Recent performance")).toBeVisible();
  await expect(page.getByText("History")).toBeVisible();
  const detailBody = (await page.textContent("body")) ?? "";
  expect(detailBody).toContain("63%");
  await page.getByRole("button", { name: "All concepts" }).click();

  // Second assessment, all wrong: estimates must move down, history grows.
  await page.getByRole("link", { name: "Quiz", exact: true }).click();
  await page.getByLabel("Number of questions").fill("2");
  await page.getByRole("button", { name: "Generate quiz" }).click();
  await expect(page.getByRole("button", { name: "Start attempt" })).toBeVisible({
    timeout: 60_000,
  });
  await page.getByRole("button", { name: "Start attempt" }).click();
  await expect(page.getByText(/Answered 0 of/)).toBeVisible({ timeout: 30_000 });
  const wrongCount = await page.getByRole("radiogroup").count();
  for (let i = 0; i < wrongCount; i++) {
    await page.getByRole("radiogroup").nth(i).getByRole("radio").nth(1).check();
  }
  await page.getByRole("button", { name: "Submit Quiz" }).click();
  await expect(page.getByText("Assessment result")).toBeVisible({ timeout: 60_000 });
  await expect(page.getByText("0%", { exact: true }).first()).toBeVisible();

  // Reload: mastery persists server-side.
  await page.reload();
  await page.getByRole("link", { name: "Growth", exact: true }).click();
  await expect(page.getByText(firstConcept).first()).toBeVisible({ timeout: 60_000 });

  // Logout gates the workspace again.
  await page.getByRole("button", { name: "Account: E2E Learner" }).click();
  await page.getByRole("menuitem", { name: /sign out/i }).click();
  await expect(page.getByRole("heading", { name: /welcome back/i })).toBeVisible();
  await page.goto(projectUrl);
  await expect(page.getByRole("heading", { name: /welcome back/i })).toBeVisible();
});

test("assessment performance flows into next quiz selection", async ({ page }) => {
  test.setTimeout(300_000);
  const stamp = Date.now();
  await register(page, `mloop-${stamp}@example.com`);
  await makeProjectWithPdf(page, stamp, "Loop bio");

  await generateMcqQuiz(page, "2");
  const labels = await page.getByText(/Concepts: /).allTextContents();
  expect(labels).toHaveLength(2);
  const missed = labels[0]?.replace("Concepts: ", "").split(",")[0]?.trim() ?? "";
  expect(missed).not.toBe("");

  // First question wrong, second right: mixed evidence.
  expect(await page.getByRole("radiogroup").count()).toBe(2);
  await page.getByRole("radiogroup").nth(0).getByRole("radio").nth(1).check();
  await page.getByRole("radiogroup").nth(1).getByRole("radio").first().check();
  await page.getByRole("button", { name: "Submit Quiz" }).click();
  await expect(page.getByText("50%", { exact: true }).first()).toBeVisible({ timeout: 60_000 });

  // Persisted mastery for the missed concept sits below 50% (0.375 -> 38%).
  await page.getByRole("button", { name: "Back to quizzes" }).click();
  await page.getByRole("link", { name: "Growth", exact: true }).click();
  const missedRow = page
    .locator("li")
    .filter({ hasText: missed })
    .filter({ hasText: /Mastery \d+%/ });
  await expect(missedRow).toBeVisible({ timeout: 30_000 });
  await missedRow.getByRole("button").click();
  await expect(page.getByRole("heading", { name: `Concept: ${missed}` })).toBeVisible({
    timeout: 30_000,
  });
  const detailBody = (await page.textContent("body")) ?? "";
  expect(detailBody).toContain("38%");
  await page.getByRole("button", { name: "All concepts" }).click();

  // Next quiz: the low-mastery concept resurfaces despite unseen alternatives.
  await page.getByRole("link", { name: "Quiz", exact: true }).click();
  await page.getByLabel("Number of questions").fill("2");
  await page.getByLabel("Open-ended").uncheck();
  await page.getByRole("button", { name: "Generate quiz" }).click();
  await expect(page.getByRole("button", { name: "Start attempt" })).toBeVisible({
    timeout: 60_000,
  });
  await page.getByRole("button", { name: "Start attempt" }).click();
  await expect(page.getByText(/Answered 0 of/)).toBeVisible({ timeout: 30_000 });
  await expect(page.getByText(`Concepts: ${missed}`).first()).toBeVisible({
    timeout: 30_000,
  });
});
