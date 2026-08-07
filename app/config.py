from functools import lru_cache
from zoneinfo import ZoneInfo

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    env: str = Field(default="local", alias="ENV")

    database_url: str = Field(alias="DATABASE_URL")

    secret_key: str = Field(alias="SECRET_KEY")

    cors_origins_raw: str = Field(default="", alias="CORS_ORIGINS")

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.cors_origins_raw.split(",") if o.strip()]

    # Sessions
    traveler_session_ttl_hours: int = Field(default=24 * 30, alias="TRAVELER_SESSION_TTL_HOURS")
    staff_session_ttl_hours: int = Field(default=12, alias="STAFF_SESSION_TTL_HOURS")
    admin_session_ttl_hours: int = Field(default=12, alias="ADMIN_SESSION_TTL_HOURS")

    # Magic link
    magic_link_ttl_minutes: int = Field(default=15, alias="MAGIC_LINK_TTL_MINUTES")

    # Staff PIN lockout
    pin_max_attempts: int = Field(default=5, alias="PIN_MAX_ATTEMPTS")
    pin_lockout_minutes: int = Field(default=15, alias="PIN_LOCKOUT_MINUTES")

    # Booking token / location token
    booking_token_bytes: int = Field(default=32, alias="BOOKING_TOKEN_BYTES")

    # Object storage (Cloudflare R2)
    r2_account_id: str = Field(default="", alias="R2_ACCOUNT_ID")
    r2_access_key_id: str = Field(default="", alias="R2_ACCESS_KEY_ID")
    r2_secret_access_key: str = Field(default="", alias="R2_SECRET_ACCESS_KEY")
    r2_bucket: str = Field(default="", alias="R2_BUCKET")

    # Email (Resend)
    resend_api_key: str = Field(default="", alias="RESEND_API_KEY")
    email_from: str = Field(default="HaiHui <no-reply@haihui.ro>", alias="EMAIL_FROM")
    email_reply_to: str = Field(default="", alias="EMAIL_REPLY_TO")

    # Stripe
    stripe_secret_key: str = Field(default="", alias="STRIPE_SECRET_KEY")
    stripe_webhook_secret: str = Field(default="", alias="STRIPE_WEBHOOK_SECRET")

    # Monitoring
    sentry_dsn: str = Field(default="", alias="SENTRY_DSN")

    # App
    public_base_url: str = Field(default="http://localhost:3000", alias="PUBLIC_BASE_URL")
    timezone_name: str = Field(default="Europe/Bucharest", alias="APP_TIMEZONE")

    @property
    def tz(self) -> ZoneInfo:
        return ZoneInfo(self.timezone_name)

    @property
    def is_production(self) -> bool:
        return self.env == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
