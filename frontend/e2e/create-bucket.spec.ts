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

  // Selecting the type card auto-advances straight to Step 2 — no separate Continue click.
  await expect(page.getByText("Tell us about it")).toBeVisible();

  // Step 2 — name is required; manufacture year is optional and the odometer seeds usage.
  await expect(page.getByLabel("Manufacture year (optional)")).toBeVisible();
  await expect(page.getByLabel("Current odometer")).toBeVisible();
  await expect(page.getByText("Make & model", { exact: true })).toHaveCount(0);
  await page.getByTestId("bucket-name-input").fill("E2E Test Car");
  await page.getByLabel("Manufacture year (optional)").fill("2020");
  await page.getByLabel("Current odometer").fill("120000");
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
  const requestBody = createResponse.request().postDataJSON();
  expect(requestBody.vehicle).toEqual({ manufacture_year: 2020, starting_odometer: 120000 });
  expect(requestBody).not.toHaveProperty("subtitle");
  expect(requestBody).not.toHaveProperty("attributes");

  // The app navigates into the new bucket's dashboard — the name shows as the page heading,
  // with no error banner or "not found" state (the reported regression).
  await expect(page.getByRole("heading", { name: "E2E Test Car" })).toBeVisible();
  await expect(page.locator(".error-banner")).toHaveCount(0);
  await expect(page.getByText(/not found/i)).toHaveCount(0);
});

test("vehicle manufacture year validation blocks an out-of-range value", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: "New bucket", exact: true }).click();
  const catalogFetched = page.waitForResponse(
    (response) => response.url().includes("/api/asset-templates/vehicle/catalog") && response.ok(),
  );
  await page.getByRole("button", { name: /Vehicle/ }).click();
  await catalogFetched;

  await page.getByTestId("bucket-name-input").fill("Year Validation Car");
  await page.getByLabel("Manufacture year (optional)").fill("1885");

  await expect(
    page.getByText(`Enter a year between 1886 and ${new Date().getFullYear()}.`, { exact: true }),
  ).toBeVisible();
  await expect(page.getByRole("button", { name: /Continue/ })).toBeDisabled();

  await page.getByLabel("Manufacture year (optional)").fill("2020");
  await expect(page.getByRole("button", { name: /Continue/ })).toBeEnabled();
});

test("create a property bucket from the House template", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Your buckets" })).toBeVisible();
  await page.getByRole("button", { name: "New bucket", exact: true }).click();
  const catalogFetched = page.waitForResponse(
    (response) => response.url().includes("/api/asset-templates/house/catalog") && response.ok(),
  );
  await page.getByRole("button", { name: /^Property/ }).click();
  await catalogFetched;

  await expect(page.getByText("Tell us about it")).toBeVisible();
  await expect(page.getByLabel("Bucket name")).toBeVisible();
  await expect(page.getByText("Address or label", { exact: true })).toHaveCount(0);
  await expect(page.getByText("Year built", { exact: true })).toHaveCount(0);
  await expect(page.getByText("Size", { exact: true })).toHaveCount(0);
  await page.getByTestId("bucket-name-input").fill("E2E Test Property");
  await page.getByRole("button", { name: /Continue/ }).click();

  for (const [key, label, amount] of [
    ["building_tax", "Building tax", "38000"],
    ["home_insurance", "Home insurance", "80000"],
    ["boiler_cleaning", "Boiler cleaning", "35000"],
    ["air_conditioner_cleaning", "Air-conditioner cleaning", "45000"],
  ]) {
    await expect(page.getByText(label, { exact: true })).toBeVisible();
    await expect(page.getByTestId(`catalog-amount-${key}`)).toHaveValue(amount);
  }
  await expect(page.getByLabel("Monthly safety buffer")).toHaveValue("18000");
  await expect(page.getByText("Usage reserve", { exact: true })).toHaveCount(0);
  await expect(page.getByText("Maintenance & replacements", { exact: true })).toHaveCount(0);

  // Edits survive moving back and forward within the same template.
  await page.getByTestId("catalog-amount-home_insurance").fill("81000");
  await page.getByLabel("Monthly safety buffer").fill("19000");
  await page.getByRole("button", { name: /Back/ }).click();
  await expect(page.getByLabel("Bucket name")).toHaveValue("E2E Test Property");
  await page.getByRole("button", { name: /Continue/ }).click();
  await expect(page.getByTestId("catalog-amount-home_insurance")).toHaveValue("81000");
  await expect(page.getByLabel("Monthly safety buffer")).toHaveValue("19000");

  await page.getByLabel("Monthly safety buffer").fill("");
  await expect(page.getByText("Enter a number that is 0 or greater.")).toBeVisible();
  await expect(page.getByRole("button", { name: /Continue/ })).toBeDisabled();

  const untouchedEstimate = page.waitForResponse((response) => {
    if (!response.url().endsWith("/api/allocation-estimates") || !response.ok()) return false;
    const body = response.request().postDataJSON();
    return (
      body.template === "house" &&
      body.manual_extra_monthly === 18000 &&
      body.cost_overrides?.some(
        (row: { technical_key: string; amount: number }) =>
          row.technical_key === "home_insurance" && row.amount === 80000,
      )
    );
  });
  await page.getByTestId("catalog-amount-home_insurance").fill("80000");
  await page.getByLabel("Monthly safety buffer").fill("18000");
  await untouchedEstimate;
  await page.getByRole("button", { name: /Continue/ }).click();

  await expect(page.locator(".allocation-callout")).toContainText("34,500 Ft");
  await expect(page.locator(".allocation-callout")).toContainText("414,000 Ft/year");
  for (const label of [
    "Building tax",
    "Home insurance",
    "Boiler cleaning",
    "Air-conditioner cleaning",
    "Monthly safety buffer",
  ]) {
    await expect(page.getByText(label, { exact: true })).toBeVisible();
  }

  const created = page.waitForResponse(
    (r) => r.url().endsWith("/api/assets") && r.request().method() === "POST",
  );
  await page.getByRole("button", { name: /Create bucket/ }).click();
  const createResponse = await created;
  expect(createResponse.status()).toBe(201);
  const requestBody = createResponse.request().postDataJSON();
  expect(requestBody.name).toBe("E2E Test Property");
  expect(requestBody.template).toBe("house");
  expect(requestBody.selected_cost_keys).toEqual([
    "building_tax",
    "home_insurance",
    "boiler_cleaning",
    "air_conditioner_cleaning",
  ]);
  expect(requestBody.cost_overrides).toEqual([
    { technical_key: "building_tax", amount: 38000, interval_value: 12, interval_unit: "months" },
    { technical_key: "home_insurance", amount: 80000, interval_value: 12, interval_unit: "months" },
    { technical_key: "boiler_cleaning", amount: 35000, interval_value: 12, interval_unit: "months" },
    { technical_key: "air_conditioner_cleaning", amount: 45000, interval_value: 12, interval_unit: "months" },
  ]);
  expect(requestBody.manual_extra_monthly).toBe(18000);
  expect(requestBody).not.toHaveProperty("type");
  expect(requestBody).not.toHaveProperty("vehicle");

  await expect(page.getByRole("heading", { name: "E2E Test Property" })).toBeVisible();
  await page.getByRole("tab", { name: "Costs" }).click();
  for (const label of [
    "Building tax",
    "Home insurance",
    "Boiler cleaning",
    "Air-conditioner cleaning",
  ]) {
    await expect(page.getByRole("row", { name: new RegExp(label) })).toHaveCount(1);
  }
  await expect(page.getByText("Manual extra", { exact: true })).toBeVisible();
  await expect(page.getByText("18,000 Ft/mo", { exact: true })).toBeVisible();
});

test("create a pet bucket with name only", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Your buckets" })).toBeVisible();
  await page.getByRole("button", { name: "New bucket", exact: true }).click();
  await page.getByRole("button", { name: /^Pet/ }).click();

  await expect(page.getByText("Tell us about it")).toBeVisible();
  await expect(page.getByLabel("Bucket name")).toBeVisible();
  await expect(page.getByText("Breed", { exact: true })).toHaveCount(0);
  await expect(page.getByText("Age", { exact: true })).toHaveCount(0);
  await expect(page.getByText("Weight", { exact: true })).toHaveCount(0);
  await page.getByTestId("bucket-name-input").fill("E2E Test Pet");
  await page.getByRole("button", { name: /Continue/ }).click();
  await page.getByRole("button", { name: /Continue/ }).click();

  const created = page.waitForResponse(
    (r) => r.url().endsWith("/api/assets") && r.request().method() === "POST",
  );
  await page.getByRole("button", { name: /Create bucket/ }).click();
  const createResponse = await created;
  expect(createResponse.status()).toBe(201);
  expect(createResponse.request().postDataJSON()).toEqual({
    name: "E2E Test Pet",
    type: "pet",
  });
  await expect(page.getByRole("heading", { name: "E2E Test Pet" })).toBeVisible();
});

test("switching templates preserves the name and ignores a late prior catalog", async ({ page }) => {
  let releaseVehicleCatalog: () => void = () => {};
  const heldVehicleCatalog = new Promise<void>((resolve) => {
    releaseVehicleCatalog = resolve;
  });
  await page.route("**/api/asset-templates/vehicle/catalog", async (route) => {
    await heldVehicleCatalog;
    await route.continue();
  });

  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Your buckets" })).toBeVisible();

  await page.getByRole("button", { name: "New bucket", exact: true }).click();
  const vehicleCatalogRequested = page.waitForRequest((request) =>
    request.url().includes("/api/asset-templates/vehicle/catalog"),
  );
  await page.getByRole("button", { name: /Vehicle/ }).click();
  await vehicleCatalogRequested;
  await expect(page.getByText("Tell us about it")).toBeVisible();
  await page.getByTestId("bucket-name-input").fill("Switching Home");

  // Back returns to Step 1 with the previously selected type still highlighted.
  await page.getByRole("button", { name: /Back/ }).click();
  await expect(page.getByRole("button", { name: /Vehicle/ })).toHaveAttribute("aria-pressed", "true");

  const houseCatalogFetched = page.waitForResponse(
    (response) => response.url().includes("/api/asset-templates/house/catalog") && response.ok(),
  );
  await page.getByRole("button", { name: /^Property/ }).click();
  await houseCatalogFetched;
  await expect(page.getByText("Tell us about it")).toBeVisible();
  await expect(page.getByTestId("bucket-name-input")).toHaveValue("Switching Home");
  const lateVehicleCatalog = page.waitForResponse(
    (response) => response.url().includes("/api/asset-templates/vehicle/catalog") && response.ok(),
  );
  releaseVehicleCatalog();
  await lateVehicleCatalog;
  await page.getByRole("button", { name: /Continue/ }).click();
  await expect(page.getByText("Building tax", { exact: true })).toBeVisible();
  await expect(page.getByText("Seasonal tire change", { exact: true })).toHaveCount(0);
});

test("House catalog retry keeps the active template and entered name", async ({ page }) => {
  let catalogCalls = 0;
  await page.route("**/api/asset-templates/house/catalog", async (route) => {
    catalogCalls += 1;
    if (catalogCalls === 1) {
      await route.fulfill({
        status: 503,
        contentType: "application/json",
        body: JSON.stringify({ detail: "Temporary catalog failure" }),
      });
      return;
    }
    await route.continue();
  });

  await page.goto("/");
  await page.getByRole("button", { name: "New bucket", exact: true }).click();
  const failedCatalog = page.waitForResponse(
    (response) =>
      response.url().includes("/api/asset-templates/house/catalog") &&
      response.status() === 503,
  );
  await page.getByRole("button", { name: /^Property/ }).click();
  await failedCatalog;
  await page.getByTestId("bucket-name-input").fill("Retry House");
  await page.getByRole("button", { name: /Continue/ }).click();

  await expect(page.getByText("Could not load the template catalog.")).toBeVisible();
  const retriedCatalog = page.waitForResponse(
    (response) => response.url().includes("/api/asset-templates/house/catalog") && response.ok(),
  );
  await page.getByRole("button", { name: "Retry" }).click();
  await retriedCatalog;
  await expect(page.getByText("Building tax", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: /Back/ }).click();
  await expect(page.getByTestId("bucket-name-input")).toHaveValue("Retry House");
});

test("editing a template row's amount and interval on Step 3 persists the edited value", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Your buckets" })).toBeVisible();

  await page.getByRole("button", { name: "New bucket", exact: true }).click();
  const catalogFetched = page.waitForResponse(
    (r) => r.url().includes("/api/asset-templates/vehicle/catalog") && r.ok(),
  );
  await page.getByRole("button", { name: /Vehicle/ }).click();
  await catalogFetched;

  await page.getByTestId("bucket-name-input").fill("E2E Edited Car");
  await page.getByRole("button", { name: /Continue/ }).click();

  // Step 3 — the mandatory liability insurance row is pre-filled from the template default;
  // edit both its amount and its interval before creating the bucket.
  await page.getByTestId("catalog-amount-mandatory_liability_insurance").fill("60000");
  await page.getByTestId("catalog-interval-value-mandatory_liability_insurance").fill("6");
  await page.getByRole("button", { name: /Continue/ }).click();

  const created = page.waitForResponse((r) => r.url().endsWith("/api/assets") && r.request().method() === "POST");
  await page.getByRole("button", { name: /Create bucket/ }).click();
  await created;
  await expect(page.getByRole("heading", { name: "E2E Edited Car" })).toBeVisible();

  // The Costs screen reads the persisted row back from the API — confirms the override reached
  // the backend and was cloned instead of the template default (50119/12 months).
  await page.getByRole("tab", { name: "Costs" }).click();
  const liabilityRow = page.getByRole("row", { name: /Mandatory liability insurance/ });
  await expect(liabilityRow).toContainText("60,000");
  await expect(liabilityRow).toContainText("6");
  await expect(liabilityRow).toContainText("328.77");
});

test("allocation estimate retries through the backend and preserves wizard input", async ({ page }) => {
  let estimateCalls = 0;
  await page.route("**/api/allocation-estimates", async (route) => {
    estimateCalls += 1;
    if (estimateCalls === 1) {
      await route.fulfill({
        status: 503,
        contentType: "application/json",
        body: JSON.stringify({ detail: "Temporary estimate failure" }),
      });
      return;
    }
    await route.continue();
  });

  await page.goto("/");
  await page.getByRole("button", { name: "New bucket", exact: true }).click();
  await page.getByRole("button", { name: /^Property/ }).click();
  await page.getByTestId("bucket-name-input").fill("Estimate Retry Property");
  await page.getByRole("button", { name: /Continue/ }).click();

  await page.getByText("Add a custom cost…").click();
  const row = page.locator(".cost-row");
  await row.getByPlaceholder("Cost name").fill("Annual repair");
  await row.locator('input[type="number"]').fill("1200");
  await page.getByRole("button", { name: /Continue/ }).click();

  await expect(page.getByText("Temporary estimate failure")).toBeVisible();
  await page.getByRole("button", { name: "Retry" }).click();
  await expect(page.getByText("34,600 Ft", { exact: true })).toBeVisible();

  await page.getByRole("button", { name: /Back/ }).click();
  await expect(page.getByPlaceholder("Cost name")).toHaveValue("Annual repair");
  await expect(row.locator('input[type="number"]')).toHaveValue("1200");
});

test("misleading free-form car type does not enable usage input", async ({ page }) => {
  const name = "Display-only Car Type";
  const created = await page.request.post("/api/assets", {
    data: { name, type: "car" },
  });
  expect(created.status()).toBe(201);

  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Your buckets" })).toBeVisible();
  await page.locator(".side-entity").filter({ hasText: name }).click();
  const previewRequest = page.waitForRequest(
    (request) => request.url().includes("/check-ins/preview") && request.method() === "POST",
  );
  await page.getByRole("tab", { name: "Check-in" }).click();

  await expect(page.getByLabel("Current usage")).toHaveCount(0);
  expect((await previewRequest).postDataJSON().usage_end).toBeNull();
});
