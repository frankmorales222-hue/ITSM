import { test, expect } from "@playwright/test";
import { E2E_USER_EMAIL, E2E_USER_PASSWORD } from "./global-setup";

// The bulk status control on /technician asks for confirmation client-side
// (ConfirmBulkStatusButton) before submitting, since it's a Server Action
// with no per-ticket undo. Verified against a real confirm()/alert()
// dialog via Playwright's dialog handling, not just the underlying
// bulkUpdateStatus DB logic (already covered by tickets.integration.test.ts).
//
// One test with steps, reusing a single login, rather than three separate
// tests — this file and golden-path.spec.ts share a login rate limit
// (5 attempts/60s per IP), and three fresh logins here was enough to trip
// it when the whole suite ran together.
test("bulk status confirmation: accept, dismiss, and no-selection", async ({ page }) => {
  await test.step("log in and create a ticket", async () => {
    await page.goto("/login");
    await page.getByLabel("Email").fill(E2E_USER_EMAIL);
    await page.getByLabel("Password").fill(E2E_USER_PASSWORD);
    await page.getByRole("button", { name: "Log in" }).click();
    await expect(page).toHaveURL(/\/tickets$/);

    await page.getByRole("link", { name: "Report a problem" }).click();
    await page.getByLabel("Subject").fill("Bulk confirm dialog test");
    await page.getByLabel("Description").fill("Used to exercise the bulk status confirm dialog.");
    await page.getByRole("button", { name: "Submit" }).click();
    await expect(page).toHaveURL(/\/tickets$/);

    await page.getByRole("link", { name: "Technician Queue" }).click();
    await expect(page).toHaveURL(/\/technician(\?|$)/);
  });

  const row = page.locator("tr", { hasText: "Bulk confirm dialog test" });

  await test.step("dismissing the confirmation leaves the status unchanged", async () => {
    await row.locator('input[name="ticketIds"]').check();
    await page.locator('select[name="bulkStatus"]').selectOption("resolved");

    page.once("dialog", (dialog) => dialog.dismiss());
    await page.getByRole("button", { name: "Apply to selected" }).click();

    // No navigation happened — dismissing prevented the form submit.
    await expect(page).toHaveURL(/\/technician(\?|$)/);
    await expect(row.locator("span.badge")).toHaveText("assigned");
  });

  await test.step("accepting the confirmation applies the bulk status change", async () => {
    await row.locator('input[name="ticketIds"]').check();
    await page.locator('select[name="bulkStatus"]').selectOption("on_hold");

    page.once("dialog", (dialog) => {
      expect(dialog.message()).toContain("on_hold");
      expect(dialog.message()).toContain("1 selected ticket");
      dialog.accept();
    });
    await page.getByRole("button", { name: "Apply to selected" }).click();

    await expect(page).toHaveURL(/\/technician(\?|$)/);
    await expect(row.locator("span.badge")).toHaveText("on_hold");
  });

  await test.step("submitting with nothing selected shows an alert, not a confirm dialog", async () => {
    let alertMessage = "";
    page.once("dialog", (dialog) => {
      alertMessage = dialog.message();
      dialog.accept();
    });
    await page.locator('select[name="bulkStatus"]').selectOption("resolved");
    await page.getByRole("button", { name: "Apply to selected" }).click();

    expect(alertMessage).toContain("Select at least one ticket");
    await expect(page).toHaveURL(/\/technician/);
    // Still on_hold from the previous step — the alert path never submitted.
    await expect(row.locator("span.badge")).toHaveText("on_hold");
  });
});
