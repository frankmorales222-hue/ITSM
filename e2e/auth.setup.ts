import { test as setup, expect } from "@playwright/test";
import { E2E_USER_EMAIL, E2E_USER_PASSWORD } from "./global-setup";

// Logs in exactly once for the whole suite and saves the session cookie to
// disk; every authenticated test project reuses it via `storageState`
// instead of submitting the login form itself. Not just a speed-up — the
// login rate limit (5 attempts/60s per IP, src/lib/rate-limit.ts) is
// shared across every spec file that logs in, and once the suite grew past
// ~5 files each doing their own fresh login, later files started getting
// rate-limited by earlier ones. auth.spec.ts deliberately isn't part of
// this — it's testing the login flow itself, so it needs to start from a
// clean, unauthenticated state.
const authFile = "e2e/.auth/user.json";

setup("authenticate", async ({ page }) => {
  await page.goto("/login");
  await page.getByLabel("Email").fill(E2E_USER_EMAIL);
  await page.getByLabel("Password").fill(E2E_USER_PASSWORD);
  await page.getByRole("button", { name: "Log in" }).click();
  await expect(page).toHaveURL(/\/dashboard$/);
  await page.context().storageState({ path: authFile });
});
