import { expect, test } from "@playwright/test";

// Smoke test: the app shell boots and the workspace overview loads against a live backend
// without falling into the error state. Cheap guard that the frontend/backend wiring and the
// initial GET /api/assets contract are intact.

test("workspace overview loads without an error state", async ({ page }) => {
  const overviewLoaded = page.waitForResponse((r) => r.url().endsWith("/api/assets") && r.ok());
  await page.goto("/");
  await overviewLoaded;

  await expect(page.getByRole("heading", { name: "Your buckets" })).toBeVisible();
  await expect(page.getByText(/Could not load workspace/i)).toHaveCount(0);
});
