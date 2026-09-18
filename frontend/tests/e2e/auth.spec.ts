import { expect, test } from "@playwright/test";

/**
 * Full auth journey against the real API (backend boots on SQLite in CI/local
 * e2e; production uses Neon — same models, same routes).
 *
 * Register -> app -> reload persists -> logout -> login page -> login -> app.
 * API-level cross-tenant IDOR is covered in backend/tests/test_auth.py.
 */
test("register, persist across reload, logout, login", async ({ page }) => {
  const email = `e2e-${Date.now()}@example.com`;
  const password = "E2eSecure123";
  const userMenu = page.getByRole("button", { name: "Account: E2E User" });

  // Unauthenticated root redirects to login.
  await page.goto("/");
  await expect(page.getByRole("heading", { name: /welcome back/i })).toBeVisible();

  // Register through the real endpoint and wait for the app shell.
  await page.goto("/register");
  await page.getByLabel("Display name").fill("E2E User");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel(/^Password$/).fill(password);
  await page.getByLabel("Confirm password").fill(password);
  await page.getByRole("button", { name: /create account/i }).click();
  await page.waitForURL("/");
  await expect(userMenu).toBeVisible();

  // Reload: session must survive via the persisted token + /me.
  await page.reload();
  await expect(userMenu).toBeVisible();

  // Logout returns to the login page; protected routes stay gated.
  // ( generous timeouts: the live-Neon round-trip follows logout here )
  await userMenu.click();
  await page.getByRole("menuitem", { name: /sign out/i }).click();
  await expect(page.getByRole("heading", { name: /welcome back/i })).toBeVisible({
    timeout: 30_000,
  });
  await page.goto("/projects");
  await expect(page.getByRole("heading", { name: /welcome back/i })).toBeVisible({
    timeout: 30_000,
  });

  // Login restores the session, honoring the preserved destination.
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(password);
  await page.getByRole("button", { name: /sign in/i }).click();
  await page.waitForURL("/projects");
  await expect(userMenu).toBeVisible();
});

test("invalid credentials show a server error", async ({ page }) => {
  await page.goto("/login");
  await page.getByLabel("Email").fill("nobody@example.com");
  await page.getByLabel("Password").fill("WrongPassword123");
  await page.getByRole("button", { name: /sign in/i }).click();
  await expect(page.getByRole("alert")).toContainText(/invalid email or password/i);
});
