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

    pessoa_resumo = api.model(
        "PessoaResumo",
        {"id": fields.String(description="UUID"), "nome": fields.String(description="Nome")},
    )

    veiculo_resumo = api.model(
        "VeiculoResumo",
        {
            "id": fields.String(description="UUID do veículo"),
            "placa": fields.String(description="Placa"),
            "modelo": fields.String(description="Modelo"),
        },
    )

    rodada_viagem = api.model(
        "RodadaViagem",
        {
            "id": fields.String(description="UUID da viagem"),
            "status": fields.String(enum=["SOLICITADA", "BUFFER_ABERTO", "EM_ANDAMENTO"]),
            "rota_id": fields.String(description="UUID da rota"),
            "created_at": fields.DateTime(description="Momento da primeira solicitação"),
            "inicio_real": fields.DateTime(description="Início do percurso em rota"),
            "buffer_fim": fields.DateTime(description="Fim da janela de buffer, se aberta"),
            "segundos_restantes_buffer": fields.Integer(
                description="Segundos até o fim do buffer pelo relógio do servidor; null fora do buffer"
            ),
            "motorista": fields.Nested(pessoa_resumo, allow_null=True),
            "veiculo": fields.Nested(veiculo_resumo, allow_null=True),
        },
    )

    minha_solicitacao = api.model(
        "MinhaSolicitacao",
        {
            "id": fields.String(description="UUID da solicitação ativa do aluno"),
            "status": fields.String(enum=["ATIVA"]),
        },
    )

    janela_hoje = api.model(
        "JanelaHoje",
        {"hora_inicio": fields.String(example="08:00"), "hora_fim": fields.String(example="12:00")},
    )

    rodada_ativa_response = api.model(
        "RodadaAtivaResponse",
        {
            "viagem": fields.Nested(
                rodada_viagem, allow_null=True, description="null quando o veículo está ocioso"
            ),
            "minha_solicitacao": fields.Nested(
                minha_solicitacao,
                allow_null=True,
                description="Só para aluno com solicitação ativa",
            ),
            "janelas_hoje": fields.List(fields.Nested(janela_hoje)),
        },
    )

    return {
        "solicitacao_viagem_resumo": solicitacao_viagem_resumo,
        "solicitacao_response": solicitacao_response,
        "rodada_ativa_response": rodada_ativa_response,
    }
