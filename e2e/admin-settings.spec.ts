import { test, expect } from "@playwright/test";
import { E2E_USER_EMAIL, E2E_USER_PASSWORD } from "./global-setup";

// One test with steps, reusing a single login, rather than separate tests
// per card — the login rate limit (5 attempts/60s per IP) is shared across
// every spec file that logs in, and this file previously logged in fresh
// per test, which added up across the suite.
test("admin settings: save/clear Azure AD and IMAP, with confirm-dialog handling on Clear", async ({
  page,
}) => {
  await test.step("log in", async () => {
    await page.goto("/login");
    await page.getByLabel("Email").fill(E2E_USER_EMAIL);
    await page.getByLabel("Password").fill(E2E_USER_PASSWORD);
    await page.getByRole("button", { name: "Log in" }).click();
    await expect(page).toHaveURL(/\/tickets$/);
    await page.goto("/admin");
  });

  await test.step("saving Azure AD config shows configured status without echoing the secret", async () => {
    await expect(page.getByText("Single sign-on (Azure AD)")).toBeVisible();

    const azureCard = page.locator(".card", { hasText: "Single sign-on" });
    await expect(azureCard.getByText("not configured")).toBeVisible();

    await azureCard.getByLabel("Tenant ID").fill("e2e-tenant");
    await azureCard.getByLabel("Client ID").fill("e2e-client");
    await azureCard.getByLabel("Client secret").fill("e2e-super-secret");
    await azureCard.getByRole("button", { name: "Save" }).click();

    await expect(page).toHaveURL(/\/admin$/);
    const updatedCard = page.locator(".card", { hasText: "Single sign-on" });
    await expect(updatedCard.getByText("configured", { exact: true })).toBeVisible();
    await expect(updatedCard.getByText("e2e-tenant")).toBeVisible();
    await expect(updatedCard.getByText("e2e-client")).toBeVisible();
    // The secret itself must never come back in the page.
    await expect(page.getByText("e2e-super-secret")).toHaveCount(0);
  });

  await test.step("dismissing the Clear confirmation leaves the config untouched", async () => {
    const updatedCard = page.locator(".card", { hasText: "Single sign-on" });
    page.once("dialog", (dialog) => dialog.dismiss());
    await updatedCard.getByRole("button", { name: "Clear" }).click();

    // Dismissed — still on /admin, config still there (no navigation happened).
    await expect(page).toHaveURL(/\/admin$/);
    await expect(updatedCard.getByText("configured", { exact: true })).toBeVisible();
  });

  await test.step("accepting the Clear confirmation actually clears it", async () => {
    const updatedCard = page.locator(".card", { hasText: "Single sign-on" });
    page.once("dialog", (dialog) => dialog.accept());
    await updatedCard.getByRole("button", { name: "Clear" }).click();

    await expect(page).toHaveURL(/\/admin$/);
    const clearedCard = page.locator(".card", { hasText: "Single sign-on" });
    await expect(clearedCard.getByText("not configured")).toBeVisible();
  });

  await test.step("saving IMAP config shows configured status without echoing the password", async () => {
    const imapCard = page.locator(".card", { hasText: "Email intake" });
    await expect(imapCard.getByText("not configured")).toBeVisible();

    await imapCard.getByLabel("IMAP host").fill("imap.e2e-example.com");
    await imapCard.getByLabel("Port").fill("993");
    await imapCard.getByLabel("Username").fill("support@e2e-example.com");
    await imapCard.getByLabel("Password").fill("e2e-mailbox-password");
    await imapCard.getByRole("button", { name: "Save" }).click();

    await expect(page).toHaveURL(/\/admin$/);
    const updatedCard = page.locator(".card", { hasText: "Email intake" });
    await expect(updatedCard.getByText("configured", { exact: true })).toBeVisible();
    await expect(updatedCard.getByText("imap.e2e-example.com")).toBeVisible();
    await expect(page.getByText("e2e-mailbox-password")).toHaveCount(0);

    page.once("dialog", (dialog) => dialog.accept());
    await updatedCard.getByRole("button", { name: "Clear" }).click();

    await expect(page).toHaveURL(/\/admin$/);
    const clearedCard = page.locator(".card", { hasText: "Email intake" });
    await expect(clearedCard.getByText("not configured")).toBeVisible();
  });
});
