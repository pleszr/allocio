import { expect, test, type Page } from "@playwright/test";

type AverageAllocation = {
  months: 3 | 6 | 12;
  amount: number | null;
};

test("dashboard renders backend-derived vehicle overview and next-maintenance signals", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 1000 });
  const bucketName = "E2E Dashboard Signals Car";
  let averageAllocation: AverageAllocation = { amount: 200, months: 3 };
  let trackedInAppMonths = 23;
  let nextMaintenance: { label: string; remaining_km: number } | null = {
    label: "Oil service",
    remaining_km: 1500,
  };

  await page.route("**/api/assets/*", async (route) => {
    const request = route.request();
    const pathParts = new URL(request.url()).pathname.split("/").filter(Boolean);
    const isAssetDetail =
      request.method() === "GET" &&
      pathParts.length === 3 &&
      pathParts[0] === "api" &&
      pathParts[1] === "assets";
    if (!isAssetDetail) {
      await route.continue();
      return;
    }

    const response = await route.fetch();
    const detail = await response.json();
    await route.fulfill({
      response,
      json: {
        ...detail,
        average_allocation: averageAllocation,
        vehicle_age_years: 6,
        tracked_in_app_months: trackedInAppMonths,
        average_monthly_cost: 1200,
        next_maintenance: nextMaintenance,
        current_usage: 121012,
        usage_since_last_check_in: 1012,
        upcoming_expenses: [
          {
            name: "Annual service",
            category: "maintenance",
            days_until: 90,
            amount: 12345,
            overdue: false,
          },
        ],
      },
    });
  });

  const assetId = await createVehicleBucket(page, bucketName);
  const dashboard = page.locator(".content");
  const averageBlock = dashboard.locator(".entity-hero");
  const overviewKpi = dashboard.locator(".kpi").filter({ hasText: "Vehicle overview" });
  const currentUsageKpi = dashboard.locator(".kpi").filter({ hasText: "Current usage" });
  const nextMaintenanceKpi = dashboard.locator(".kpi").filter({ hasText: "Next maintenance" });

  await assertAverage(averageBlock, "200 Ft", 3);
  await expect(dashboard.getByText("Next allocation", { exact: true })).toHaveCount(0);
  await expect(overviewKpi).toContainText("Vehicle is 6 years old.");
  await expect(overviewKpi).toContainText("It has been tracked in the app for 23 months.");
  await expect(overviewKpi).toContainText("Average monthly cost over the last 12 months was 1,200 Ft.");
  await expect(currentUsageKpi).toContainText("121,012");
  await expect(currentUsageKpi).toContainText("+1,012 km since last check-in");
  await expect(nextMaintenanceKpi).toContainText(
    "Next maintenance is Oil service and it is 1,500 km away.",
  );
  const upcomingCard = dashboard.locator(".card").filter({ hasText: "Upcoming expenses" });
  await expect(upcomingCard.getByText("Annual service", { exact: true })).toBeVisible();
  await expect(upcomingCard).toContainText("Maintenance · in ~90d");
  await expect(upcomingCard).toContainText("12,345 Ft");
  await expect(upcomingCard.getByText("Nothing forecasted in this window.", { exact: true })).toHaveCount(0);
  await expect(dashboard.getByText("Until annual service", { exact: true })).toHaveCount(0);
  await assertDashboardWidgetLayout(page, dashboard);

  const threeMonthHistory = page.waitForRequest((request) => {
    const url = new URL(request.url());
    return url.pathname === `/api/assets/${assetId}/balance-history` && url.searchParams.get("months") === "3";
  });
  await dashboard.getByRole("button", { name: "3M", exact: true }).click();
  await threeMonthHistory;
  await expect(dashboard.getByRole("button", { name: "3M", exact: true })).toHaveAttribute("aria-pressed", "true");

  await page.setViewportSize({ width: 700, height: 1000 });
  await assertDashboardWidgetLayout(page, dashboard, true);
  await page.setViewportSize({ width: 1440, height: 1000 });

  averageAllocation = { amount: 1200, months: 6 };
  await reloadDashboard(page, bucketName);
  await assertAverage(page.locator(".entity-hero"), "1,200 Ft", 6);

  averageAllocation = { amount: 2400, months: 12 };
  await reloadDashboard(page, bucketName);
  await assertAverage(page.locator(".entity-hero"), "2,400 Ft", 12);

  averageAllocation = { amount: null, months: 3 };
  await reloadDashboard(page, bucketName);
  await expect(page.locator(".entity-hero").getByText("No allocation history", { exact: true })).toBeVisible();

  trackedInAppMonths = 24;
  nextMaintenance = null;
  await reloadDashboard(page, bucketName);
  await expect(page.locator(".kpi").filter({ hasText: "Vehicle overview" })).toContainText(
    "It has been tracked in the app for 2 years and 0 months.",
  );
  await expect(page.locator(".kpi").filter({ hasText: "Next maintenance" })).toContainText(
    "No upcoming kilometer-based maintenance is available.",
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
  await page.getByLabel("Manufacture year (optional)").fill("2020");
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

async function assertDashboardWidgetLayout(
  page: Page,
  dashboard: ReturnType<Page["locator"]>,
  stacked = false,
): Promise<void> {
  const widgetGrid = dashboard.locator(".col-2");
  const maintenanceCard = widgetGrid.locator(":scope > .card");
  const rightStack = widgetGrid.locator(":scope > .stack");
  const recentActivityCard = rightStack.locator(".card").filter({ hasText: "Recent activity" });
  const balanceHistoryCard = rightStack.locator(".card").filter({ hasText: "Balance history" });
  const dashboardCards = dashboard.locator(".card");

  await expect(recentActivityCard).toBeVisible();
  await expect(balanceHistoryCard).toBeVisible();
  await expect(dashboardCards.last()).toContainText("Balance history");

  const titles = await dashboard.locator(".card-title").allTextContents();
  expect(titles.indexOf("Recent activity")).toBeLessThan(titles.indexOf("Balance history"));
  expect(titles.at(-1)).toBe("Balance history");

  const [dashboardBox, maintenanceBox, rightStackBox, balanceBox] = await Promise.all([
    dashboard.boundingBox(),
    maintenanceCard.boundingBox(),
    rightStack.boundingBox(),
    balanceHistoryCard.boundingBox(),
  ]);
  expect(dashboardBox).not.toBeNull();
  expect(maintenanceBox).not.toBeNull();
  expect(rightStackBox).not.toBeNull();
  expect(balanceBox).not.toBeNull();

  if (stacked) {
    expect(rightStackBox!.x).toBeCloseTo(maintenanceBox!.x, 0);
    expect(rightStackBox!.y).toBeGreaterThanOrEqual(maintenanceBox!.y + maintenanceBox!.height - 1);
    expect(balanceBox!.width / dashboardBox!.width).toBeGreaterThan(0.9);
    const hasHorizontalOverflow = await page.evaluate(
      () => document.documentElement.scrollWidth > document.documentElement.clientWidth,
    );
    expect(hasHorizontalOverflow).toBe(false);
  } else {
    expect(rightStackBox!.x).toBeGreaterThan(maintenanceBox!.x + maintenanceBox!.width - 1);
    expect(balanceBox!.width / dashboardBox!.width).toBeGreaterThan(0.42);
    expect(balanceBox!.width / dashboardBox!.width).toBeLessThan(0.52);
  }
}
