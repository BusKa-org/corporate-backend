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
            "horario_inicio": fields.String(
                description="Horário de saída (HH:MM:SS); null em viagem sob demanda"
            ),
            "tipo": fields.String(description="Sentido (IDA/VOLTA); null em viagem sob demanda"),
            "status": fields.String(
                description="AGENDADA, SOLICITADA, BUFFER_ABERTO, EM_ANDAMENTO, FINALIZADA, CANCELADA"
            ),
            "rota_id": fields.String(description="UUID da rota"),
            "rota_nome": fields.String(description="Nome da rota"),
            "inicio_real": fields.DateTime(description="Início real da viagem"),
            "horario_fim": fields.DateTime(description="Fim real da viagem"),
            "buffer_fim": fields.DateTime(
                description="Fim do buffer de embarque (sob demanda, BUFFER_ABERTO)"
            ),
            "motorista_nome": fields.String(description="Nome do motorista"),
            "veiculo_placa": fields.String(description="Placa do veículo"),
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
            "horario_saida": fields.String(description="Horário; null em viagem sob demanda"),
            "sentido": fields.String(description="Sentido; null em viagem sob demanda"),
            "rota_id": fields.String(description="UUID da rota"),
            "rota_nome": fields.String(description="Nome da rota"),
            "status_viagem": fields.String(description="Status da viagem"),
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

    viagem_list_response = api.model(
        "ViagemListResponse",
        {
            "items": fields.List(fields.Nested(viagem_response)),
            "total": fields.Integer(description="Total de viagens"),
        },
    )

    return {
        "viagem_create_request": viagem_create_request,
        "viagem_confirmacao_request": viagem_confirmacao_request,
        "viagem_acao_request": viagem_acao_request,
        "viagem_response": viagem_response,
        "viagem_list_response": viagem_list_response,
        "viagem_aluno_confirmacao_response": viagem_aluno_confirmacao_response,
        "viagem_agenda_aluno_list_response": viagem_agenda_aluno_list_response,
        "viagem_agenda_aluno_response": viagem_agenda_aluno_response,
        "localizacao_request": localizacao_request,
    }
