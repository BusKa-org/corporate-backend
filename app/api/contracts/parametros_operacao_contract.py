"""Parametros da operação endpoint documentation models."""

from flask_restx import fields


def register_models(api):
    """Register parametros_operacao models with the API namespace."""

    campos = {
        "minimo_alunos": fields.Integer(
            required=True, description="Mínimo de alunos solicitantes para iniciar o percurso"
        ),
        "pausa_entre_viagens_minutos": fields.Integer(
            required=True, description="Pausa mínima do motorista entre duas viagens, em minutos"
        ),
        "antecedencia_motorista_minutos": fields.Integer(
            required=True,
            description="Antecedência mínima com que o motorista precisa ser avisado, em minutos",
        ),
    }

    parametros_request = api.model("ParametrosOperacaoRequest", campos)

    parametros_response = api.model(
        "ParametrosOperacaoResponse",
        {
            "organizacao_id": fields.String(),
            **campos,
            "updated_at": fields.DateTime(
                description="Última alteração; null enquanto valem os padrões"
            ),
        },
    )

    return {
        "parametros_request": parametros_request,
        "parametros_response": parametros_response,
    }
