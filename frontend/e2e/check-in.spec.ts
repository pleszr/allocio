import { expect, test } from "@playwright/test";

// Covers the check-in screen's expense-attribution and tire-type wiring added for backdated
// check-ins + maintenance service-baseline reset. A same-day-created asset can never satisfy the
// backend's period rule (period_end must be later than the derived period_start — the asset's own
// creation date — and no later than today, which is impossible on day zero), so this spec exercises
// the preview request's payload shape rather than a successful post. The full backdated-post and
// maintenance-reset behavior is covered by the backend suite (`backend/tests/test_check_in.py`,
// `backend/tests/test_maintenance_status.py`), which can backdate an asset's `created_at` directly.

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
  // Step 3 — cost picker defaults to every catalog row selected, so the vehicle gets tire and
  // non-tire maintenance items without any extra clicks.
  await page.getByRole("button", { name: /Continue/ }).click();

  const created = page.waitForResponse((r) => r.url().endsWith("/api/assets") && r.request().method() === "POST");
  await page.getByRole("button", { name: /Create bucket/ }).click();
  await created;
  await expect(page.getByRole("heading", { name })).toBeVisible();
}

test("check-in date field cannot be set to a future date", async ({ page }) => {
  await createVehicleBucket(page, "E2E Check-In Car");
  await page.getByRole("tab", { name: "Check-in" }).click();

  const today = new Date().toISOString().slice(0, 10);
  await expect(page.getByLabel("Period end")).toHaveAttribute("max", today);
});

test("tire-type picker is seeded and expenses are sent with the preview request", async ({ page }) => {
  await createVehicleBucket(page, "E2E Tire Car");
  await page.getByRole("tab", { name: "Check-in" }).click();

  // The vehicle template seeds tire-specific maintenance items, so the picker renders.
  const tirePicker = page.getByLabel("Active tire type");
  await expect(tirePicker).toBeVisible();
  // No prior check-in exists yet, so the server-resolved default is null (blank selection).
  await expect(tirePicker).toHaveValue("");
  await tirePicker.selectOption("winter");

  // Add a manual "Other" expense.
  await page.getByRole("button", { name: /Add expense/ }).click();
  await page.getByLabel("Amount").fill("5000");
  await page.getByLabel("Comment").fill("Car wash");

  const previewed = page.waitForResponse((r) => r.url().includes("/check-ins/preview"));
  await page.getByRole("button", { name: /Update preview/ }).click();
  const previewResponse = await previewed;
  const previewBody = previewResponse.request().postDataJSON();
  expect(previewBody.active_tire_type).toBe("winter");
  expect(previewBody.expenses).toEqual([
    { kind: "other", amount: 5000, comment: "Car wash", source_type: null, source_id: null },
  ]);

  // Switch the same row to a maintenance-linked expense and re-preview.
  await page.getByLabel("Type", { exact: true }).selectOption("modeled");
  await page.getByLabel("Maintenance item").selectOption({ label: "All-season tires" });

  const secondPreview = page.waitForResponse((r) => r.url().includes("/check-ins/preview"));
  await page.getByRole("button", { name: /Update preview/ }).click();
  const secondBody = (await secondPreview).request().postDataJSON();
  expect(secondBody.expenses).toHaveLength(1);
  expect(secondBody.expenses[0].source_type).toBe("maintenance_item");
  expect(secondBody.expenses[0].source_id).toBeTruthy();

  // Removing the row drops it from the next preview request.
  await page.getByRole("button", { name: "Remove" }).click();
  const thirdPreview = page.waitForResponse((r) => r.url().includes("/check-ins/preview"));
  await page.getByRole("button", { name: /Update preview/ }).click();
  const thirdBody = (await thirdPreview).request().postDataJSON();
  expect(thirdBody.expenses).toEqual([]);
});
