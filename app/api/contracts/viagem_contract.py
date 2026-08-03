"""Viagem endpoint documentation models."""

from flask_restx import fields


def register_models(api):
    """Register viagem models with the API namespace."""

    viagem_create_request = api.model(
        "ViagemCreateRequest",
        {
            "rota_id": fields.String(required=True, description="UUID da rota"),
            "horario_id": fields.String(required=True, description="UUID do horário"),
            "data": fields.String(required=True, description="Data (YYYY-MM-DD)"),
            "motorista_id": fields.String(description="UUID do motorista (opcional)"),
            "veiculo_id": fields.String(description="UUID do veículo (opcional)"),
        },
    )

    viagem_lote_request = api.model(
        "ViagemLoteRequest",
        {"data": fields.String(required=True, description="Data para gerar viagens (YYYY-MM-DD)")},
    )

    viagem_confirmacao_request = api.model(
        "ViagemConfirmacaoRequest",
        {
            "confirmacao": fields.Boolean(required=True, description="Confirmado"),
            "ponto_embarque_id": fields.String(description="UUID do ponto de embarque (opcional)"),
        },
    )

    viagem_acao_request = api.model(
        "ViagemAcaoRequest",
        {"acao": fields.String(required=True, description="iniciar ou finalizar")},
    )

    localizacao_request = api.model(
        "LocalizacaoRequest",
        {
            "latitude": fields.Float(required=True, description="Latitude atual do ônibus"),
            "longitude": fields.Float(required=True, description="Longitude atual do ônibus"),
        },
    )

    viagem_response = api.model(
        "ViagemResponse",
        {
            "id": fields.String(description="UUID"),
            "data": fields.String(description="Data"),
            "horario_saida": fields.String(description="Horário"),
            "sentido": fields.String(description="Sentido"),
            "status": fields.String(description="AGENDADA, EM_ANDAMENTO, FINALIZADA"),
            "rota_id": fields.String(description="UUID da rota"),
            "rota_nome": fields.String(description="Nome da rota"),
            "motorista_id": fields.String(description="UUID do motorista"),
            "veiculo_id": fields.String(description="UUID do veículo"),
        },
    )

    viagem_aluno_confirmacao_response = api.model(
        "ViagemAlunoConfirmacaoResponse",
        {
            "aluno_id": fields.String(description="UUID do aluno"),
            "nome": fields.String(description="Nome do aluno"),
            "confirmacao": fields.Boolean(description="Confirmado"),
            "ponto_embarque": fields.String(description="UUID do ponto de embarque"),
        },
    )

    viagem_agenda_aluno_response = api.model(
        "ViagemAgendaAlunoResponse",
        {
            "viagem_id": fields.String(description="UUID da viagem"),
            "data": fields.String(description="Data"),
            "dia_semana": fields.String(description="Dia da semana"),
            "horario_saida": fields.String(description="Horário"),
            "sentido": fields.String(description="Sentido"),
            "rota_id": fields.String(description="UUID da rota"),
            "rota_nome": fields.String(description="Nome da rota"),
            "status_confirmacao": fields.Boolean(description="Confirmado"),
            "ponto_embarque_id": fields.String(description="UUID do ponto de embarque"),
        },
    )

    viagem_agenda_aluno_list_response = api.model(
        "ViagemAgendaAlunoListResponse",
        {
            "items": fields.List(fields.Nested(viagem_agenda_aluno_response)),
            "total": fields.Integer(description="Total de viagens"),
        },
    )

    viagem_lote_response = api.model(
        "ViagemLoteResponse",
        {
            "total_rotas_analisadas": fields.Integer(description="Total de rotas analisadas"),
            "viagens_criadas": fields.Integer(description="Total de viagens criadas"),
            "detalhes": fields.List(fields.String(description="Detalhes da viagem")),
        },
    )

    viagem_list_response = api.model(
        "ViagemListResponse",
        {
            "items": fields.List(fields.Nested(viagem_response)),
            "total": fields.Integer(description="Total de viagens"),
        },
    )

    return {
        "viagem_create_request": viagem_create_request,
        "viagem_lote_request": viagem_lote_request,
        "viagem_confirmacao_request": viagem_confirmacao_request,
        "viagem_acao_request": viagem_acao_request,
        "viagem_response": viagem_response,
        "viagem_list_response": viagem_list_response,
        "viagem_aluno_confirmacao_response": viagem_aluno_confirmacao_response,
        "viagem_lote_response": viagem_lote_response,
        "viagem_agenda_aluno_list_response": viagem_agenda_aluno_list_response,
        "viagem_agenda_aluno_response": viagem_agenda_aluno_response,
        "localizacao_request": localizacao_request,
    }
