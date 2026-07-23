// The unauthenticated gate screen. Presentational only — no data fetching, no props.
// "Sign in with Google" is a full-page navigation to the backend OAuth flow (not a fetch):
// the backend redirects to Google and, on return, sets the session cookie and bounces to `/`.
// A `?auth_error=1` on the URL (set by the backend callback on OAuth failure) shows a retry note.

const authFailed = new URLSearchParams(window.location.search).has("auth_error");

export function SignInScreen() {
  return (
    <div className="signin-wrap">
      <div className="signin-card">
        <div className="brand signin-brand">
          <div className="brand-mark">α</div>
          <div className="brand-name">allocio</div>
        </div>
        <p className="signin-lead">Smooth out your irregular asset costs into steady monthly savings.</p>
        {authFailed && <p className="signin-error">Sign-in failed. Please try again.</p>}
        <a className="btn btn-primary signin-btn" href="/api/auth/login">
          Sign in with Google
        </a>
      </div>
    </div>
  );
}
