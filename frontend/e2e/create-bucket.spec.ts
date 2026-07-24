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

  // Step 2 — name is required; odometer is the only remaining vehicle metadata.
  await expect(page.getByLabel("Current odometer")).toBeVisible();
  await expect(page.getByText("Make & model", { exact: true })).toHaveCount(0);
  await expect(page.getByText("Year", { exact: true })).toHaveCount(0);
  await page.getByTestId("bucket-name-input").fill("E2E Test Car");
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
  expect(requestBody.vehicle).toEqual({ starting_odometer: 120000 });
  expect(requestBody).not.toHaveProperty("subtitle");
  expect(requestBody).not.toHaveProperty("attributes");

  // The app navigates into the new bucket's dashboard — the name shows as the page heading,
  // with no error banner or "not found" state (the reported regression).
  await expect(page.getByRole("heading", { name: "E2E Test Car" })).toBeVisible();
  await expect(page.locator(".error-banner")).toHaveCount(0);
  await expect(page.getByText(/not found/i)).toHaveCount(0);
});

test("create a property bucket with name only", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Your buckets" })).toBeVisible();
  await page.getByRole("button", { name: "New bucket", exact: true }).click();
  await page.getByRole("button", { name: /^Property/ }).click();

  await expect(page.getByText("Tell us about it")).toBeVisible();
  await expect(page.getByLabel("Bucket name")).toBeVisible();
  await expect(page.getByText("Address or label", { exact: true })).toHaveCount(0);
  await expect(page.getByText("Year built", { exact: true })).toHaveCount(0);
  await expect(page.getByText("Size", { exact: true })).toHaveCount(0);
  await page.getByTestId("bucket-name-input").fill("E2E Test Property");
  await page.getByRole("button", { name: /Continue/ }).click();
  await page.getByRole("button", { name: /Continue/ }).click();

  const created = page.waitForResponse(
    (r) => r.url().endsWith("/api/assets") && r.request().method() === "POST",
  );
  await page.getByRole("button", { name: /Create bucket/ }).click();
  const createResponse = await created;
  expect(createResponse.status()).toBe(201);
  expect(createResponse.request().postDataJSON()).toEqual({
    name: "E2E Test Property",
    type: "house",
  });
  await expect(page.getByRole("heading", { name: "E2E Test Property" })).toBeVisible();
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

test("Back from Step 2 preserves the selected type and re-advances on a new pick", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Your buckets" })).toBeVisible();

  await page.getByRole("button", { name: "New bucket", exact: true }).click();
  const catalogFetched = page.waitForResponse(
    (r) => r.url().includes("/api/asset-templates/vehicle/catalog") && r.ok(),
  );
  await page.getByRole("button", { name: /Vehicle/ }).click();
  await catalogFetched;
  await expect(page.getByText("Tell us about it")).toBeVisible();

  // Back returns to Step 1 with the previously selected type still highlighted.
  await page.getByRole("button", { name: /Back/ }).click();
  await expect(page.getByRole("button", { name: /Vehicle/ })).toHaveAttribute("aria-pressed", "true");

  // Picking a different type re-advances straight to Step 2 with the new type reflected.
  await page.getByRole("button", { name: /^Property/ }).click();
  await expect(page.getByText("Tell us about it")).toBeVisible();
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
});
