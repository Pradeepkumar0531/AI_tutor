import { readFileSync } from "node:fs";

import { expect, test, type APIRequestContext, type Page } from "@playwright/test";

import { E2E_FIXTURE_PDF } from "./global-setup";

/**
 * Admin journey (RBAC is server-side; the UI only hides links):
 *
 * learner API → /admin/* denied (403) · learner UI → denial page ·
 * admin register (ADMIN_EMAILS bootstrap) → /admin overview/users/activity/
 * jobs/health/AI usage/evaluation → inspect learner → run evaluation suite.
 */

const API = "http://127.0.0.1:8000/api/v1";

async function register(request: APIRequestContext, email: string) {
  const res = await request.post(`${API}/auth/register`, {
    data: { email, password: "E2eSecure123", display_name: "E2E" },
  });
  expect(res.ok()).toBeTruthy();
  return (await res.json()) as { access_token: string; user: { id: string; role: string } };
}

async function registerThroughUi(page: Page, email: string) {
  await page.goto("/register");
  await page.getByLabel("Display name").fill("E2E Learner");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel(/^Password$/).fill("E2eSecure123");
  await page.getByLabel("Confirm password").fill("E2eSecure123");
  await page.getByRole("button", { name: /create account/i }).click();
  await page.waitForURL("/");
}

test("admin journey: RBAC denial, dashboard, users, jobs, health, evaluation", async ({
  page,
  request,
}) => {
  test.setTimeout(300_000);
  const stamp = Date.now();

  // Learner: every admin API denied, UI shows the denial page (no data).
  const learner = await register(request, `learner-${stamp}@example.com`);
  expect(learner.user.role).toBe("learner");
  const learnerHeaders = { Authorization: `Bearer ${learner.access_token}` };
  expect((await request.get(`${API}/admin/overview`, { headers: learnerHeaders })).status()).toBe(
    403,
  );
  expect((await request.get(`${API}/admin/users`, { headers: learnerHeaders })).status()).toBe(403);
  await registerThroughUi(page, `ui-learner-${stamp}@example.com`);
  await page.goto("/admin");
  await expect(page.getByText("Admin access required")).toBeVisible();
  // No Admin nav link for learners.
  await expect(page.getByRole("link", { name: "Admin", exact: true })).toHaveCount(0);
  // Sign out through the user menu (same pattern as auth.spec.ts).
  await page.getByRole("button", { name: "Account: E2E Learner" }).click();
  await page.getByRole("menuitem", { name: /sign out/i }).click();
  await expect(page.getByRole("heading", { name: /welcome back/i })).toBeVisible();

  // Admin bootstrap via ADMIN_EMAILS, then UI login.
  const admin = await register(request, "e2e-admin@example.com");
  expect(admin.user.role).toBe("admin");
  const adminHeaders = { Authorization: `Bearer ${admin.access_token}` };

  const overview = await request.get(`${API}/admin/overview`, { headers: adminHeaders });
  expect(overview.ok()).toBeTruthy();
  const stats = await overview.json();
  expect(stats.users).toBeGreaterThanOrEqual(2);
  expect(stats.jobs).toBeDefined();

  const users = await request.get(`${API}/admin/users?limit=10`, { headers: adminHeaders });
  expect(users.ok()).toBeTruthy();
  expect((await users.json()).total).toBeGreaterThanOrEqual(2);

  const journey = await request.get(`${API}/admin/users/${learner.user.id}`, {
    headers: adminHeaders,
  });
  expect(journey.ok()).toBeTruthy();
  expect((await journey.json()).user.email).toContain(`learner-${stamp}@example.com`);

  const activity = await request.get(`${API}/admin/activity?user_id=${learner.user.id}&limit=5`, {
    headers: adminHeaders,
  });
  expect(activity.ok()).toBeTruthy();
  expect((await activity.json()).total).toBeGreaterThanOrEqual(1);

  const health = await request.get(`${API}/admin/health`, { headers: adminHeaders });
  expect(health.ok()).toBeTruthy();
  const healthBody = await health.text();
  for (const secret of ["gsk_", "AIza", "postgresql://", "rediss://"]) {
    expect(healthBody).not.toContain(secret);
  }

  // Learner activity generates a background job visible to admins.
  const space = await request.post(`${API}/spaces`, {
    headers: learnerHeaders,
    data: { name: `Admin ${stamp}` },
  });
  const spaceId = ((await space.json()) as { id: string }).id;
  const project = await request.post(`${API}/projects`, {
    headers: learnerHeaders,
    data: { space_id: spaceId, name: `Observed ${stamp}` },
  });
  const projectId = ((await project.json()) as { id: string }).id;
  const upload = await request.post(`${API}/projects/${projectId}/materials`, {
    headers: learnerHeaders,
    multipart: {
      file: {
        name: "notes.pdf",
        mimeType: "application/pdf",
        buffer: readFileSync(E2E_FIXTURE_PDF),
      },
    },
  });
  expect(upload.ok()).toBeTruthy();
  const jobs = await request.get(`${API}/admin/jobs?limit=5`, { headers: adminHeaders });
  expect(jobs.ok()).toBeTruthy();
  expect((await jobs.json()).total).toBeGreaterThanOrEqual(1);

  // AI evaluation suite runs deterministically and persists 16/16.
  const run = await request.post(`${API}/admin/evaluations/run`, { headers: adminHeaders });
  expect(run.ok()).toBeTruthy();
  const runBody = await run.json();
  expect(runBody.total_cases).toBe(16);
  expect(runBody.failed).toBe(0);
  const summary = await request.get(`${API}/admin/evaluations/summary`, {
    headers: adminHeaders,
  });
  expect(summary.ok()).toBeTruthy();
  expect((await summary.json()).passed).toBe(16);

  // Admin UI: dashboard renders real platform numbers.
  await page.goto("/login");
  await page.getByLabel("Email").fill("e2e-admin@example.com");
  await page.getByLabel("Password").fill("E2eSecure123");
  await page.getByRole("button", { name: /sign in/i }).click();
  await page.waitForURL("/");
  await expect(page.getByRole("link", { name: "Admin", exact: true })).toBeVisible();
  await page.goto("/admin");
  await expect(page.getByText("Admin dashboard")).toBeVisible();
  await expect(page.getByText("AI calls")).toBeVisible();
});
