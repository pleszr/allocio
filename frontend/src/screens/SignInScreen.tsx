// The unauthenticated gate screen. Presentational only — no data fetching, no props.
// "Sign in with Google" is a full-page navigation to the backend OAuth flow (not a fetch):
// the backend redirects to Google and, on return, sets the session cookie and bounces to `/`.
// A `?auth_error=1` on the URL (set by the backend callback on OAuth failure) shows a retry note.

import { useTranslation } from "react-i18next";

const authFailed = new URLSearchParams(window.location.search).has("auth_error");

export function SignInScreen() {
  const { t } = useTranslation();
  return (
    <div className="signin-wrap">
      <div className="signin-card">
        <div className="brand signin-brand">
          <div className="brand-mark">α</div>
          <div className="brand-name">allocio</div>
        </div>
        <p className="signin-lead">{t("signin.lead")}</p>
        {authFailed && <p className="signin-error">{t("signin.error")}</p>}
        <a className="btn btn-primary signin-btn" href="/api/auth/login">
          {t("signin.button")}
        </a>
      </div>
    </div>
  );
}
