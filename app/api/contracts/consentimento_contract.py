"""Consentimento endpoint documentation models."""

from flask_restx import fields


def register_models(api):
    """Register consentimento models with the API namespace."""

    aceite_request = api.model(
        "AceiteConsentimentoRequest",
        {"versao": fields.String(required=True, description="Versão vigente do termo aceita")},
    )

    consentimento_estado_response = api.model(
        "ConsentimentoEstadoResponse",
        {
            "versao_vigente": fields.String(description="Versão vigente do termo"),
            "pendente": fields.Boolean(description="true quando o usuário ainda precisa aceitar"),
        },
    )

    return {
        "aceite_request": aceite_request,
        "consentimento_estado_response": consentimento_estado_response,
    }
