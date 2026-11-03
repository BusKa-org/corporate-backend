import logging
import os
import re
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from limits import parse_many

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

        # Mail settings (optional - used for password reset and invitation e-mails)
        self.MAIL_SERVER = os.getenv("MAIL_SERVER", "")
        self.MAIL_PORT = self._get_int("MAIL_PORT", default=587, min_val=1, max_val=65535)
        self.MAIL_USERNAME = os.getenv("MAIL_USERNAME", "")
        self.MAIL_PASSWORD = os.getenv("MAIL_PASSWORD", "")
        self.MAIL_USE_TLS = os.getenv("MAIL_USE_TLS", "true").lower() == "true"

        # Frontend URL (used for links in invitation and password reset e-mails).
        # Required in production: an empty value would build relative, broken links.
        self.FRONTEND_URL = self._get_required("FRONTEND_URL", default="http://localhost:8081")

        # App download link, included in the invite e-mail (optional)
        self.APP_DOWNLOAD_URL = os.getenv("APP_DOWNLOAD_URL", "")

        # Organization time zone: local time of the availability windows (RF-05) and of
        # the driver's working hours.
        self.TIMEZONE = os.getenv("TIMEZONE", "America/Sao_Paulo")
        try:
            ZoneInfo(self.TIMEZONE)
        except (ZoneInfoNotFoundError, ValueError):
            self._errors.append(f"TIMEZONE is not a valid IANA timezone: '{self.TIMEZONE}'")
            self.TIMEZONE = "UTC"

        # Intervals of the on-demand trip jobs: close expired buffers and alert the
        # manager when the driver misses the start deadline (RF-11)
        self.JOB_BUFFER_INTERVALO_SEGUNDOS = self._get_int(
            "JOB_BUFFER_INTERVALO_SEGUNDOS", default=30, min_val=5, max_val=3600
        )
        self.JOB_PRAZO_INICIO_INTERVALO_SEGUNDOS = self._get_int(
            "JOB_PRAZO_INICIO_INTERVALO_SEGUNDOS", default=60, min_val=5, max_val=3600
        )

        # On-demand routes (RF-11): buffer length and driver start deadline, in minutes.
        # The default applies when the manager creates the route without a value.
        self.ROTA_BUFFER_MINUTOS_MAX = self._get_int(
            "ROTA_BUFFER_MINUTOS_MAX", default=30, min_val=1, max_val=1440
        )
        self.ROTA_BUFFER_MINUTOS_PADRAO = self._get_int(
            "ROTA_BUFFER_MINUTOS_PADRAO", default=5, min_val=1, max_val=self.ROTA_BUFFER_MINUTOS_MAX
        )
        self.ROTA_PRAZO_INICIO_MINUTOS_MAX = self._get_int(
            "ROTA_PRAZO_INICIO_MINUTOS_MAX", default=120, min_val=1, max_val=1440
        )
        self.ROTA_PRAZO_INICIO_MINUTOS_PADRAO = self._get_int(
            "ROTA_PRAZO_INICIO_MINUTOS_PADRAO",
            default=10,
            min_val=1,
            max_val=self.ROTA_PRAZO_INICIO_MINUTOS_MAX,
        )

        # Driver working hours. CTB (Law 9.503/97) art. 67-C §1-A, added by Law
        # 13.103/2015: in passenger transport, 30 min rest every 4 h of driving (may be split).
        self.MOTORISTA_HORAS_MAX_DIRECAO = self._get_int(
            "MOTORISTA_HORAS_MAX_DIRECAO", default=4, min_val=1, max_val=24
        )
        self.MOTORISTA_DESCANSO_MINUTOS = self._get_int(
            "MOTORISTA_DESCANSO_MINUTOS", default=30, min_val=1, max_val=1440
        )
        # Student photos (RF-15/RF-17). Empty = <instance_path>/fotos_aluno.
        self.FOTOS_ALUNO_DIR = os.getenv("FOTOS_ALUNO_DIR", "")
        self.FOTO_ALUNO_MAX_BYTES = self._get_int(
            "FOTO_ALUNO_MAX_BYTES", default=5 * 1024 * 1024, min_val=1024
        )
        # Width x height. 25 MP covers phone photos and blocks images small in bytes
        # that take gigabytes of memory once opened (decompression bomb).
        self.FOTO_ALUNO_MAX_PIXELS = self._get_int(
            "FOTO_ALUNO_MAX_PIXELS", default=25_000_000, min_val=1
        )

        # Dynamic boarding QR (RF-15): TOTP code (RFC 6238) that changes every step.
        # The window accepts up to N steps before or after the server clock.
        self.QR_PASSO_SEGUNDOS = self._get_int(
            "QR_PASSO_SEGUNDOS", default=30, min_val=5, max_val=300
        )
        self.QR_DIGITOS = self._get_int("QR_DIGITOS", default=6, min_val=6, max_val=8)
        self.QR_JANELA_PASSOS = self._get_int("QR_JANELA_PASSOS", default=1, min_val=0, max_val=10)
        # Offline queue (RF-18): how far ahead the driver app's clock may be.
        self.SYNC_TOLERANCIA_SEGUNDOS = self._get_int(
            "SYNC_TOLERANCIA_SEGUNDOS", default=120, min_val=0, max_val=3600
        )

        # Invite PIN: errors summed across all PINs before the PIN is locked.
        self.CONVITE_PIN_MAX_ERROS_TOTAL = self._get_int(
            "CONVITE_PIN_MAX_ERROS_TOTAL", default=20, min_val=5, max_val=1000
        )
        # Minutes the PIN stays locked after that limit; errors reset when it ends.
        self.CONVITE_PIN_BLOQUEIO_MINUTOS = self._get_int(
            "CONVITE_PIN_BLOQUEIO_MINUTOS", default=60, min_val=1, max_val=1440
        )

        # Rate limit (Flask-Limiter). Limit format: "10 per minute", "2000 per hour".
        self.RATELIMIT_ENABLED = os.getenv("RATELIMIT_ENABLED", "true").lower() == "true"
        # memory:// counts separately in each gunicorn worker; production uses Redis.
        self.RATELIMIT_STORAGE_URI = os.getenv("RATELIMIT_STORAGE_URI", "memory://")
        self.RATELIMIT_DEFAULT = self._get_rate_limit("RATELIMIT_DEFAULT", "2000 per hour")
        self.RATELIMIT_AUTH = self._get_rate_limit("RATELIMIT_AUTH", "10 per minute")
        self.RATELIMIT_SENSITIVE = self._get_rate_limit("RATELIMIT_SENSITIVE", "5 per minute")
        # GPS, telemetry and boarding send many requests in a row from the same user.
        self.RATELIMIT_REALTIME = self._get_rate_limit("RATELIMIT_REALTIME", "120 per minute")
        if (
            not self.DEBUG
            and self.RATELIMIT_ENABLED
            and self.RATELIMIT_STORAGE_URI.startswith("memory://")
        ):
            self._errors.append(
                "RATELIMIT_STORAGE_URI cannot be memory:// in production "
                "(each gunicorn worker would count separately); use redis://"
            )

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
        """Get a required string value.

        Outside production, an unset or empty value falls back to the default.
        """
        value = os.getenv(key, "")
        if value:
            return value
        if self.DEBUG and default:
            return default
        self._errors.append(f"{key} is required")
        return ""

    def _get_int(
        self, key: str, default: int, min_val: int | None = None, max_val: int | None = None
    ) -> int:
        """Get an integer value with optional range validation."""
        # The fallback stays in range: max_val can come from another setting
        # (e.g. ROTA_BUFFER_MINUTOS_MAX=3 with the default PADRAO of 5).
        fallback = default
        if max_val is not None and fallback > max_val:
            fallback = max_val
        if min_val is not None and fallback < min_val:
            fallback = min_val

        raw = os.getenv(key, str(default))
        try:
            value = int(raw)
        except ValueError:
            self._errors.append(f"{key} must be an integer, got '{raw}'")
            return fallback

        if min_val is not None and value < min_val:
            self._errors.append(f"{key} must be >= {min_val}, got {value}")
            return fallback
        if max_val is not None and value > max_val:
            self._errors.append(f"{key} must be <= {max_val}, got {value}")
            return fallback

        return value

    def _get_rate_limit(self, key: str, default: str) -> str:
        """Get a rate limit string such as "10 per minute"."""
        value = os.getenv(key, default)
        try:
            parse_many(value)
        except ValueError:
            self._errors.append(f"{key} is not a valid rate limit, got '{value}'")
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
