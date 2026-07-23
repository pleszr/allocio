from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "postgresql+psycopg://allocio:allocio@localhost:5432/allocio"

    # Auth. `auth_disabled` is the dev/e2e bypass; when it is off, real Google creds and a
    # session secret are required and their absence is a fail-loud startup error (see validator).
    auth_disabled: bool = False
    google_client_id: str | None = None
    google_client_secret: str | None = None
    session_secret: str | None = None
    # Base origin used to build the fixed OAuth callback URL (`/api/auth/callback`); override per env.
    oauth_redirect_base_url: str = "http://localhost:8000"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @model_validator(mode="after")
    def _require_auth_config_when_enabled(self) -> "Settings":
        """Fail loud when auth is enabled but its required secrets are missing.

        Honors the no-placeholder-defaults rule: a half-configured auth flow must not start. The
        `auth_disabled` bypass is exempt so local dev and the test suite run without Google creds.
        """
        if self.auth_disabled:
            return self
        missing = [
            name
            for name, value in (
                ("GOOGLE_CLIENT_ID", self.google_client_id),
                ("GOOGLE_CLIENT_SECRET", self.google_client_secret),
                ("SESSION_SECRET", self.session_secret),
            )
            if not value
        ]
        if missing:
            raise ValueError(
                f"Auth is enabled but required settings are missing: {', '.join(missing)}. "
                "Set them, or set AUTH_DISABLED=true for local dev."
            )
        return self


settings = Settings()
