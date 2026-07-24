import { useEffect, useRef, useState } from "react";
import { api, ApiError } from "../api/client";
import type { CurrencyCode, CurrentUser, LanguageCode, UserSettings } from "../api/types";

interface UserMenuProps {
  user: CurrentUser;
  settings: UserSettings;
  onSettingsSaved: (next: UserSettings) => void;
}

const CURRENCIES: { value: CurrencyCode; label: string }[] = [
  { value: "HUF", label: "HUF · Forint" },
  { value: "EUR", label: "EUR · Euro" },
  { value: "USD", label: "USD · Dollar" },
];

const LANGUAGES: { value: LanguageCode; label: string }[] = [
  { value: "en", label: "English" },
  { value: "hu", label: "Hungarian" },
  { value: "en_hu_alloc", label: "English + Hungarian allocation names" },
];

// The sidebar-footer user menu: the name row is a button that toggles a popover holding the
// currency + language selectors and Sign out. No routing and no modal — the popover is an
// absolutely-positioned element anchored to the footer.
export function UserMenu({ user, settings, onSettingsSaved }: UserMenuProps) {
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
      setError(err instanceof ApiError ? err.message : "Could not save settings.");
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
              Default currency
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
                  {c.label}
                </option>
              ))}
            </select>
          </div>

          <div className="field user-popover-field">
            <label className="field-label" htmlFor="language-select">
              Language
            </label>
            <select
              id="language-select"
              className="input"
              value={settings.language}
              disabled={saving}
              onChange={(e) => save({ ...settings, language: e.target.value as LanguageCode })}
            >
              {LANGUAGES.map((l) => (
                <option key={l.value} value={l.value}>
                  {l.label}
                </option>
              ))}
            </select>
            {/* Language is persist-only for now; UI translation lands in a later issue. */}
          </div>

          {error && <div className="error-banner user-popover-error">{error}</div>}

          <button className="logout-btn user-popover-signout" onClick={logout}>
            Sign out
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
