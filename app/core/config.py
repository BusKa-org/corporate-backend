import logging
import os
import re

logger = logging.getLogger(__name__)


class ConfigurationError(Exception):
    """Raised when required configuration is missing or invalid."""

    pass


class Settings:
    """Application configuration with validation.

    In development mode, uses permissive defaults.
    In production mode, enforces strict validation.
    """

    # Weak secrets that should never be used in production
    WEAK_SECRETS = {"change-me", "secret", "password", "123456", ""}

    def __init__(self):
        self._errors: list[str] = []

        # Environment
        self.ENV = os.getenv("FLASK_ENV", "development")
        self.DEBUG = self.ENV == "development"
        self.FIREBASE_CREDENTIALS: str | None = os.getenv("FIREBASE_CREDENTIALS")

        # Database settings
        self.DB_USER = self._get_required("DB_USER", default="buska_user")
        self.DB_PASSWORD = self._get_required("DB_PASSWORD", default="buska_pass")
        self.DB_HOST = self._get_required("DB_HOST", default="localhost")
        self.DB_PORT = self._get_int("DB_PORT", default=5432, min_val=1, max_val=65535)
        self.DB_NAME = self._get_required("DB_NAME", default="buska_db")

        # JWT settings
        self.JWT_SECRET_KEY = self._get_secret("JWT_SECRET_KEY", default="change-me")
        self.JWT_EXPIRES_HOURS = self._get_int(
            "JWT_EXPIRES_HOURS", default=2, min_val=1, max_val=720
        )

        # Mail settings (optional - used for forgot password and guardian consent)
        self.MAIL_SERVER = os.getenv("MAIL_SERVER", "")
        self.MAIL_PORT = self._get_int("MAIL_PORT", default=587, min_val=1, max_val=65535)
        self.MAIL_USERNAME = os.getenv("MAIL_USERNAME", "")
        self.MAIL_PASSWORD = os.getenv("MAIL_PASSWORD", "")
        self.MAIL_USE_TLS = os.getenv("MAIL_USE_TLS", "true").lower() == "true"

        # Frontend URL (used for guardian consent email links)
        self.FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:8081")

        # CORS settings
        self.CORS_ORIGINS = self._parse_cors_origins()

        # Database URI (built after validation)
        self.SQLALCHEMY_DATABASE_URI = (
            f"postgresql+psycopg2://{self.DB_USER}:{self.DB_PASSWORD}@"
            f"{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"
        )

        # Validate and fail fast
        self._validate()

    def _get_required(self, key: str, default: str | None = None) -> str:
        """Get a required string value."""
        value = os.getenv(key, default if self.DEBUG else None)
        if not value:
            self._errors.append(f"{key} is required")
            return ""
        return value

    def _get_int(
        self, key: str, default: int, min_val: int | None = None, max_val: int | None = None
    ) -> int:
        """Get an integer value with optional range validation."""
        raw = os.getenv(key, str(default))
        try:
            value = int(raw)
        except ValueError:
            self._errors.append(f"{key} must be an integer, got '{raw}'")
            return default

        if min_val is not None and value < min_val:
            self._errors.append(f"{key} must be >= {min_val}, got {value}")
            return default
        if max_val is not None and value > max_val:
            self._errors.append(f"{key} must be <= {max_val}, got {value}")
            return default

        return value

    def _get_secret(self, key: str, default: str, min_length: int = 16) -> str:
        """Get a secret value with strength validation in production."""
        value = os.getenv(key, default if self.DEBUG else None)

        if not value:
            self._errors.append(f"{key} is required in production")
            return ""

        if self.DEBUG:
            # Warn but don't fail in development
            if value in self.WEAK_SECRETS or len(value) < min_length:
                logger.warning(f"{key} is weak. Use a secure random string in production!")
            return value

        # Strict validation in production
        if value in self.WEAK_SECRETS:
            self._errors.append(f"{key} cannot be a weak/default value in production")
        elif len(value) < min_length:
            self._errors.append(f"{key} must be at least {min_length} characters in production")

        return value

    def _parse_cors_origins(self) -> list[str] | str:
        """Parse CORS_ORIGINS from comma-separated string."""
        raw = os.getenv("CORS_ORIGINS", "")

        if raw:
            origins = [o.strip() for o in raw.split(",") if o.strip()]
            # Validate URLs
            for origin in origins:
                if not re.match(r"^https?://", origin):
                    self._errors.append(
                        f"CORS_ORIGINS contains invalid URL: '{origin}' (must start with http:// or https://)"
                    )
            return origins

        if self.DEBUG:
            return "*"  # Allow all in development

        logger.warning("CORS_ORIGINS not set in production. No cross-origin requests allowed.")
        return []

    def _validate(self) -> None:
        """Validate configuration and fail fast if errors exist."""
        if not self._errors:
            return

        error_msg = "Configuration errors:\n" + "\n".join(f"  - {e}" for e in self._errors)

        if self.DEBUG:
            # Log errors but don't crash in development
            logger.error(error_msg)
        else:
            # Fail fast in production
            raise ConfigurationError(error_msg)
