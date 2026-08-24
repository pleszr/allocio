import { expect, test } from "@playwright/test";

// Covers the History-tab "edit a past check-in" flow added for issue #107.
//
// The plan this spec implements described a "post two check-ins, edit the first" golden path, but
// that is not reachable in this e2e suite: the backend rejects any check-in whose period_end is not
// strictly later than the previous one (`check_in_service._validate_period`), and this suite always
// runs against the real system clock with no backdating endpoint (see check-in.spec.ts's own note on
// the same constraint) -- so a single test run can only ever post one real, same-day baseline
// check-in. This spec instead covers the achievable version of the same golden path: post one
// check-in, edit it from History, and confirm the corrected numbers land. The "editing an older,
// non-most-recent check-in without breaking a later period" scenario is covered by the backend suite
// (`backend/tests/test_check_in_edit.py`), which seeds multi-period history directly against Postgres.

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
  // Costs step — cost picker defaults to every catalog row selected.
  await page.getByRole("button", { name: /Continue/ }).click(); // costs -> safety
  await page.getByRole("button", { name: /Continue/ }).click(); // safety -> ask-checkin
  await page.getByRole("button", { name: "No", exact: true }).click(); // ask-checkin -> review

  const created = page.waitForResponse((r) => r.url().endsWith("/api/assets") && r.request().method() === "POST");
  await page.getByRole("button", { name: /Create bucket/ }).click();
  await created;
  await expect(page.getByRole("heading", { name })).toBeVisible();
}

test("editing a posted check-in's expense from History updates the ledger with no 'edited' badge", async ({
  page,
}) => {
  await createVehicleBucket(page, "E2E Edit Car");
  const initialPreviewed = page.waitForResponse(
    (r) => r.url().endsWith("/check-ins/preview") && r.request().method() === "POST",
  );
  await page.getByRole("tab", { name: "Check-in" }).click();
  await initialPreviewed;

  // The check-in screen is a guided wizard: period -> expenses -> review.
  await page.getByRole("button", { name: "Continue" }).click(); // period -> expenses
  await page.getByRole("button", { name: /Add expense/ }).click();
  const previewed = page.waitForResponse((response) => {
    if (!response.url().endsWith("/check-ins/preview") || !response.ok()) return false;
    return response.request().postDataJSON().expenses?.[0]?.comment === "Car wash";
  });
  await page.getByLabel("Amount").fill("5000");
  await page.getByLabel("Comment").fill("Car wash");
  await previewed;

  // This is a same-day, zero-accrual baseline (elapsed_days = 0), so the bucket has nothing
  // available yet and the 5,000 expense is entirely paid out of pocket -- triggering the existing
  // out-of-pocket confirmation dialog before the post actually happens.
  await page.getByRole("button", { name: "Continue" }).click(); // expenses -> review
  const posted = page.waitForResponse(
    (r) => r.url().includes("/check-ins") && !r.url().includes("/preview") && r.request().method() === "POST",
  );
  await page.getByRole("button", { name: /Confirm and post/ }).click();
  const postDialog = page.getByRole("dialog");
  await expect(postDialog.getByRole("heading", { name: "Paid out of pocket" })).toBeVisible();
  await postDialog.getByRole("button", { name: "Confirm and post" }).click();
  await posted;

  await page.getByRole("tab", { name: "History" }).click();
  const historyRow = page.getByRole("row").filter({ has: page.getByRole("cell", { name: "120,000" }) });
  await expect(historyRow.locator("td").nth(5)).toContainText("−5,000 Ft");

  const editTargetFetched = page.waitForResponse((r) => /\/check-ins\/[^/]+$/.test(r.url()) && r.ok());
  const initialEditPreviewed = page.waitForResponse(
    (r) => /\/check-ins\/[^/]+\/preview$/.test(r.url()) && r.ok(),
  );
  await page.getByRole("button", { name: "Edit this check-in" }).click();
  await editTargetFetched;
  await initialEditPreviewed;

  // Editing a past period is clearly indicated, and the period end field renders read-only (a plain
  // display value, not the editable date `<input>` the new-check-in flow uses).
  // The read-only period and the "editing a past period" banner render on the wizard's first step.
  await expect(page.getByText(/Editing the check-in for/)).toBeVisible();
  await expect(page.locator("input#checkin-period-end")).toHaveCount(0);
  await expect(page.getByRole("button", { name: /Update preview/ })).toHaveCount(0);

  // period -> expenses, where the editable amount lives.
  await page.getByRole("button", { name: "Continue" }).click();
  const editPreviewed = page.waitForResponse((response) => {
    if (!/\/check-ins\/[^/]+\/preview$/.test(response.url()) || !response.ok()) return false;
    return response.request().postDataJSON().expenses?.[0]?.amount === 8000;
  });
  await page.getByLabel("Amount").fill("8000");

  // expenses -> review, where the confirm button lives.
  await page.getByRole("button", { name: "Continue" }).click();
  await expect(page.getByRole("button", { name: /Confirm and post/ })).toBeDisabled();
  await editPreviewed;
  await expect(page.getByRole("button", { name: /Confirm and post/ })).toBeEnabled();

  const edited = page.waitForResponse(
    (r) => /\/check-ins\/[^/]+$/.test(r.url()) && r.request().method() === "PATCH" && r.ok(),
  );
  await page.getByRole("button", { name: /Confirm and post/ }).click();
  const editDialog = page.getByRole("dialog");
  await expect(editDialog.getByRole("heading", { name: "Paid out of pocket" })).toBeVisible();
  await editDialog.getByRole("button", { name: "Confirm and post" }).click();
  await edited;

  await expect(page.getByRole("heading", { name: "History" })).toBeVisible();
  const updatedRow = page.getByRole("row").filter({ has: page.getByRole("cell", { name: "120,000" }) });
  await expect(updatedRow.locator("td").nth(5)).toContainText("−8,000 Ft");
  // Locked-in decision: no "edited" indicator anywhere in the History row.
  await expect(updatedRow.getByText(/edited/i)).toHaveCount(0);
});
