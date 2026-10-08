import { test, expect } from "@playwright/test";

// Saved views round-trip: filter, save, confirm the chip reapplies the
// same filter after navigating away, then delete it. Runs pre-authenticated
// via storageState — see auth.setup.ts.
test("save a filtered view on /tickets, reapply it, then delete it", async ({ page }) => {
  await test.step("create a ticket to filter for", async () => {
    await page.goto("/tickets/new");
    await page.getByLabel("Subject").fill("Saved view target ticket");
    await page.getByLabel("Description").fill("Used to verify saved views.");
    await page.getByRole("button", { name: "Submit" }).click();
    await expect(page).toHaveURL(/\/tickets$/);
  });

  await test.step("filter, save the view, and see it appear as a chip", async () => {
    await page.locator("#q").fill("Saved view target");
    await page.getByRole("button", { name: "Apply" }).click();
    await expect(page).toHaveURL(/q=Saved/);
    await expect(page.locator("tr", { hasText: "Saved view target ticket" })).toBeVisible();

    await page.locator('input[name="name"]').fill("My saved view");
    await page.getByRole("button", { name: "Save view" }).click();
    await expect(page.getByText("View saved.")).toBeVisible();
    await expect(page.getByRole("link", { name: "My saved view" })).toBeVisible();
  });

  await test.step("navigating away and clicking the chip reapplies the filter", async () => {
    await page.goto("/tickets");
    await expect(page.locator("#q")).toHaveValue("");

    await page.getByRole("link", { name: "My saved view" }).click();
    await expect(page).toHaveURL(/q=Saved/);
    await expect(page.locator("#q")).toHaveValue("Saved view target");
    await expect(page.locator("tr", { hasText: "Saved view target ticket" })).toBeVisible();
  });

  await test.step("deleting the view removes the chip", async () => {
    await page.getByRole("button", { name: "Delete saved view My saved view" }).click();
    await expect(page.getByText("View deleted.")).toBeVisible();
    await expect(page.getByRole("link", { name: "My saved view" })).toHaveCount(0);
  });
});
