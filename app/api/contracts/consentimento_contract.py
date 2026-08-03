"""Consent / data-subject endpoint documentation models (RF-09, RF-20)."""

from flask_restx import fields


def register_models(api):
    """Register consent models with the API namespace."""

    consentimento_status_response = api.model(
        "ConsentimentoStatusResponse",
        {
            "versao_termo": fields.String(description="Versão vigente do termo"),
            "aceito": fields.Boolean(description="Há aceite válido para a versão vigente"),
            "aceito_em": fields.DateTime(description="Data/hora do aceite vigente"),
        },
    )

    consentimento_response = api.model(
        "ConsentimentoResponse",
        {
            "id": fields.String(description="UUID do registro de consentimento"),
            "versao_termo": fields.String(description="Versão aceita"),
            "aceito_em": fields.DateTime(description="Data/hora do aceite"),
        },
    )

    exclusao_conta_request = api.model(
        "ExclusaoContaRequest",
        {
            "email": fields.String(required=True, description="E-mail do próprio titular"),
            "password": fields.String(required=True, description="Senha do próprio titular"),
        },
    )

    message_response = api.model(
        "ConsentimentoMessageResponse",
        {"message": fields.String(description="Mensagem de confirmação")},
    )

    return {
        "consentimento_status_response": consentimento_status_response,
        "consentimento_response": consentimento_response,
        "exclusao_conta_request": exclusao_conta_request,
        "message_response": message_response,
    }
