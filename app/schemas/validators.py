"""Input validation utilities for enhanced security."""

# app/schemas/validators.py
import re
import uuid
from typing import Any

from marshmallow import ValidationError as MarshmallowValidationError

from app.utils.security import SecurityConfig


def validate_optional_string(value: str | None, field_name: str = "Texto") -> str | None:
    """
    Validate string.

    Args:
        value: String to validate
        field_name: Name of the field for error messages

    Returns:
        string
    """
    if value is None:
        return None
    if not isinstance(value, str):
        raise MarshmallowValidationError(f"{field_name} deve ser uma string")
    return value


def validate_uuid4(value: str, field_name: str = "ID") -> str:
    """
    Validate UUID4 format.

    Args:
        value: UUID4 string to validate
        field_name: Name of the field for error messages

    Returns:
        string UUID4

    Raises:
        ValidationError: If the UUID4 format is invalid
    """
    try:
        uuid.UUID(value, version=4)
        return value
    except (ValueError, AttributeError, TypeError):
        raise MarshmallowValidationError(f"{field_name} deve ser um UUID4 válido")


def validate_optional_cpf(value: str | None, field_name: str = "CPF") -> str | None:
    """
    Validate Brazilian CPF (Cadastro de Pessoas Físicas).

    Args:
        value: CPF string to validate (can include dots and dashes)
    """
    if not value:
        return None

    return validate_cpf(value, field_name)


def validate_cpf(value: str, field_name: str = "CPF") -> str:
    """
    Validate Brazilian CPF (Cadastro de Pessoas Físicas).

    Args:
        value: CPF string to validate (can include dots and dashes)

    Returns:
        Cleaned CPF string (digits only)

    Raises:
        ValidationError: If CPF format or checksum is invalid
    """
    if not value:
        raise MarshmallowValidationError(f"{field_name} não pode ser vazio")

    # Remove formatting characters
    raw_cpf = re.sub(r"[^\d]", "", value)

    if len(raw_cpf) != 11:
        raise MarshmallowValidationError(f"{field_name} deve conter 11 dígitos")

    if raw_cpf == raw_cpf[0] * 11:
        raise MarshmallowValidationError(f"{field_name} inválido (todos os dígitos são iguais)")

    # Validate checksum digits
    def calculate_digit(cpf_partial: str, weight_start: int) -> int:
        """Calculate CPF checksum digit."""
        total = sum(int(cpf_partial[i]) * (weight_start - i) for i in range(len(cpf_partial)))
        remainder = total % 11
        return 0 if remainder < 2 else 11 - remainder

    first_digit = calculate_digit(raw_cpf[:9], 10)
    if first_digit != int(raw_cpf[9]):
        raise MarshmallowValidationError(f"{field_name} inválido (primeiro dígito verificador)")

    second_digit = calculate_digit(raw_cpf[:10], 11)
    if second_digit != int(raw_cpf[10]):
        raise MarshmallowValidationError(f"{field_name} inválido (segundo dígito verificador)")

    return raw_cpf


def validate_optional_phone(value: str | None, field_name: str = "Telefone") -> str | None:
    """
    Validate Brazilian phone number.

    Args:
        value: Phone number string (can include formatting)

    Returns:
        Cleaned phone string (digits only)

    Raises:
        MarshmallowValidationError: If phone format is invalid
    """
    if not value:
        return None

    return validate_phone(value, field_name)


def validate_phone(value: str, field_name: str = "Telefone") -> str:
    """
    Validate Brazilian phone number.

    Args:
        value: Phone number string (can include formatting)

    Returns:
        Cleaned phone string (digits only)

    Raises:
        MarshmallowValidationError: If phone format is invalid
    """
    raw_phone = re.sub(r"[^\d]", "", value)

    if len(raw_phone) not in [10, 11]:
        raise MarshmallowValidationError(f"{field_name} deve conter 10 ou 11 dígitos (com DDD)")

    area_code = int(raw_phone[:2])
    if area_code < 11 or area_code > 99:
        raise MarshmallowValidationError(f"{field_name} DDD inválido (deve estar entre 11 e 99)")

    return raw_phone


def validate_cnh(value: str, field_name: str = "CNH") -> str:
    """
    Validate Brazilian CNH (driver's license) format.

    Args:
        value: CNH string to validate

    Returns:
        Cleaned CNH string (digits only)

    Raises:
        MarshmallowValidationError: If CNH format is invalid
    """
    raw_cnh = re.sub(r"[^\d]", "", value)

    if len(raw_cnh) != 11:
        raise MarshmallowValidationError(f"{field_name} deve conter 11 dígitos")

    if raw_cnh == raw_cnh[0] * 11:
        raise MarshmallowValidationError(f"{field_name} inválida (todos os dígitos são iguais)")

    return raw_cnh


def validate_pagination(page: Any, per_page: Any, max_per_page: int = 100) -> tuple[int, int]:
    """
    Validate pagination parameters.

    Args:
        page: Page number (default: 1)
        per_page: Items per page
        max_per_page: Maximum allowed items per page

    Returns:
        Tuple of (page, per_page) as integers

    Raises:
        MarshmallowValidationError: If pagination parameters are invalid
    """
    try:
        page_int = int(page) if page else 1
        per_page_int = int(per_page) if per_page else 20
    except (ValueError, TypeError):
        raise MarshmallowValidationError("Parâmetros de paginação devem ser números inteiros")

    if page_int < 1:
        raise MarshmallowValidationError("Número da página deve ser maior ou igual a 1")

    if per_page_int < 1:
        raise MarshmallowValidationError("Items por página deve ser maior ou igual a 1")

    if per_page_int > max_per_page:
        raise MarshmallowValidationError(f"Items por página não pode exceder {max_per_page}")

    return page_int, per_page_int


def validate_coordinates(
    latitude: float, longitude: float, field_name: str = "Coordenadas"
) -> tuple[float, float]:
    """
    Validate geographic coordinates.

    Args:
        latitude: Latitude value (default: 0)
        longitude: Longitude value (default: 0)

    Returns:
        Tuple of (latitude, longitude)

    Raises:
        MarshmallowValidationError: If coordinates are out of valid range
    """
    try:
        lat = float(latitude)
        lon = float(longitude)
    except (ValueError, TypeError):
        raise MarshmallowValidationError(f"{field_name} devem ser números")

    if not -90 <= lat <= 90:
        raise MarshmallowValidationError(f"{field_name} latitude deve estar entre -90 e 90")

    if not -180 <= lon <= 180:
        raise MarshmallowValidationError(f"{field_name} longitude deve estar entre -180 e 180")

    return lat, lon


def validate_password(value: str, field_name: str = "Senha") -> str:
    """
    Validate password meets minimum requirements.

    Args:
        value: Password to validate
        field_name: Field name for error messages (default: "Senha")

    Returns:
        Stripped password string

    Raises:
        MarshmallowValidationError: If password doesn't meet requirements
    """
    value = value.strip()

    if len(value) < SecurityConfig.MIN_PASSWORD_LENGTH:
        raise MarshmallowValidationError(
            f"{field_name} deve ter no mínimo {SecurityConfig.MIN_PASSWORD_LENGTH} caracteres"
        )

    return value


def validate_sanitize_string(
    value: str, max_length: int | None = None, field_name: str = "Texto"
) -> str:
    """
    Sanitize string input by removing dangerous characters.

    Args:
        value: String to sanitize
        max_length: Maximum allowed length (default: None)
        field_name: Field name for error messages (default: "Texto")

    Returns:
        Sanitized string

    Raises:
        MarshmallowValidationError: If string exceeds max_length
    """
    if not isinstance(value, str):
        raise MarshmallowValidationError(f"{field_name} deve ser uma string")

    sanitized = value.strip()

    # Remove null bytes and other control characters
    sanitized = re.sub(r"[\x00-\x1f\x7f]", "", sanitized)

    if max_length and len(sanitized) > max_length:
        raise MarshmallowValidationError(f"{field_name} não pode exceder {max_length} caracteres")

    return sanitized
