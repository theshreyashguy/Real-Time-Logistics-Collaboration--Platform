"""Application configuration loaded from environment / .env."""
from functools import lru_cache

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# The well-known dev placeholder. Allowed in dev/test, rejected in production
# so a deploy can never silently sign tokens with a guessable key.
_INSECURE_JWT_SECRET = "dev-only-change-me"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Deployment environment: development | test | production
    app_env: str = "development"

    # Core
    database_url: str = "postgresql+asyncpg://app:app@localhost:5432/hemut"
    redis_url: str = "redis://localhost:6379/0"

    # Auth
    jwt_secret: str = _INSECURE_JWT_SECRET
    jwt_alg: str = "HS256"
    jwt_access_ttl: int = 900          # seconds (15 min)
    jwt_refresh_ttl: int = 60 * 60 * 24 * 14  # 14 days

    # AI
    ai_model: str = "claude-sonnet-4-6"
    anthropic_api_key: str = ""        # empty -> deterministic extractive fallback
    ai_summary_window_messages: int = 500
    ai_summary_cache_ttl: int = 300    # seconds

    # Realtime / limits
    presence_ttl: int = 30             # seconds
    rate_limit_messages: int = 30      # per window
    rate_limit_window: int = 10        # seconds

    # Misc
    shipment_webhook_url: str = ""     # optional outbound webhook
    cors_origins: str = "http://localhost:3000"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @model_validator(mode="after")
    def _enforce_production_secrets(self) -> "Settings":
        """Fail closed: refuse to boot in production with the dev JWT secret.
        Better a loud startup crash than silently issuing forgeable tokens."""
        if self.app_env == "production" and self.jwt_secret == _INSECURE_JWT_SECRET:
            raise ValueError(
                "JWT_SECRET must be set to a strong, unique value when "
                "APP_ENV=production (the dev placeholder is not allowed)."
            )
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
