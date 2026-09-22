"""Credencial de embarque endpoint documentation models."""

from flask_restx import fields


def register_models(api):
    """Register credencial_embarque models with the API namespace."""

    credencial_embarque_response = api.model(
        "CredencialEmbarqueResponse",
        {
            "token": fields.String(description="Token opaco do QR de embarque"),
            "ponto_embarque_id": fields.String(description="UUID do ponto de embarque"),
            "expira_em": fields.String(description="Expiração (ISO 8601)"),
            "usado": fields.Boolean(description="Se a credencial já foi usada no embarque"),
        },
    )

    return {
        "credencial_embarque_response": credencial_embarque_response,
    }
