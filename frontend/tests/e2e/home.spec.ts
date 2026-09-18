import { expect, test } from "@playwright/test";

test("anonymous root redirects to login", async ({ page }) => {
  await page.goto("/");
  await expect(page).toHaveURL(/\/login\?next=%2F/);
  await expect(page.getByRole("heading", { name: /welcome back/i })).toBeVisible();
});

test("authenticated home answers where/app/next, analytics aggregates", async ({
  page,
  request,
}) => {
  test.setTimeout(120_000);
  const stamp = Date.now();
  const email = `home-${stamp}@example.com`;
  const reg = await request.post("http://127.0.0.1:8000/api/v1/auth/register", {
    data: { email, password: "E2eSecure123", display_name: "E2E Home" },
  });
  expect(reg.ok()).toBeTruthy();
  const token = ((await reg.json()) as { access_token: string }).access_token;
  const headers = { Authorization: `Bearer ${token}` };

  // Cold start: honest empty states, no fabricated progress.
  let home = await request.get("http://127.0.0.1:8000/api/v1/home", { headers });
  expect(home.ok()).toBeTruthy();
  expect((await home.json()).continue_learning).toBeNull();

  const space = await request.post("http://127.0.0.1:8000/api/v1/spaces", {
    headers,
    data: { name: `Home ${stamp}` },
  });
  const spaceId = ((await space.json()) as { id: string }).id;
  const project = await request.post("http://127.0.0.1:8000/api/v1/projects", {
    headers,
    data: { space_id: spaceId, name: `Continue ${stamp}` },
  });
  const projectId = ((await project.json()) as { id: string }).id;

  home = await request.get("http://127.0.0.1:8000/api/v1/home", { headers });
  const homeBody = await home.json();
  expect(homeBody.continue_learning.project_id).toBe(projectId);
  expect(homeBody.continue_learning.next_action.kind).toBe("upload_material");
  expect(homeBody.recommended_action.kind).toBe("upload_material");

  const summary = await request.get("http://127.0.0.1:8000/api/v1/analytics/summary", {
    headers,
  });
  expect(summary.ok()).toBeTruthy();
  expect((await summary.json()).projects).toBe(1);

  // UI: login then home shows continue-learning + analytics page aggregates.
  await page.goto("/login");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill("E2eSecure123");
  await page.getByRole("button", { name: /sign in/i }).click();
  await page.waitForURL("/");
  await expect(page.getByText("Continue learning")).toBeVisible();
  await expect(page.getByRole("link", { name: `Continue ${stamp}` }).first()).toBeVisible();
  await expect(page.getByText("What should I do next?")).toBeVisible();
  await page.goto("/analytics");
  await expect(page.getByRole("heading", { name: "Global analytics" })).toBeVisible();
  await expect(page.getByText("Concepts requiring attention")).toBeVisible({
    timeout: 30_000,
  });
});
