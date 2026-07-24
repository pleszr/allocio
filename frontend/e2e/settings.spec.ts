import { expect, test } from "@playwright/test";

// The user-settings journey: open the sidebar user popover, change the display currency and assert
// money relabels in the sidebar (symbol only, numbers unchanged), then change the language and
// confirm both selections survive a reload (they are DB-backed via GET/PUT /api/users/me/settings).
// The dedicated live language-switch behaviour is covered in language.spec.ts; here we just confirm
// the language persists and is re-applied on reload, then restore English for later specs.
//
// A bucket is created first so there is money on screen to relabel. The suite runs serially against
// a shared throwaway DB, so this spec provisions its own asset rather than relying on another spec.

test("change currency relabels money and language persists across reload", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Your buckets" })).toBeVisible();

  // Create a vehicle bucket through the wizard so the sidebar shows a money balance.
  await page.getByRole("button", { name: "New bucket", exact: true }).click();
  const catalogFetched = page.waitForResponse(
    (r) => r.url().includes("/api/asset-templates/vehicle/catalog") && r.ok(),
  );
  await page.getByRole("button", { name: /Vehicle/ }).click();
  await catalogFetched;
  await page.getByTestId("bucket-name-input").fill("Currency Test Car");
  await page.getByRole("button", { name: /Continue/ }).click();
  await page.getByRole("button", { name: /Continue/ }).click();
  await page.getByRole("button", { name: /Create bucket/ }).click();
  await expect(page.getByRole("heading", { name: "Currency Test Car" })).toBeVisible();

  // The sidebar balance defaults to HUF (server default), so it renders with the "Ft" suffix.
  const balance = page.locator(".entity-balance").first();
  await expect(balance).toContainText("Ft");
  await expect(balance).not.toContainText("$");

  // Open the sidebar-footer user popover; it exposes the currency + language selects and Sign out.
  await page.locator(".user-menu-trigger").click();
  await expect(page.getByLabel("Default currency")).toBeVisible();
  await expect(page.getByLabel("Default currency")).toHaveValue("HUF");

  // Change the currency to USD; the PUT persists it and the balance relabels to "$" (number unchanged).
  const savedUsd = page.waitForResponse(
    (r) => r.url().includes("/api/users/me/settings") && r.request().method() === "PUT" && r.ok(),
  );
  await page.getByLabel("Default currency").selectOption("USD");
  await savedUsd;
  await expect(balance).toContainText("$");
  await expect(balance).not.toContainText("Ft");

  // Change the language to Hungarian; the same PUT persists it and the UI switches live.
  const savedHu = page.waitForResponse(
    (r) => r.url().includes("/api/users/me/settings") && r.request().method() === "PUT" && r.ok(),
  );
  await page.getByLabel("Language").selectOption("hu");
  await savedHu;

  // Reload: settings are DB-backed, so the persisted Hungarian language is applied on load — the
  // home heading now renders in Hungarian ("Perselyeid"). Reopen the popover and assert the
  // persisted values by id (the label text itself is language-dependent after the switch).
  await page.reload();
  await expect(page.getByRole("heading", { name: "Perselyeid" })).toBeVisible();
  await page.locator(".user-menu-trigger").click();
  await expect(page.locator("#currency-select")).toHaveValue("USD");
  await expect(page.locator("#language-select")).toHaveValue("hu");

  // Restore English so the shared-DB dev user is left in a clean state for later specs.
  const savedEn = page.waitForResponse(
    (r) => r.url().includes("/api/users/me/settings") && r.request().method() === "PUT" && r.ok(),
  );
  await page.locator("#language-select").selectOption("en");
  await savedEn;
  await expect(page.getByRole("heading", { name: "Your buckets" })).toBeVisible();
});
