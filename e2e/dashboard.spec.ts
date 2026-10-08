import { test, expect } from "@playwright/test";

// Dashboard customization: hide a widget, confirm it's gone, then bring it
// back — verified through the real Customize modal (checkbox + Save),
// not just the underlying setWidgetOrder DB logic (already covered by
// dashboard.integration.test.ts). Runs pre-authenticated via storageState
// — see auth.setup.ts.
test("customize the dashboard: hide a widget, then show it again", async ({ page }) => {
  await test.step("land on the dashboard", async () => {
    await page.goto("/dashboard");
    await expect(page.getByText("My open tickets")).toBeVisible();
  });

  await test.step("hiding a widget in Customize removes it from the dashboard", async () => {
    await page.getByRole("button", { name: "Customize" }).click();
    await page.getByRole("checkbox", { name: "Show My open tickets" }).uncheck();
    await page.getByRole("button", { name: "Save" }).click();

    await expect(page.getByText("Dashboard updated.")).toBeVisible();
    await expect(page.getByText("My open tickets")).toHaveCount(0);
  });

  await test.step("showing it again brings it back", async () => {
    await page.getByRole("button", { name: "Customize" }).click();
    await page.getByRole("checkbox", { name: "Show My open tickets" }).check();
    await page.getByRole("button", { name: "Save" }).click();

    await expect(page.getByText("Dashboard updated.")).toBeVisible();
    await expect(page.getByText("My open tickets")).toBeVisible();
  });
});
