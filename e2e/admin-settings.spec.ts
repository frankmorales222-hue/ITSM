import { test, expect } from "@playwright/test";
import { E2E_USER_EMAIL, E2E_USER_PASSWORD } from "./global-setup";

test.beforeEach(async ({ page }) => {
  await page.goto("/login");
  await page.getByLabel("Email").fill(E2E_USER_EMAIL);
  await page.getByLabel("Password").fill(E2E_USER_PASSWORD);
  await page.getByRole("button", { name: "Log in" }).click();
  await expect(page).toHaveURL(/\/tickets$/);
});

test("saving Azure AD config shows configured status without echoing the secret", async ({
  page,
}) => {
  await page.goto("/admin");
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

  await updatedCard.getByRole("button", { name: "Clear" }).click();
  await expect(page).toHaveURL(/\/admin$/);
  const clearedCard = page.locator(".card", { hasText: "Single sign-on" });
  await expect(clearedCard.getByText("not configured")).toBeVisible();
});

test("saving IMAP config shows configured status without echoing the password", async ({
  page,
}) => {
  await page.goto("/admin");
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

  await updatedCard.getByRole("button", { name: "Clear" }).click();
  await expect(page).toHaveURL(/\/admin$/);
  const clearedCard = page.locator(".card", { hasText: "Email intake" });
  await expect(clearedCard.getByText("not configured")).toBeVisible();
});
