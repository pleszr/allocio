import { expect, test } from "@playwright/test";

// The live language-switch journey: open the sidebar user popover and flip the Language selector.
// react-i18next re-renders the whole UI in place (no page reload), so a known English label becomes
// its Hungarian translation immediately, and reverts when switched back. Runs under AUTH_DISABLED.
//
// The suite runs serially against a shared DB; this spec restores English at the end so it leaves
// the dev user in a clean state for the specs that run after it.

test("language selector switches the UI language live and reverts", async ({ page }) => {
  await page.goto("/");

  // The home heading renders in the boot/English language before any switch.
  await expect(page.getByRole("heading", { name: "Your buckets" })).toBeVisible();

  // Open the sidebar-footer user popover; it holds the currency + language selects.
  await page.locator(".user-menu-trigger").click();
  await expect(page.getByLabel("Language")).toBeVisible();

  // Switch to Hungarian. The onChange calls i18n.changeLanguage immediately (live, no reload) and
  // fires the persistence PUT in the background. The home heading behind the popover flips to
  // Hungarian, and the popover's own "Language" label becomes "Nyelv".
  const savedHu = page.waitForResponse(
    (r) => r.url().includes("/api/users/me/settings") && r.request().method() === "PUT" && r.ok(),
  );
  await page.getByLabel("Language").selectOption("hu");
  await savedHu;
  await expect(page.getByRole("heading", { name: "Perselyeid" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Your buckets" })).toHaveCount(0);
  await expect(page.getByLabel("Nyelv")).toBeVisible();

  // Switch back to English via the now-Hungarian-labelled selector; the UI reverts live.
  const savedEn = page.waitForResponse(
    (r) => r.url().includes("/api/users/me/settings") && r.request().method() === "PUT" && r.ok(),
  );
  await page.getByLabel("Nyelv").selectOption("en");
  await savedEn;
  await expect(page.getByRole("heading", { name: "Your buckets" })).toBeVisible();
});
