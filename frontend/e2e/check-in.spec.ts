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
  await page.getByRole("button", { name: /Continue/ }).click(); // details -> costs
  // Costs step — cost picker defaults to every catalog row selected, so the vehicle gets tire and
  // non-tire maintenance items without any extra clicks.
  await page.getByRole("button", { name: /Continue/ }).click(); // costs -> safety
  await page.getByRole("button", { name: /Continue/ }).click(); // safety -> ask-checkin
  await page.getByRole("button", { name: "No", exact: true }).click(); // ask-checkin -> review

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
  await expect(page.getByRole("button", { name: /Update preview/ })).toHaveCount(0);
});

test("tire-type picker is seeded and expenses are sent with the preview request", async ({ page }) => {
  await createVehicleBucket(page, "E2E Tire Car");
  const initialPreviewed = page.waitForResponse(
    (r) => r.url().endsWith("/check-ins/preview") && r.request().method() === "POST",
  );
  await page.getByRole("tab", { name: "Check-in" }).click();
  await initialPreviewed;
  await expect(page.getByRole("button", { name: /Update preview/ })).toHaveCount(0);

  // The vehicle template seeds tire-specific maintenance items, so the picker renders.
  const tirePicker = page.getByLabel("Active tire type");
  await expect(tirePicker).toBeVisible();
  // No prior check-in exists yet, so the server-resolved default is null (blank selection).
  await expect(tirePicker).toHaveValue("");

  const previewed = page.waitForResponse((response) => {
    if (!response.url().endsWith("/check-ins/preview")) return false;
    const body = response.request().postDataJSON();
    return body.active_tire_type === "winter" && body.expenses?.[0]?.comment === "Car wash";
  });
  await tirePicker.selectOption("winter");

  // Advance from the period step to the expenses step (wizard: period -> expenses -> review).
  await page.getByRole("button", { name: "Continue" }).click();

  // Add a manual "Other" expense.
  await page.getByRole("button", { name: /Add expense/ }).click();
  await page.getByLabel("Amount").fill("5000");
  await page.getByLabel("Comment").fill("Car wash");

  const previewResponse = await previewed;
  const previewBody = previewResponse.request().postDataJSON();
  expect(previewBody.active_tire_type).toBe("winter");
  expect(previewBody.expenses).toEqual([
    {
      kind: "other",
      amount: 5000,
      paid_out_of_pocket_override: null,
      comment: "Car wash",
      source_type: null,
      source_id: null,
      excluded_from_average: false,
    },
  ]);

  // Switching the same row to a maintenance-linked expense automatically refreshes the preview.
  const secondPreview = page.waitForResponse((response) => {
    if (!response.url().endsWith("/check-ins/preview")) return false;
    return response.request().postDataJSON().expenses?.[0]?.source_type === "maintenance_item";
  });
  await page.getByLabel("Type", { exact: true }).selectOption({ label: "All-season tires" });
  const secondBody = (await secondPreview).request().postDataJSON();
  expect(secondBody.expenses).toHaveLength(1);
  expect(secondBody.expenses[0].source_type).toBe("maintenance_item");
  expect(secondBody.expenses[0].source_id).toBeTruthy();

  // Removing the row automatically drops it from the next preview request.
  const thirdPreview = page.waitForResponse((response) => {
    if (!response.url().endsWith("/check-ins/preview")) return false;
    return response.request().postDataJSON().expenses?.length === 0;
  });
  await page.getByRole("button", { name: "Remove" }).click();
  const thirdBody = (await thirdPreview).request().postDataJSON();
  expect(thirdBody.expenses).toEqual([]);
});

test("out-of-pocket amount requires bilingual confirmation and stays out of the bucket", async ({ page }) => {
  await createVehicleBucket(page, "E2E Pocket Car");
  const initialPreviewed = page.waitForResponse(
    (r) => r.url().endsWith("/check-ins/preview") && r.request().method() === "POST",
  );
  await page.getByRole("tab", { name: "Check-in" }).click();
  await initialPreviewed;

  let postCount = 0;
  page.on("request", (request) => {
    if (
      request.method() === "POST" &&
      request.url().includes("/check-ins") &&
      !request.url().includes("/preview")
    ) {
      postCount += 1;
    }
  });

  // Wizard: period -> expenses.
  await page.getByRole("button", { name: "Continue" }).click();

  await page.getByRole("button", { name: /Add expense/ }).click();
  const previewed = page.waitForResponse((response) => {
    if (!response.url().endsWith("/check-ins/preview") || !response.ok()) return false;
    return response.request().postDataJSON().expenses?.[0]?.comment === "Unexpected repair";
  });
  await page.getByLabel("Amount").fill("5000");
  await page.getByLabel("Comment").fill("Unexpected repair");

  // expenses -> review, where the confirm button and preview breakdown render.
  await page.getByRole("button", { name: "Continue" }).click();
  await expect(page.getByRole("button", { name: "Confirm and post" })).toBeDisabled();

  await previewed;
  await expect(page.getByRole("button", { name: "Confirm and post" })).toBeEnabled();
  await expect(page.getByText("5,000.00 Ft", { exact: true }).first()).toBeVisible();

  await page.getByRole("button", { name: "Confirm and post" }).click();
  const englishDialog = page.getByRole("dialog");
  await expect(englishDialog.getByRole("heading", { name: "Paid out of pocket" })).toBeVisible();
  await expect(
    englishDialog.getByText(
      "This expense is larger than the money available in this bucket. 5,000.00 Ft will be recorded as paid out of pocket, and the bucket balance will stay at zero.",
    ),
  ).toBeVisible();
  await englishDialog.getByRole("button", { name: "Back" }).click();
  expect(postCount).toBe(0);

  await page.locator(".user-menu-trigger").click();
  const savedHu = page.waitForResponse(
    (r) => r.url().includes("/api/users/me/settings") && r.request().method() === "PUT" && r.ok(),
  );
  await page.getByLabel("Language").selectOption("hu");
  await savedHu;

  await page.getByRole("button", { name: "Megerősítés és rögzítés" }).click();
  const hungarianDialog = page.getByRole("dialog");
  await expect(hungarianDialog.getByRole("heading", { name: "Kifizettük zsebből" })).toBeVisible();
  await expect(
    hungarianDialog.getByText(
      "Ez a kiadás nagyobb, mint a zsebben elérhető összeg. 5,000.00 Ft zsebből fizetett összegként lesz rögzítve, a zseb egyenlege pedig nulla marad.",
    ),
  ).toBeVisible();

  const posted = page.waitForResponse(
    (r) => r.url().includes("/check-ins") && !r.url().includes("/preview") && r.request().method() === "POST" && r.ok(),
  );
  await hungarianDialog.getByRole("button", { name: "Megerősítés és rögzítés" }).click();
  await posted;
  expect(postCount).toBe(1);
  await expect(hungarianDialog).toHaveCount(0);

  await page.locator(".user-menu-trigger").click();
  const savedEn = page.waitForResponse(
    (r) => r.url().includes("/api/users/me/settings") && r.request().method() === "PUT" && r.ok(),
  );
  await page.getByLabel("Nyelv").selectOption("en");
  await savedEn;

  await page.getByRole("tab", { name: "History" }).click();
  await expect(page.getByRole("columnheader", { name: "Covered by bucket" })).toBeVisible();
  await expect(page.getByRole("columnheader", { name: "Paid out of pocket" })).toBeVisible();
  const historyRow = page.getByRole("row").filter({ has: page.getByRole("cell", { name: "120,000" }) });
  await expect(historyRow.locator("td").nth(5)).toContainText("−5,000.00 Ft");
  await expect(historyRow.locator("td").nth(6)).toContainText("0.00 Ft");
  await expect(historyRow.locator("td").nth(7)).toContainText("5,000.00 Ft");
  await expect(historyRow.locator("td").nth(9)).toContainText("0.00 Ft");
});

test("paid-out-of-pocket override forces the full expense out of the bucket in the preview", async ({ page }) => {
  await createVehicleBucket(page, "E2E Override Car");
  const initialPreviewed = page.waitForResponse(
    (r) => r.url().endsWith("/check-ins/preview") && r.request().method() === "POST",
  );
  await page.getByRole("tab", { name: "Check-in" }).click();
  await initialPreviewed;

  // Advance the odometer (without advancing the calendar day) so the usage-based cost accrues a
  // positive allocation on this same-day baseline check-in, giving the bucket money available to
  // cover the upcoming expense naturally -- letting the override prove it forces the full amount
  // out of pocket anyway, rather than merely reflecting an already-zero bucket.
  const usagePreviewed = page.waitForResponse((response) => {
    if (!response.url().endsWith("/check-ins/preview") || !response.ok()) return false;
    return response.request().postDataJSON().usage_end === 120600;
  });
  // Current usage lives on the wizard's first (period) step.
  await page.getByLabel("Current usage").fill("120600");
  await usagePreviewed;

  // period -> expenses.
  await page.getByRole("button", { name: "Continue" }).click();

  await page.getByRole("button", { name: /Add expense/ }).click();
  const previewed = page.waitForResponse((response) => {
    if (!response.url().endsWith("/check-ins/preview") || !response.ok()) return false;
    return response.request().postDataJSON().expenses?.[0]?.paid_out_of_pocket_override === 3000;
  });
  await page.getByLabel("Amount").fill("3000");
  await page.getByLabel("Comment").fill("Car wash");
  await page.getByLabel("Paid out of pocket").fill("3000");

  const previewResponse = await previewed;
  const previewBody = previewResponse.request().postDataJSON();
  expect(previewBody.expenses[0].paid_out_of_pocket_override).toBe(3000);
  const previewResult = await previewResponse.json();
  // Decimal precision on the wire tracks the operands' own precision (unquantized whole-number
  // inputs serialize without trailing zeros), so compare numerically rather than by exact string.
  expect(Number(previewResult.expense_lines[0].paid_out_of_pocket)).toBe(3000);
  expect(Number(previewResult.expense_lines[0].bucket_amount)).toBe(0);

  // expenses -> review, where the per-line breakdown renders.
  await page.getByRole("button", { name: "Continue" }).click();
  const pocketLine = page.locator(".checkin-line").filter({ hasText: "Paid out of pocket" });
  await expect(pocketLine.locator(".checkin-line-amt")).toHaveText("3,000.00 Ft");
  const bucketLine = page.locator(".checkin-line").filter({ hasText: "Covered by bucket" });
  await expect(bucketLine.locator(".checkin-line-amt")).toHaveText("0.00 Ft");
});

test("a failed automatic preview can be retried without changing the form", async ({ page }) => {
  await createVehicleBucket(page, "E2E Preview Error Car");

  let shouldFail = true;
  await page.route(/\/api\/assets\/[^/]+\/check-ins\/preview$/, async (route) => {
    if (shouldFail) {
      shouldFail = false;
      await route.fulfill({
        status: 503,
        contentType: "application/json",
        body: JSON.stringify({ detail: "Temporary preview failure" }),
      });
      return;
    }
    await route.continue();
  });

  const failedPreview = page.waitForResponse(
    (r) => r.url().endsWith("/check-ins/preview") && r.status() === 503,
  );
  await page.getByRole("tab", { name: "Check-in" }).click();
  await failedPreview;

  // The preview error surfaces on the review step; advance there (period -> expenses -> review).
  await page.getByRole("button", { name: "Continue" }).click();
  await page.getByRole("button", { name: "Continue" }).click();

  await expect(page.getByText("Temporary preview failure")).toBeVisible();
  const confirm = page.getByRole("button", { name: "Confirm and post" });
  await expect(confirm).toBeDisabled();

  const retriedPreview = page.waitForResponse(
    (r) => r.url().endsWith("/check-ins/preview") && r.ok(),
  );
  await page.getByRole("button", { name: "Retry calculation" }).click();
  await retriedPreview;

  await expect(page.getByText("Temporary preview failure")).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Retry calculation" })).toHaveCount(0);
  await expect(confirm).toBeEnabled();
});
