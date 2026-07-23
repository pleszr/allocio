# Google authentication setup

Allocio signs users in with Google using the server-side OAuth 2.0 Authorization-Code flow. This
guide covers the one-time Google Cloud console setup and the backend environment variables that wire
it up. See issue #62.

## 1. Create (or pick) a Google Cloud project

1. Go to <https://console.cloud.google.com/>.
2. In the project picker (top bar), **New Project** — name it e.g. `allocio` — **Create**, then select it.

## 2. Configure the OAuth consent screen

1. Navigation menu → **APIs & Services** → **OAuth consent screen**.
2. **User type: External** → **Create**.
3. App information: set the **App name** (`Allocio`), your **User support email**, and a **Developer
   contact email**. Leave logo/domain optional for MVP. **Save and continue**.
4. **Scopes** → **Add or remove scopes** → add exactly:
   - `openid`
   - `.../auth/userinfo.email` (email)
   - `.../auth/userinfo.profile` (profile)

   These map to the app's requested scope string `openid email profile`. **Update** → **Save and continue**.
5. **Test users**: while the app is in **Testing** (not published), only listed test users can sign
   in. **Add users** → add every Google account that will sign in during development. **Save and continue**.
6. Review the summary and **Back to dashboard**. Leave the publishing status on **Testing** for MVP.

## 3. Create an OAuth 2.0 Web application client

1. **APIs & Services** → **Credentials** → **Create credentials** → **OAuth client ID**.
2. **Application type: Web application**. Name it e.g. `allocio-web`.
3. **Authorized redirect URIs** → **Add URI** for each environment the callback runs in. The callback
   path is fixed at `/api/auth/callback`:
   - Local dev: `http://localhost:8000/api/auth/callback`
   - Production: `https://<your-host>/api/auth/callback`
4. **Create**. Copy the **Client ID** and **Client secret** shown in the dialog — these are the
   `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET` below.

## 4. Backend environment variables

Set these in the backend environment (e.g. `backend/.env`, which is git-ignored — never commit real
values; a gitleaks hook scans commits). Auth is **on** by default; when it is on, the three required
vars must be present or the process fails loud at startup naming the missing ones.

| Variable | Required when | Purpose |
| --- | --- | --- |
| `AUTH_DISABLED` | never (optional) | `true` bypasses Google for local dev / e2e (returns a synthetic dev user, no session). Unset or `false` in production. |
| `GOOGLE_CLIENT_ID` | auth enabled | OAuth client ID from step 3. |
| `GOOGLE_CLIENT_SECRET` | auth enabled | OAuth client secret from step 3. |
| `SESSION_SECRET` | auth enabled | Random high-entropy string signing the session cookie. Generate e.g. `python -c "import secrets; print(secrets.token_urlsafe(48))"`. |
| `OAUTH_REDIRECT_BASE_URL` | optional | Origin used to build the callback URL. Defaults to `http://localhost:8000`; set to the public origin (e.g. `https://<your-host>`) in production. |

### Local development

- **Without Google** (fastest for UI work and the e2e suite): set `AUTH_DISABLED=true`. The app
  renders past the sign-in gate as the dev user; no Google creds needed.
- **With the real Google flow**: set `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, and `SESSION_SECRET`,
  and leave `AUTH_DISABLED` unset. Visit the app, click **Sign in with Google**, and complete consent.

Example `backend/.env` for the real flow (placeholder values — replace with your own):

```
GOOGLE_CLIENT_ID=your-client-id.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=your-client-secret
SESSION_SECRET=replace-with-a-long-random-string
# OAUTH_REDIRECT_BASE_URL=http://localhost:8000  # default; override in prod
```

## 5. Notes

- The session cookie is HttpOnly, `SameSite=Lax`, and signed (`itsdangerous`). The app and API are
  same-origin (Vite proxy in dev, single VM in prod), so no CORS or bearer-token handling is needed.
- Adding a new environment (e.g. staging) means adding its `/api/auth/callback` URL to the client's
  authorized redirect URIs and setting `OAUTH_REDIRECT_BASE_URL` for that environment.
