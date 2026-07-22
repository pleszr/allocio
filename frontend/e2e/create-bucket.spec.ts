import { expect, test } from "@playwright/test";

// The critical end-to-end journey: create a vehicle bucket through the wizard and land on its
// dashboard without an error. This is the flow that surfaced the "not found" regression, so it
// asserts both the create call's 201 and that the app navigates into the new bucket cleanly.

test("create a vehicle bucket through the wizard and land on its dashboard", async ({ page }) => {
  await page.goto("/");

  // Home loads.
  await expect(page.getByRole("heading", { name: "Your buckets" })).toBeVisible();

  // Open the New Bucket wizard.
  await page.getByRole("button", { name: "New bucket", exact: true }).click();
  await expect(page.getByRole("heading", { name: "New bucket" })).toBeVisible();

  // Step 1 — pick the Vehicle type; selecting it triggers the template catalog fetch.
  const catalogFetched = page.waitForResponse(
    (r) => r.url().includes("/api/asset-templates/vehicle/catalog") && r.ok(),
  );
  await page.getByRole("button", { name: /Vehicle/ }).click();
  await catalogFetched;
  await page.getByRole("button", { name: /Continue/ }).click();

  // Step 2 — name the bucket (required to advance).
  await page.getByTestId("bucket-name-input").fill("E2E Test Car");
  await page.getByRole("button", { name: /Continue/ }).click();

  // Step 3 — cost picker (defaults to every catalog row selected); continue to review.
  await page.getByRole("button", { name: /Continue/ }).click();

  // Step 4 — submit and assert the create request succeeds.
  const created = page.waitForResponse(
    (r) => r.url().endsWith("/api/assets") && r.request().method() === "POST",
  );
  await page.getByRole("button", { name: /Create bucket/ }).click();
  const createResponse = await created;
  expect(createResponse.status()).toBe(201);

  // The app navigates into the new bucket's dashboard — the name shows as the page heading,
  // with no error banner or "not found" state (the reported regression).
  await expect(page.getByRole("heading", { name: "E2E Test Car" })).toBeVisible();
  await expect(page.locator(".error-banner")).toHaveCount(0);
  await expect(page.getByText(/not found/i)).toHaveCount(0);
});
