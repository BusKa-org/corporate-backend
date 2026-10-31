"""Credencial de embarque endpoint documentation models."""

from flask_restx import fields


def register_models(api):
    """Register credencial_embarque models with the API namespace."""

    credencial_embarque_response = api.model(
        "CredencialEmbarqueResponse",
        {
            "credencial_id": fields.String(description="UUID da credencial, início do QR"),
            "segredo": fields.String(description="Segredo do código TOTP (hex, 32 bytes)"),
            "algoritmo": fields.String(description="HMAC do TOTP (RFC 6238): SHA1"),
            "passo_segundos": fields.Integer(description="O código muda a cada passo"),
            "digitos": fields.Integer(description="Tamanho do código"),
            "ponto_embarque_id": fields.String(description="UUID do ponto de embarque"),
            "expira_em": fields.String(description="Expiração (ISO 8601)"),
            "usado": fields.Boolean(description="Se a credencial já foi usada no embarque"),
        },
    )

    return {
        "credencial_embarque_response": credencial_embarque_response,
    }
