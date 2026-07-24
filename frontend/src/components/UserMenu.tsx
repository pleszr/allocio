import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { api, ApiError } from "../api/client";
import type { CurrencyCode, CurrentUser, LanguageCode, UserSettings } from "../api/types";
import { resolveLanguage } from "../i18n";

interface UserMenuProps {
  user: CurrentUser;
  settings: UserSettings;
  onSettingsSaved: (next: UserSettings) => void;
}

// The `value`s are the API contract in `src/api/types.ts` and must stay byte-identical; only the
// display label is translated (via `labelKey`) so the option text switches language live.
const CURRENCIES: { value: CurrencyCode; labelKey: string }[] = [
  { value: "HUF", labelKey: "userMenu.currency_huf" },
  { value: "EUR", labelKey: "userMenu.currency_eur" },
  { value: "USD", labelKey: "userMenu.currency_usd" },
];

// `en_hu_alloc` is intentionally omitted — it is not yet a real locale, so it is hidden from the
// selector. A row that already persists it renders as English via `resolveLanguage`.
const LANGUAGES: { value: LanguageCode; labelKey: string }[] = [
  { value: "en", labelKey: "userMenu.language_en" },
  { value: "hu", labelKey: "userMenu.language_hu" },
];

// The sidebar-footer user menu: the name row is a button that toggles a popover holding the
// currency + language selectors and Sign out. No routing and no modal — the popover is an
// absolutely-positioned element anchored to the footer.
export function UserMenu({ user, settings, onSettingsSaved }: UserMenuProps) {
  const { t, i18n } = useTranslation();
  const [open, setOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const rootRef = useRef<HTMLDivElement>(null);

  // Standard "click-outside to dismiss": while open, a document mousedown outside the menu root
  // closes the popover, and Escape closes it too. Both listeners are cleaned up on close/unmount.
  useEffect(() => {
    if (!open) return;
    const onMouseDown = (e: MouseEvent) => {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) setOpen(false);
    };
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", onMouseDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("mousedown", onMouseDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [open]);

  // Persist a changed setting. On success, lift the saved value to `prefs` in Workspace (which
  // relabels all money via the provider). On failure, keep the popover open, surface the message,
  // and leave `prefs` untouched so the UI still reflects the last saved value.
  const save = async (next: UserSettings) => {
    setSaving(true);
    setError(null);
    try {
      const saved = await api.updateSettings(next);
      onSettingsSaved(saved);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t("userMenu.save_error"));
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="user-menu" ref={rootRef}>
      {open && (
        <div className="user-popover" role="menu">
          <div className="user-popover-head">
            <div className="user-name">{user.name || user.email}</div>
            <div className="user-email">{user.email}</div>
          </div>

          <div className="field user-popover-field">
            <label className="field-label" htmlFor="currency-select">
              {t("userMenu.default_currency")}
            </label>
            <select
              id="currency-select"
              className="input"
              value={settings.default_currency}
              disabled={saving}
              onChange={(e) => save({ ...settings, default_currency: e.target.value as CurrencyCode })}
            >
              {CURRENCIES.map((c) => (
                <option key={c.value} value={c.value}>
                  {t(c.labelKey)}
                </option>
              ))}
            </select>
          </div>

          <div className="field user-popover-field">
            <label className="field-label" htmlFor="language-select">
              {t("userMenu.language")}
            </label>
            <select
              id="language-select"
              className="input"
              value={settings.language}
              disabled={saving}
              onChange={(e) => {
                const language = e.target.value as LanguageCode;
                // Switch the UI language immediately (fire-and-forget for display), independent of
                // the persistence PUT below. If the PUT fails, the display may be ahead of the
                // saved value until retry — acceptable per the settings flow.
                void i18n.changeLanguage(resolveLanguage(language));
                save({ ...settings, language });
              }}
            >
              {LANGUAGES.map((l) => (
                <option key={l.value} value={l.value}>
                  {t(l.labelKey)}
                </option>
              ))}
            </select>
          </div>

          {error && <div className="error-banner user-popover-error">{error}</div>}

          <button className="logout-btn user-popover-signout" onClick={logout}>
            {t("userMenu.sign_out")}
          </button>
        </div>
      )}

      <button
        className="user-menu-trigger"
        aria-haspopup="menu"
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
      >
        <div className="sidebar-user">
          <div className="user-name">{user.name || user.email}</div>
          <div className="user-email">{user.email}</div>
        </div>
      </button>
    </div>
  );
}

// Best-effort logout: clear the session server-side, then reload so the auth gate re-checks and
// shows the sign-in screen. Reload even if the call fails — a failed logout must not trap the user.
async function logout(): Promise<void> {
  try {
    await api.logout();
  } finally {
    window.location.reload();
  }
}
