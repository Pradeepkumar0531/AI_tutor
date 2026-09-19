import { expect, test, type Page } from "@playwright/test";

import { E2E_FIXTURE_PDF } from "./global-setup";

/**
 * Assessment journey with deterministic fake AI (TEST_FAKE_AI — no keys, no
 * network): login → project → upload → READY knowledge → generate quiz →
 * READY → start attempt → answer MCQ + open-ended → complete → assessment
 * with concept performance → reload → result persists → logout.
 *
 * Fake-AI contracts exercised here (documented test doubles, never prod):
 * generated MCQ correct answers are always the first option; open-ended
 * evaluation scores word overlap with the reference sentence.
 */

const CHUNK_ONE = "Photosynthesis converts sunlight into chemical energy. Page one.";
const CHUNK_TWO = "Mitochondria release that energy as ATP. Page two.";

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
  await page.getByLabel("Name").fill(`Quiz ${stamp}`);
  await page.getByRole("button", { name: "Create space", exact: true }).click();
  await page.getByRole("link", { name: new RegExp(`Open space Quiz ${stamp}`) }).click();
  await page.waitForURL(/\/spaces\/.+/);
  await page.getByRole("button", { name: "New Project" }).click();
  await page.getByLabel("Name").fill(`Assessed ${stamp}`);
  await page.getByRole("button", { name: "Create project", exact: true }).click();
  await page.waitForURL(/\/projects\/.+/);
  const projectUrl = page.url();

  // Uploads live on the Materials tab; knowledge status on Overview.
  await page.getByRole("link", { name: "Materials", exact: true }).click();
  await page.getByRole("button", { name: "Upload PDF" }).click();
  await page.getByLabel(/Title/).fill(title);
  await page.locator('input[type="file"]').setInputFiles(E2E_FIXTURE_PDF);
  await page.getByRole("button", { name: "Upload", exact: true }).click();
  // Scoped to the material card: the dashboard summary also renders
  // "ready" text, so a global text match is ambiguous.
  const card = page.getByRole("link", { name: `Open material ${title}` });
  await expect(card).toBeVisible({ timeout: 120_000 });
  await expect(card.getByText("Ready")).toBeVisible({ timeout: 120_000 });
  // Quiz generation needs embedded chunks AND extracted concepts: gate on
  // full worker completion (badge/counter-only waits race embedding).
  await page.getByRole("link", { name: "Overview", exact: true }).click();
  await expect(page.getByText("READY").first()).toBeVisible({ timeout: 120_000 });
  await expect(page.getByText("2/2 chunks embedded")).toBeVisible({ timeout: 120_000 });
  await expect(page.getByRole("button", { name: /Photosynthesis/ })).toBeVisible({
    timeout: 120_000,
  });
  return projectUrl;
}

async function generateQuiz(page: Page, count: string, mcqOnly = false) {
  await page.getByRole("link", { name: "Quiz", exact: true }).click();
  await expect(page.getByText("No quizzes yet.")).toBeVisible({ timeout: 30_000 });
  await page.getByLabel("Number of questions").fill(count);
  if (mcqOnly) {
    await page.getByLabel("Open-ended").uncheck();
  }
  await page.getByRole("button", { name: "Generate quiz" }).click();
  await expect(page.getByRole("button", { name: "Start attempt" })).toBeVisible({
    timeout: 60_000,
  });
  await page.getByRole("button", { name: "Start attempt" }).click();
  await expect(page.getByText(/Answered 0 of/)).toBeVisible({ timeout: 30_000 });
}

test("quiz journey: generate, answer, complete, result persists", async ({ page }) => {
  test.setTimeout(300_000);
  const stamp = Date.now();
  await register(page, `quiz-${stamp}@example.com`);
  const projectUrl = await makeProjectWithPdf(page, stamp, "Quiz bio");

  await generateQuiz(page, "3");

  // Fill every answer first (MCQ: first option is correct by fake-AI
  // contract; open-ended: both chunk sentences cover any reference), then
  // submit one by one — submits after the first wait for the in-flight
  // request via the disabled state.
  const mcqCount = await page.getByRole("radiogroup").count();
  const openCount = await page.getByLabel(/Answer for question/).count();
  expect(mcqCount + openCount).toBe(3);
  for (let i = 0; i < mcqCount; i++) {
    await page.getByRole("radiogroup").nth(i).getByRole("radio").first().check();
  }
  for (let i = 0; i < openCount; i++) {
    await page
      .getByLabel(/Answer for question/)
      .nth(i)
      .fill(`${CHUNK_ONE} ${CHUNK_TWO}`);
  }
  for (let i = 0; i < mcqCount + openCount; i++) {
    await page.getByRole("button", { name: "Submit answer" }).first().click();
  }
  await expect(page.getByText(/Answered 3 of 3/)).toBeVisible({ timeout: 60_000 });

  await page.getByRole("button", { name: "Finish and see results" }).click();
  await expect(page.getByText("Assessment result")).toBeVisible({ timeout: 30_000 });
  await expect(page.getByText("100%", { exact: true }).first()).toBeVisible();
  await expect(page.getByText("Concept performance")).toBeVisible();

  // Reload: server state restores the result through history.
  await page.reload();
  await expect(page.getByText("Past results")).toBeVisible({ timeout: 60_000 });
  await page.getByRole("button", { name: /100%/ }).first().click();
  await expect(page.getByText("Assessment result")).toBeVisible({ timeout: 30_000 });
  await expect(page.getByText("Concept performance")).toBeVisible();

  // Logout gates the workspace again.
  await page.getByRole("button", { name: "Account: E2E Learner" }).click();
  await page.getByRole("menuitem", { name: /sign out/i }).click();
  await expect(page.getByRole("heading", { name: /welcome back/i })).toBeVisible();
  await page.goto(projectUrl);
  await expect(page.getByRole("heading", { name: /welcome back/i })).toBeVisible();
});

test("adaptive selection resurfaces missed concepts", async ({ page }) => {
  test.setTimeout(300_000);
  const stamp = Date.now();
  await register(page, `adap-${stamp}@example.com`);
  await makeProjectWithPdf(page, stamp, "Adaptive bio");

  await generateQuiz(page, "2", true);

  // Read the two assessed concepts straight from the UI: first question
  // answered WRONG, second one RIGHT.
  const labels = await page.getByText(/Concepts: /).allTextContents();
  expect(labels).toHaveLength(2);
  const missed = labels[0]?.replace("Concepts: ", "").split(",")[0]?.trim() ?? "";
  expect(missed).not.toBe("");

  expect(await page.getByRole("radiogroup").count()).toBe(2);
  await page.getByRole("radiogroup").nth(0).getByRole("radio").nth(1).check();
  await page.getByRole("radiogroup").nth(1).getByRole("radio").first().check();
  for (let i = 0; i < 2; i++) {
    await page.getByRole("button", { name: "Submit answer" }).first().click();
  }
  await expect(page.getByText(/Answered 2 of 2/)).toBeVisible({ timeout: 60_000 });
  await page.getByRole("button", { name: "Finish and see results" }).click();
  await expect(page.getByText("50%", { exact: true }).first()).toBeVisible({ timeout: 30_000 });

  // Second quiz: the missed concept must resurface (mistake-weighted
  // selection), even though unseen concepts remain.
  await page.getByRole("button", { name: "Back to quizzes" }).click();
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
