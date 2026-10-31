"""Solicitação de viagem sob demanda endpoint documentation models."""

from flask_restx import fields


def register_models(api):
    """Register solicitação models with the API namespace."""

    solicitacao_viagem_resumo = api.model(
        "SolicitacaoViagemResumo",
        {
            "id": fields.String(description="UUID da viagem"),
            "status": fields.String(
                description="Status da viagem",
                enum=["SOLICITADA", "BUFFER_ABERTO", "EM_ANDAMENTO", "FINALIZADA", "CANCELADA"],
            ),
            "rota_id": fields.String(description="UUID da rota"),
            "motorista_id": fields.String(description="UUID do motorista da janela"),
            "buffer_fim": fields.DateTime(description="Fim da janela de buffer, se aberta"),
        },
    )

    solicitacao_response = api.model(
        "SolicitacaoResponse",
        {
            "id": fields.String(description="UUID da solicitação"),
            "viagem_id": fields.String(description="UUID da viagem"),
            "status": fields.String(
                description="Status da solicitação", enum=["ATIVA", "CANCELADA", "DESISTENCIA"]
            ),
            "created_at": fields.DateTime(description="Momento da solicitação"),
            "viagem": fields.Nested(solicitacao_viagem_resumo),
        },
    )

    return {
        "solicitacao_viagem_resumo": solicitacao_viagem_resumo,
        "solicitacao_response": solicitacao_response,
    }
