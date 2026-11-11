"""Parametros da operação endpoint documentation models."""

from flask_restx import fields


def register_models(api):
    """Register parametros_operacao models with the API namespace."""

    campos = {
        "minimo_alunos": fields.Integer(
            required=True,
            description=(
                "Mínimo de alunos para iniciar o percurso e no fechamento do buffer "
                "(só viagens sob demanda)"
            ),
        ),
        "pausa_entre_viagens_minutos": fields.Integer(
            required=True,
            description=(
                "Pausa mínima do motorista após uma viagem sob demanda, em minutos "
                "(só bloqueia novas viagens sob demanda)"
            ),
        ),
        "antecedencia_motorista_minutos": fields.Integer(
            required=True,
            description=(
                "Antecedência mínima com que o motorista precisa ser avisado, em minutos "
                "(ainda não aplicado; aguardando definição do gestor)"
            ),
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
