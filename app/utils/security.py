"""Security utilities and middleware for enhanced application security."""

import logging
from typing import Any

from flask import Flask, Response

logger = logging.getLogger(__name__)


def setup_security_headers(app: Flask) -> None:
    """
    Configure security headers for all HTTP responses.

    Implements best practices for web application security including:
    - Content Security Policy
    - XSS Protection
    - Clickjacking Protection
    - MIME Type Sniffing Protection
    - Strict Transport Security (HSTS)

    Args:
        app: Flask application instance
    """

    @app.after_request
    def add_security_headers(response: Response) -> Response:
        """Add security headers to all responses."""
        # Content Security Policy
        # Note: Adjust as needed for your frontend requirements
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' 'unsafe-eval' https://unpkg.com; "
            "style-src 'self' 'unsafe-inline' https://unpkg.com; "
            "img-src 'self' data: https://tile.openstreetmap.org https:; "
            "font-src 'self' data:; "
            "connect-src 'self' https:; "
            "frame-ancestors 'self'; "
        )

        # Prevent MIME type sniffing
        response.headers["X-Content-Type-Options"] = "nosniff"

        # Enable browser XSS protection
        response.headers["X-XSS-Protection"] = "1; mode=block"

        # Prevent clickjacking
        response.headers["X-Frame-Options"] = "DENY"

        # Referrer policy
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

        # Permissions policy (formerly Feature Policy)
        response.headers["Permissions-Policy"] = (
            "geolocation=(self), microphone=(), camera=(), payment=()"
        )

        # HSTS - force HTTPS (only in production)
        if not app.config.get("DEBUG"):
            response.headers["Strict-Transport-Security"] = (
                "max-age=31536000; includeSubDomains; preload"
            )

        return response

    logger.info("Security headers configured")


def validate_request_size(max_content_length: int = 16 * 1024 * 1024) -> None:
    """
    Configure maximum request size to prevent DoS attacks.

    Args:
        max_content_length: Maximum request size in bytes (default: 16MB)
    """
    # This would be configured on the Flask app
    # app.config["MAX_CONTENT_LENGTH"] = max_content_length
    pass


class SecurityConfig:
    """Security configuration constants and recommendations."""

    # Password requirements
    MIN_PASSWORD_LENGTH = 8
    REQUIRE_SPECIAL_CHAR = False  # Can be enabled for stricter security
    REQUIRE_NUMBER = False  # Can be enabled for stricter security
    REQUIRE_UPPERCASE = False  # Can be enabled for stricter security

    # Session configuration
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SECURE = True  # Requires HTTPS
    SESSION_COOKIE_SAMESITE = "Lax"

    # JWT configuration
    JWT_ACCESS_TOKEN_EXPIRES_HOURS = 2
    JWT_REFRESH_TOKEN_EXPIRES_DAYS = 30

    # Rate limiting
    DEFAULT_RATE_LIMIT = "200 per hour"
    AUTH_RATE_LIMIT = "10 per minute"
    SENSITIVE_RATE_LIMIT = "5 per minute"

    # CORS
    CORS_MAX_AGE = 86400  # 24 hours

    @classmethod
    def get_security_recommendations(cls) -> dict[str, Any]:
        """
        Get security configuration recommendations.

        Returns:
            Dictionary of security recommendations
        """
        return {
            "password_policy": {
                "min_length": cls.MIN_PASSWORD_LENGTH,
                "recommendations": [
                    "Use a password manager",
                    "Avoid common passwords",
                    "Use different passwords for different services",
                ],
            },
            "authentication": {
                "jwt_expiration": f"{cls.JWT_ACCESS_TOKEN_EXPIRES_HOURS} hours",
                "rate_limiting": cls.AUTH_RATE_LIMIT,
                "recommendations": [
                    "Enable 2FA for production",
                    "Implement account lockout after failed attempts",
                    "Monitor for suspicious login patterns",
                ],
            },
            "data_protection": {
                "encryption": "Passwords hashed with werkzeug.security",
                "transport": "HTTPS required in production",
                "recommendations": [
                    "Encrypt sensitive data at rest",
                    "Use environment variables for secrets",
                    "Regular security audits",
                    "Keep dependencies updated",
                ],
            },
            "monitoring": {
                "logging": "Structured JSON logging with request IDs",
                "audit_trail": "All sensitive operations logged",
                "recommendations": [
                    "Set up centralized logging (e.g., ELK stack)",
                    "Configure alerts for security events",
                    "Regular log review",
                    "Incident response plan",
                ],
            },
        }


def check_production_security(app: Flask) -> list[str]:
    """
    Check security configuration for production readiness.

    Args:
        app: Flask application instance

    Returns:
        List of security warnings/issues
    """
    warnings: list[str] = []

    # Check if DEBUG is disabled
    if app.config.get("DEBUG"):
        warnings.append("DEBUG mode is enabled - MUST be disabled in production")

    # Check for strong JWT secret
    jwt_secret = app.config.get("JWT_SECRET_KEY", "")
    if len(jwt_secret) < 32:
        warnings.append("JWT_SECRET_KEY is too short - use at least 32 characters")

    # Check CORS configuration
    cors_origins = app.config.get("CORS_ORIGINS", "*")
    if cors_origins == "*":
        warnings.append("CORS allows all origins - restrict to specific domains in production")

    # Check if HTTPS is enforced
    if not app.config.get("SESSION_COOKIE_SECURE"):
        warnings.append("SESSION_COOKIE_SECURE not set - cookies should require HTTPS")

    return warnings
