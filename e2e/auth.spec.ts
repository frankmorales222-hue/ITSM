import { test, expect } from "@playwright/test";

test("unauthenticated visitors are redirected to login", async ({ page }) => {
  await page.goto("/tickets");
  await expect(page).toHaveURL(/\/login/);
});

test("invalid credentials show an error and don't create a session", async ({ page }) => {
  await page.goto("/login");
  await page.getByLabel("Email").fill("nobody@example.com");
  await page.getByLabel("Password").fill("wrong-password");
  await page.getByRole("button", { name: "Log in" }).click();

  await expect(page).toHaveURL(/\/login/);
  await expect(page.getByText("Invalid email or password.")).toBeVisible();

  // Confirm no session actually got issued despite landing back on /login.
  await page.goto("/tickets");
  await expect(page).toHaveURL(/\/login/);
});
