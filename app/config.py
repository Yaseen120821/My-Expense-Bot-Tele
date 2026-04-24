"""
Application configuration loaded from environment variables.
Uses pydantic-settings for validation and type coercion.

Includes:
- Strong typing with defaults
- Startup validation for required secrets
- Sensitive value masking in logs
- Neon PostgreSQL SSL enforcement
"""

import sys
from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central configuration for the Expense Tracker application."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore"
    )

    # --- Telegram Bot ---
    TELEGRAM_BOT_TOKEN: str = Field("", description="Telegram Bot API token from @BotFather")
    WEBHOOK_BASE_URL: str = Field("", description="Public URL for webhook (e.g., https://app.onrender.com)")

    # --- Google Gemini AI ---
    GEMINI_API_KEY: str = Field("", description="Google Gemini API key")
    GEMINI_MODEL: str = Field("gemini-2.0-flash", description="Gemini model name for text + vision")

    # --- Database (Neon PostgreSQL) ---
    DATABASE_URL: str = Field("", description="Synchronous PostgreSQL connection string (Neon)")

    # --- Resend Email API ---
    RESEND_API_KEY: str = Field("", description="Resend API key for email delivery")
    EMAIL_FROM: str = Field("", description="Verified sender email address (Resend)")

    # --- Scheduling ---
    REPORT_TIMEZONE: str = Field("Asia/Kolkata", description="Timezone for scheduled reports")
    DAILY_REPORT_HOUR: int = Field(21, description="Hour (0-23) to send daily report")
    WEEKLY_REPORT_DAY: str = Field("sun", description="Day of week for weekly report")
    WEEKLY_REPORT_HOUR: int = Field(9, description="Hour for weekly report")
    MONTHLY_REPORT_HOUR: int = Field(9, description="Hour for monthly report")

    # --- Application ---
    LOG_LEVEL: str = Field("INFO", description="Logging level")
    APP_ENV: str = Field("development", description="Runtime environment (development/production)")

    # -----------------------------------------------------------------------
    # Computed properties
    # -----------------------------------------------------------------------

    @property
    def is_production(self) -> bool:
        return self.APP_ENV.lower() == "production"

    @property
    def telegram_api_base(self) -> str:
        return f"https://api.telegram.org/bot{self.TELEGRAM_BOT_TOKEN}"

    @property
    def webhook_url(self) -> str:
        return f"{self.WEBHOOK_BASE_URL}/webhook"

    # Backward-compat alias
    @property
    def ENVIRONMENT(self) -> str:
        return self.APP_ENV

    # -----------------------------------------------------------------------
    # Validation
    # -----------------------------------------------------------------------

    def validate_required(self) -> list[str]:
        """
        Check that all required secrets are set (non-empty).
        Returns a list of missing variable names.
        """
        required = {
            "TELEGRAM_BOT_TOKEN": self.TELEGRAM_BOT_TOKEN,
            "GEMINI_API_KEY": self.GEMINI_API_KEY,
            "DATABASE_URL": self.DATABASE_URL,
        }
        return [name for name, value in required.items() if not value.strip()]

    def validate_database_url(self) -> None:
        """Ensure DATABASE_URL uses the psycopg driver and SSL for Neon."""
        url = self.DATABASE_URL
        if not url:
            return

        if not url.startswith("postgresql+psycopg://"):
            raise ValueError(
                f"DATABASE_URL must start with 'postgresql+psycopg://'. "
                f"Got: {self._mask(url)}"
            )

        if "sslmode=require" not in url and "sslmode=verify" not in url:
            raise ValueError(
                "DATABASE_URL must include '?sslmode=require' for Neon PostgreSQL. "
                "Append it to your connection string."
            )

    # -----------------------------------------------------------------------
    # Logging helpers
    # -----------------------------------------------------------------------

    @staticmethod
    def _mask(value: str, visible: int = 6) -> str:
        """Mask a sensitive string, showing only the first few chars."""
        if not value or len(value) <= visible:
            return "***"
        return value[:visible] + "***"

    def log_config_summary(self) -> str:
        """Return a safe-to-log summary of the current configuration."""
        lines = [
            "┌─── Configuration Summary ───",
            f"│ APP_ENV          : {self.APP_ENV}",
            f"│ TELEGRAM_TOKEN   : {self._mask(self.TELEGRAM_BOT_TOKEN)}",
            f"│ GEMINI_API_KEY   : {self._mask(self.GEMINI_API_KEY)}",
            f"│ DATABASE_URL     : {self._mask(self.DATABASE_URL, 30)}",
            f"│ WEBHOOK_BASE_URL : {self.WEBHOOK_BASE_URL or '(not set)'}",
            f"│ RESEND_API_KEY   : {self._mask(self.RESEND_API_KEY)}",
            f"│ EMAIL_FROM       : {self.EMAIL_FROM or '(not set)'}",
            f"│ REPORT_TIMEZONE  : {self.REPORT_TIMEZONE}",
            f"│ DAILY_REPORT_HOUR: {self.DAILY_REPORT_HOUR}",
            f"│ LOG_LEVEL        : {self.LOG_LEVEL}",
            "└─────────────────────────────",
        ]
        return "\n".join(lines)


@lru_cache()
def get_settings() -> Settings:
    """Return cached settings singleton."""
    return Settings()


def validate_settings_on_startup() -> Settings:
    """
    Load, validate, and return settings.
    Prints clear errors and exits if required variables are missing.
    Call this during app startup (lifespan).
    """
    settings = get_settings()

    # 1. Check required secrets
    missing = settings.validate_required()
    if missing:
        print("\n" + "=" * 60, file=sys.stderr)
        print("❌ STARTUP FAILED — Missing required environment variables:", file=sys.stderr)
        for name in missing:
            print(f"   • {name}", file=sys.stderr)
        print("\nSet them in your .env file or in the Render dashboard.", file=sys.stderr)
        print("See .env.example for reference.", file=sys.stderr)
        print("=" * 60 + "\n", file=sys.stderr)
        raise SystemExit(1)

    # 2. Validate DATABASE_URL format
    try:
        settings.validate_database_url()
    except ValueError as e:
        print(f"\n❌ STARTUP FAILED — {e}", file=sys.stderr)
        raise SystemExit(1)

    return settings
