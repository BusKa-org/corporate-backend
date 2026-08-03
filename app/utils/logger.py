"""Structured logging utilities with request ID tracking and audit logging."""

import logging
import sys
import uuid
from datetime import UTC, datetime
from typing import Any

from flask import Flask, g, has_request_context, request
from pythonjsonlogger import jsonlogger


class RequestIdFilter(logging.Filter):
    """Add request ID to log records."""

    def filter(self, record: logging.LogRecord) -> bool:
        """Add request_id to the log record."""
        if has_request_context():
            record.request_id = getattr(g, "request_id", "no-request-id")
            record.method = request.method
            record.path = request.path
            record.remote_addr = request.remote_addr
        else:
            record.request_id = "no-request-id"
            record.method = ""
            record.path = ""
            record.remote_addr = ""
        return True


class CustomJsonFormatter(jsonlogger.JsonFormatter):
    """Custom JSON formatter with additional fields."""

    def add_fields(
        self,
        log_record: dict[str, Any],
        record: logging.LogRecord,
        message_dict: dict[str, Any],
    ) -> None:
        """Add custom fields to log record."""
        super().add_fields(log_record, record, message_dict)

        log_record["timestamp"] = datetime.now(UTC).isoformat() + "Z"
        log_record["level"] = record.levelname
        log_record["logger"] = record.name

        if hasattr(record, "request_id"):
            log_record["request_id"] = record.request_id

        if hasattr(record, "method") and record.method:
            log_record["method"] = record.method

        if hasattr(record, "path") and record.path:
            log_record["path"] = record.path

        if hasattr(record, "remote_addr") and record.remote_addr:
            log_record["remote_addr"] = record.remote_addr


def setup_logging(app: Flask) -> None:
    """
    Configure logging for the application.

    - Development (DEBUG=True): Human-readable colored format
    - Production (DEBUG=False): Structured JSON format

    Args:
        app: Flask application instance
    """
    is_debug = app.config.get("DEBUG", False)
    log_level = logging.DEBUG if is_debug else logging.INFO

    # Choose formatter based on environment
    if is_debug:
        # Human-readable format for development
        formatter = logging.Formatter(
            fmt="%(asctime)s [%(levelname)s] %(name)s [%(request_id)s] %(method)s %(path)s - %(message)s",
            datefmt="%H:%M:%S",
        )
    else:
        # JSON format for production
        formatter = CustomJsonFormatter()

    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)

    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(log_level)
    console_handler.setFormatter(formatter)

    console_handler.addFilter(RequestIdFilter())

    root_logger.addHandler(console_handler)

    app_logger = logging.getLogger("app")
    app_logger.setLevel(log_level)

    # Suppress noisy loggers
    logging.getLogger("werkzeug").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)

    mode = "development (readable)" if is_debug else "production (JSON)"
    app.logger.info(f"Logging configured: {mode}")


def setup_request_id_middleware(app: Flask) -> None:
    """
    Add request ID middleware to track requests across the application.

    Args:
        app: Flask application instance
    """

    @app.before_request
    def add_request_id() -> None:
        """Generate and store request ID for the current request."""
        g.request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))

    @app.after_request
    def add_request_id_header(response):
        """Add request ID to response headers."""
        response.headers["X-Request-ID"] = g.request_id
        return response


class AuditLogger:
    """Audit logger for sensitive operations."""

    def __init__(self, logger_name: str = "app.audit"):
        """Initialize audit logger."""
        self.logger = logging.getLogger(logger_name)

    def log_auth(
        self,
        action: str,
        user_id: str | None = None,
        email: str | None = None,
        success: bool = True,
        details: dict[str, Any] | None = None,
    ) -> None:
        """
        Log authentication events.

        Args:
            action: Action performed (login, logout, register, etc.)
            user_id: User ID if available
            email: User email
            success: Whether the action was successful
            details: Additional details
        """
        extra = {
            "audit_type": "authentication",
            "action": action,
            "user_id": user_id,
            "email": email,
            "success": success,
            "details": details or {},
        }

        if success:
            self.logger.info(f"Auth: {action}", extra=extra)
        else:
            self.logger.warning(f"Auth failed: {action}", extra=extra)

    def log_user_action(
        self,
        action: str,
        user_id: str,
        resource_type: str,
        resource_id: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        """
        Log user actions on resources.

        Args:
            action: Action performed (create, update, delete, etc.)
            user_id: User performing the action
            resource_type: Type of resource (user, rota, viagem, etc.)
            resource_id: ID of the resource
            details: Additional details
        """
        extra = {
            "audit_type": "user_action",
            "action": action,
            "user_id": user_id,
            "resource_type": resource_type,
            "resource_id": resource_id,
            "details": details or {},
        }

        self.logger.info(f"{action.capitalize()} {resource_type}", extra=extra)

    def log_security_event(
        self,
        event_type: str,
        severity: str,
        user_id: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        """
        Log security-related events.

        Args:
            event_type: Type of security event
            severity: Severity level (low, medium, high, critical)
            user_id: User ID if applicable
            details: Additional details
        """
        extra = {
            "audit_type": "security",
            "event_type": event_type,
            "severity": severity,
            "user_id": user_id,
            "details": details or {},
        }

        if severity in ["high", "critical"]:
            self.logger.error(f"Security: {event_type}", extra=extra)
        elif severity == "medium":
            self.logger.warning(f"Security: {event_type}", extra=extra)
        else:
            self.logger.info(f"Security: {event_type}", extra=extra)


# Global audit logger instance
audit_logger = AuditLogger()
