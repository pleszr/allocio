import { expect, test } from "@playwright/test";

async function createVehicleBucket(page: import("@playwright/test").Page, name: string): Promise<void> {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Your buckets" })).toBeVisible();
  await page.getByRole("button", { name: "New bucket", exact: true }).click();

  const catalogFetched = page.waitForResponse(
    (r) => r.url().includes("/api/asset-templates/vehicle/catalog") && r.ok(),
  );
  await page.getByRole("button", { name: /Vehicle/ }).click();
  await catalogFetched;

  await page.getByTestId("bucket-name-input").fill(name);
  await page.getByLabel("Current odometer").fill("120000");
  await page.getByRole("button", { name: /Continue/ }).click();
  // Step 3 — cost picker defaults to every catalog row selected.
  await page.getByRole("button", { name: /Continue/ }).click();

  const created = page.waitForResponse((r) => r.url().endsWith("/api/assets") && r.request().method() === "POST");
  await page.getByRole("button", { name: /Create bucket/ }).click();
  await created;
  await expect(page.getByRole("heading", { name })).toBeVisible();
}

test("History tab shows the empty state before any check-in is posted", async ({ page }) => {
  await createVehicleBucket(page, "E2E History Empty Car");
  await page.getByRole("tab", { name: "History" }).click();

  await expect(page.getByText("No history yet for this bucket.")).toBeVisible();
});

test("History tab lists a posted baseline check-in as a ledger row", async ({ page }) => {
  await createVehicleBucket(page, "E2E History Car");
  await page.getByRole("tab", { name: "Check-in" }).click();

  // A freshly created asset's first check-in may post same-day as a zero-length baseline period
  // (see docs/vehicle-rules.md, "First check-in"); the usage field is pre-seeded with the vehicle's
  // starting odometer, so posting it unedited records a baseline row with no usage delta.
  const posted = page.waitForResponse(
    (r) => r.url().includes("/check-ins") && !r.url().includes("/preview") && r.request().method() === "POST",
  );
  await page.getByRole("button", { name: /Confirm and post/ }).click();
  await posted;

  await page.getByRole("tab", { name: "History" }).click();
  await expect(page.getByRole("cell", { name: "120,000" })).toBeVisible();
});
