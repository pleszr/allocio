import { expect, test, type Page } from "@playwright/test";

type HistoryRow = {
  check_in_id: string;
  period_end: string;
  usage_end: number;
  usage_since_last: number;
  elapsed_days: number;
  allocated: number;
  spent: number;
  covered_by_bucket: number;
  paid_out_of_pocket: number;
  net: number;
  balance: number;
};

test("dashboard derives adaptive allocation and annual-service signals", async ({ page }) => {
  const bucketName = "E2E Dashboard Signals Car";
  const today = new Date();
  let historyRows = threeMonthRows(today);
  let historyUnavailable = false;

  await page.route("**/api/assets/*/check-in-history", async (route) => {
    if (historyUnavailable) {
      await route.fulfill({ status: 503, json: { detail: "History temporarily unavailable" } });
      return;
    }
    await route.fulfill({
      status: 200,
      json: { asset_id: "dashboard-signals-test", currency: "HUF", rows: historyRows },
    });
  });

  const assetId = await createVehicleBucket(page, bucketName);
  const dashboard = page.locator(".content");
  const averageBlock = dashboard.locator(".entity-hero");
  const annualServiceKpi = dashboard.locator(".kpi").filter({ hasText: "Until annual service" });

  await assertAverage(averageBlock, "200 Ft", 3);
  await expect(dashboard.getByText("Next allocation", { exact: true })).toHaveCount(0);
  await expect(annualServiceKpi).toContainText("Set the last service odometer");

  historyRows = sixMonthRows(today);
  await reloadDashboard(page, bucketName);
  await assertAverage(page.locator(".entity-hero"), "1,200 Ft", 6);

  historyRows = twelveMonthRows(today);
  await reloadDashboard(page, bucketName);
  await assertAverage(page.locator(".entity-hero"), "2,400 Ft", 12);

  historyRows = [];
  await reloadDashboard(page, bucketName);
  await expect(page.locator(".entity-hero").getByText("No allocation history", { exact: true })).toBeVisible();

  historyUnavailable = true;
  await reloadDashboard(page, bucketName);
  const unavailableBlock = page.locator(".entity-hero");
  await expect(unavailableBlock.getByText("Allocation history unavailable", { exact: true })).toBeVisible();
  const retry = unavailableBlock.getByRole("button", { name: "Try again" });
  await expect(retry).toHaveClass(/btn-ghost/);

  historyRows = threeMonthRows(today);
  historyUnavailable = false;
  await retry.click();
  await assertAverage(unavailableBlock, "200 Ft", 3);

  const detailResponse = await page.request.get(`/api/assets/${assetId}`);
  expect(detailResponse.ok()).toBeTruthy();
  const detail = await detailResponse.json();
  const annualService = detail.maintenance_items.find(
    (item: { technical_key: string | null }) => item.technical_key === "annual_service",
  );
  expect(annualService).toBeTruthy();

  const baselineResponse = await page.request.patch(
    `/api/assets/${assetId}/maintenance-items/${annualService.id}`,
    { data: { last_serviced_at_odometer: 120000 } },
  );
  expect(baselineResponse.ok()).toBeTruthy();
  await reloadDashboard(page, bucketName);
  await expect(page.locator(".kpi").filter({ hasText: "Until annual service" })).toContainText("12,000 km");

  const deactivateResponse = await page.request.patch(
    `/api/assets/${assetId}/maintenance-items/${annualService.id}`,
    { data: { is_active: false } },
  );
  expect(deactivateResponse.ok()).toBeTruthy();
  await reloadDashboard(page, bucketName);
  await expect(page.locator(".kpi").filter({ hasText: "Until annual service" })).toContainText(
    "Annual service not configured",
  );
});

async function createVehicleBucket(page: Page, name: string): Promise<string> {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Your buckets" })).toBeVisible();
  await page.getByRole("button", { name: "New bucket", exact: true }).click();

  const catalogFetched = page.waitForResponse(
    (response) => response.url().includes("/api/asset-templates/vehicle/catalog") && response.ok(),
  );
  await page.getByRole("button", { name: /Vehicle/ }).click();
  await catalogFetched;
  await page.getByTestId("bucket-name-input").fill(name);
  await page.getByLabel("Current odometer").fill("120000");
  await page.getByRole("button", { name: /Continue/ }).click();
  await page.getByRole("button", { name: /Continue/ }).click();

  const created = page.waitForResponse(
    (response) => response.url().endsWith("/api/assets") && response.request().method() === "POST",
  );
  await page.getByRole("button", { name: /Create bucket/ }).click();
  const createResponse = await created;
  expect(createResponse.status()).toBe(201);
  const body = await createResponse.json();
  await expect(page.getByRole("heading", { name })).toBeVisible();
  return body.asset.id;
}

async function reloadDashboard(page: Page, bucketName: string): Promise<void> {
  await page.reload();
  await expect(page.getByRole("heading", { name: "Your buckets" })).toBeVisible();
  await page.locator(".side-entity").filter({ hasText: bucketName }).click();
  await expect(page.getByRole("heading", { name: bucketName })).toBeVisible();
}

async function assertAverage(block: ReturnType<Page["locator"]>, amount: string, months: 3 | 6 | 12): Promise<void> {
  await expect(block.getByText(amount, { exact: true })).toBeVisible();
  await expect(block.getByText(`Average over the last ${months} months`, { exact: true })).toBeVisible();
}

function threeMonthRows(today: Date): HistoryRow[] {
  return [
    historyRow("three-boundary", subtractMonthsClamped(today, 5), 900),
    historyRow("three-current", localDateIso(today), 100),
    historyRow("three-two-months", subtractMonthsClamped(today, 2), 300),
  ];
}

function sixMonthRows(today: Date): HistoryRow[] {
  return [
    historyRow("six-boundary", subtractMonthsClamped(today, 6), 600),
    historyRow("six-current", localDateIso(today), 1200),
    historyRow("six-two-months", subtractMonthsClamped(today, 2), 1800),
  ];
}

function twelveMonthRows(today: Date): HistoryRow[] {
  return [
    historyRow("twelve-boundary", subtractMonthsClamped(today, 12), 1200),
    historyRow("twelve-current", localDateIso(today), 2400),
    historyRow("twelve-five-months", subtractMonthsClamped(today, 5), 3600),
  ];
}

function historyRow(checkInId: string, periodEnd: string, allocated: number): HistoryRow {
  return {
    check_in_id: checkInId,
    period_end: periodEnd,
    usage_end: 120000,
    usage_since_last: 0,
    elapsed_days: 30,
    allocated,
    spent: 0,
    covered_by_bucket: 0,
    paid_out_of_pocket: 0,
    net: allocated,
    balance: allocated,
  };
}

function subtractMonthsClamped(today: Date, months: number): string {
  const firstOfTargetMonth = new Date(Date.UTC(today.getFullYear(), today.getMonth() - months, 1));
  const targetYear = firstOfTargetMonth.getUTCFullYear();
  const targetMonth = firstOfTargetMonth.getUTCMonth();
  const finalDay = new Date(Date.UTC(targetYear, targetMonth + 1, 0)).getUTCDate();
  return datePartsIso(targetYear, targetMonth, Math.min(today.getDate(), finalDay));
}

function localDateIso(date: Date): string {
  return datePartsIso(date.getFullYear(), date.getMonth(), date.getDate());
}

function datePartsIso(year: number, zeroBasedMonth: number, day: number): string {
  return `${year}-${String(zeroBasedMonth + 1).padStart(2, "0")}-${String(day).padStart(2, "0")}`;
}
