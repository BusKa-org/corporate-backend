"""Input validation utilities for enhanced security."""

import re
import uuid
from typing import Any

from app.core.exceptions import ValidationError
from app.utils.security import SecurityConfig


def validate_uuid(value: str, field_name: str = "ID") -> uuid.UUID:
    """
    Validate UUID format.

    Args:
        value: UUID string to validate
        field_name: Name of the field for error messages

    Returns:
        uuid.UUID object

    Raises:
        ValidationError: If the UUID format is invalid
    """
    try:
        return uuid.UUID(value, version=4)
    except (ValueError, AttributeError, TypeError):
        raise ValidationError(f"{field_name} deve ser um UUID válido")


def validate_cpf(cpf: str) -> str:
    """
    Validate Brazilian CPF (Cadastro de Pessoas Físicas).

    Args:
        cpf: CPF string to validate (can include dots and dashes)

    Returns:
        Cleaned CPF string (digits only)

    Raises:
        ValidationError: If CPF format or checksum is invalid
    """
    # Remove formatting characters
    raw_cpf = re.sub(r"[^\d]", "", cpf)

    if len(raw_cpf) != 11:
        raise ValidationError("CPF deve conter 11 dígitos")

    if raw_cpf == raw_cpf[0] * 11:
        raise ValidationError("CPF inválido")

    # Validate checksum digits
    def calculate_digit(cpf_partial: str, weight_start: int) -> int:
        """Calculate CPF checksum digit."""
        total = sum(int(cpf_partial[i]) * (weight_start - i) for i in range(len(cpf_partial)))
        remainder = total % 11
        return 0 if remainder < 2 else 11 - remainder

    first_digit = calculate_digit(raw_cpf[:9], 10)
    if first_digit != int(raw_cpf[9]):
        raise ValidationError("CPF inválido (primeiro dígito verificador)")

    second_digit = calculate_digit(raw_cpf[:10], 11)
    if second_digit != int(raw_cpf[10]):
        raise ValidationError("CPF inválido (segundo dígito verificador)")

    return raw_cpf


def validate_email(email: str) -> str:
    """
    Validate email format.

    Args:
        email: Email string to validate

    Returns:
        Lowercased email string

    Raises:
        ValidationError: If email format is invalid
    """
    email = email.strip().lower()

    pattern = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"

    if not re.match(pattern, email):
        raise ValidationError("Formato de email inválido")

    disposable_domains = [
        "tempmail.com",
        "codgal.com",  # got this from: https://temp-mail.org/en/
        "quantyti.com",  # got this from: https://www.emailondeck.com/
        "virgilian.com",  # got this from: https://internxt.com/temporary-email
        "throwaway.email",
        "guerrillamail.com",
        "10minutemail.com",
    ]

    domain = email.split("@")[1]
    if domain in disposable_domains:
        raise ValidationError("Email de domínio descartável não é permitido")

    return email


def validate_phone(phone: str) -> str:
    """
    Validate Brazilian phone number.

    Args:
        phone: Phone number string (can include formatting)

    Returns:
        Cleaned phone string (digits only)

    Raises:
        ValidationError: If phone format is invalid
    """
    raw_phone = re.sub(r"[^\d]", "", phone)

    if len(raw_phone) not in [10, 11]:
        raise ValidationError("Telefone deve conter 10 ou 11 dígitos (com DDD)")

    area_code = int(raw_phone[:2])
    if area_code < 11 or area_code > 99:
        raise ValidationError("DDD inválido (deve estar entre 11 e 99)")

    return raw_phone


def validate_cnh(cnh: str) -> str:
    """
    Validate Brazilian CNH (driver's license) format.

    Args:
        cnh: CNH string to validate

    Returns:
        Cleaned CNH string (digits only)

    Raises:
        ValidationError: If CNH format is invalid
    """
    raw_cnh = re.sub(r"[^\d]", "", cnh)

    if len(raw_cnh) != 11:
        raise ValidationError("CNH deve conter 11 dígitos")

    if raw_cnh == raw_cnh[0] * 11:
        raise ValidationError("CNH inválida")

    return raw_cnh


def validate_pagination(page: Any, per_page: Any, max_per_page: int = 100) -> tuple[int, int]:
    """
    Validate pagination parameters.

    Args:
        page: Page number
        per_page: Items per page
        max_per_page: Maximum allowed items per page

    Returns:
        Tuple of (page, per_page) as integers

    Raises:
        ValidationError: If pagination parameters are invalid
    """
    try:
        page_int = int(page) if page else 1
        per_page_int = int(per_page) if per_page else 20
    except (ValueError, TypeError):
        raise ValidationError("Parâmetros de paginação devem ser números inteiros")

    if page_int < 1:
        raise ValidationError("Número da página deve ser maior ou igual a 1")

    if per_page_int < 1:
        raise ValidationError("Items por página deve ser maior ou igual a 1")

    if per_page_int > max_per_page:
        raise ValidationError(f"Items por página não pode exceder {max_per_page}")

    return page_int, per_page_int


def validate_coordinates(latitude: float, longitude: float) -> tuple[float, float]:
    """
    Validate geographic coordinates.

    Args:
        latitude: Latitude value
        longitude: Longitude value

    Returns:
        Tuple of (latitude, longitude)

    Raises:
        ValidationError: If coordinates are out of valid range
    """
    try:
        lat = float(latitude)
        lon = float(longitude)
    except (ValueError, TypeError):
        raise ValidationError("Coordenadas devem ser números")

    if not -90 <= lat <= 90:
        raise ValidationError("Latitude deve estar entre -90 e 90")

    if not -180 <= lon <= 180:
        raise ValidationError("Longitude deve estar entre -180 e 180")

    return lat, lon


def validate_password(password: str, field_name: str = "Senha") -> str:
    """
    Validate password meets minimum requirements.

    Args:
        password: Password to validate
        field_name: Field name for error messages (default: "Senha")

    Returns:
        Stripped password string

    Raises:
        ValidationError: If password doesn't meet requirements
    """
    password = password.strip()

    if len(password) < SecurityConfig.MIN_PASSWORD_LENGTH:
        raise ValidationError(
            f"{field_name} deve ter no mínimo {SecurityConfig.MIN_PASSWORD_LENGTH} caracteres"
        )

    return password


def sanitize_string(value: str, max_length: int | None = None) -> str:
    """
    Sanitize string input by removing dangerous characters.

    Args:
        value: String to sanitize
        max_length: Maximum allowed length

    Returns:
        Sanitized string

    Raises:
        ValidationError: If string exceeds max_length
    """
    if not isinstance(value, str):
        raise ValidationError("Valor deve ser uma string")

    sanitized = value.strip()

    # Remove null bytes and other control characters
    sanitized = re.sub(r"[\x00-\x1f\x7f]", "", sanitized)

    if max_length and len(sanitized) > max_length:
        raise ValidationError(f"Texto não pode exceder {max_length} caracteres")

    return sanitized
