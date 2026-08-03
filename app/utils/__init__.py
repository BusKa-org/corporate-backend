"""Utility modules for the application."""

from .logger import AuditLogger, audit_logger, setup_logging, setup_request_id_middleware
from .security import SecurityConfig, check_production_security, setup_security_headers
from .validators import (
    sanitize_string,
    validate_cnh,
    validate_coordinates,
    validate_cpf,
    validate_email,
    validate_pagination,
    validate_password,
    validate_phone,
    validate_uuid,
)

__all__ = [
    # Logging
    "audit_logger",
    "AuditLogger",
    "setup_logging",
    "setup_request_id_middleware",
    # Security
    "SecurityConfig",
    "setup_security_headers",
    "check_production_security",
    # Validators
    "validate_uuid",
    "validate_cpf",
    "validate_email",
    "validate_password",
    "validate_phone",
    "validate_cnh",
    "validate_pagination",
    "validate_coordinates",
    "sanitize_string",
]
