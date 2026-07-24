import i18n from "i18next";
import { initReactI18next } from "react-i18next";
import type { LanguageCode } from "./api/types";
import en from "./locales/en.json";
import hu from "./locales/hu.json";

// react-i18next initialization. Bundled, synchronous, in-memory resources — no network fetch,
// no language detector. The active language is driven solely by the persisted `User.language`
// (applied in App.tsx / UserMenu.tsx via `changeLanguage`), never by the browser locale.
void i18n.use(initReactI18next).init({
  resources: {
    en: { translation: en },
    hu: { translation: hu },
  },
  lng: "en",
  fallbackLng: "en",
  interpolation: {
    // React already escapes rendered output, so i18next must not double-escape.
    escapeValue: false,
  },
  // A missing key returns the key string, never null into JSX.
  returnNull: false,
});

// Single choke point mapping a persisted LanguageCode onto a real UI locale. `'hu'` renders
// Hungarian; every other value — `'en'` and the not-yet-implemented `'en_hu_alloc'` — falls back
// to English. This keeps a pre-existing persisted `en_hu_alloc` row from breaking rendering.
export function resolveLanguage(code: LanguageCode): "en" | "hu" {
  return code === "hu" ? "hu" : "en";
}

export default i18n;
