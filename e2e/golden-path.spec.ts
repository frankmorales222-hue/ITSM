import path from "path";
import { test, expect } from "@playwright/test";
import { E2E_USER_EMAIL, E2E_USER_PASSWORD } from "./global-setup";

// One end-to-end walk through the actual product loop, driven through a
// real browser against a running server — this is what the route-handler
// and lib integration tests can't cover: Server Component rendering,
// redirect() behavior, and real HTML form submission (including an
// actual file upload, which the in-app browser tool used earlier in this
// project's history couldn't drive — Playwright's setInputFiles can).
test("login, file a ticket, reply with an attachment, resolve it, see it in the technician queue, log out", async ({
  page,
}) => {
  await test.step("log in", async () => {
    await page.goto("/login");
    await page.getByLabel("Email").fill(E2E_USER_EMAIL);
    await page.getByLabel("Password").fill(E2E_USER_PASSWORD);
    await page.getByRole("button", { name: "Log in" }).click();
    await expect(page).toHaveURL(/\/tickets$/);
    await expect(page.getByRole("heading", { name: "My Requests" })).toBeVisible();
    await expect(page.getByText("No requests yet.")).toBeVisible();
  });

  await test.step("report a problem", async () => {
    await page.getByRole("link", { name: "Report a problem" }).click();
    await expect(page).toHaveURL(/\/tickets\/new$/);

    await page.getByLabel("Subject").fill("E2E: laptop won't boot");
    await page
      .getByLabel("Description")
      .fill("Pressed the power button several times, nothing happens.");
    await page.getByLabel("Impact").selectOption("high");
    await page.getByLabel("Urgency").selectOption("high");
    await page.getByRole("button", { name: "Submit" }).click();

    await expect(page).toHaveURL(/\/tickets$/);
    const row = page.locator("tr", { hasText: "E2E: laptop won't boot" });
    await expect(row).toBeVisible();
    // impact=high + urgency=high -> critical, and it's the only team
    // member so round-robin assigns it straight to "assigned". Scoped to
    // the row's badge, not just text on the page — both words also
    // appear as options in the status filter dropdown.
    await expect(row.locator("span.badge")).toHaveText("assigned");
    await expect(row.getByRole("cell").nth(3)).toHaveText("critical");
  });

  await test.step("open the ticket, attach a file, reply, and resolve it", async () => {
    await page.getByRole("link", { name: /^INC-\d+$/ }).click();
    await expect(page.getByRole("heading", { name: /E2E: laptop won't boot/ })).toBeVisible();
    await expect(page.getByText("No attachments.")).toBeVisible();

    await page.locator('textarea[name="body"]').fill("Reseated the battery, it powered on.");
    await page
      .getByLabel("Attach a file (optional)")
      .setInputFiles(path.join(__dirname, "fixtures", "test-attachment.txt"));
    await page.getByLabel("Change status").selectOption("resolved");
    await page.getByRole("button", { name: "Submit" }).click();

    await expect(page.getByText("Reseated the battery, it powered on.")).toBeVisible();
    // Scoped to the badge, not just text on the page — "resolved" is
    // also an <option> in the status-change <select> right below it.
    await expect(page.locator("span.badge").first()).toHaveText("resolved");
    await expect(page.getByRole("link", { name: "test-attachment.txt" })).toBeVisible();
  });

  await test.step("see it resolved in the technician queue", async () => {
    await page.getByRole("link", { name: "← My Requests" }).click();
    await page.getByRole("link", { name: "Technician queue" }).click();
    await expect(page).toHaveURL(/\/technician$/);
    await expect(page.getByText("E2E: laptop won't boot")).toBeVisible();
    await expect(page.getByText("resolved: 1")).toBeVisible();
  });

  await test.step("log out and lose access", async () => {
    // Log out only lives on the My Requests nav, not the technician queue.
    await page.goto("/tickets");
    await page.getByRole("button", { name: "Log out" }).click();
    await expect(page).toHaveURL(/\/login/);

    await page.goto("/tickets");
    await expect(page).toHaveURL(/\/login/);
  });
});
