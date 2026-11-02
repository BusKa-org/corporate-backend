"""Viagem endpoint documentation models."""

from flask_restx import fields


def register_models(api):
    """Register viagem models with the API namespace."""

    viagem_create_request = api.model(
        "ViagemCreateRequest",
        {
            "rota_id": fields.String(required=True, description="UUID da rota"),
            "data": fields.String(required=True, description="Data (YYYY-MM-DD)"),
        },
    )

    viagem_confirmacao_request = api.model(
        "ViagemConfirmacaoRequest",
        {
            "confirmacao": fields.Boolean(required=True, description="Confirmado"),
            "ponto_embarque_id": fields.String(
                description="UUID do ponto de embarque (obrigatório quando confirmacao=true)"
            ),
        },
    )

    viagem_acao_request = api.model(
        "ViagemAcaoRequest",
        {"acao": fields.String(required=True, description="INICIAR ou FINALIZAR")},
    )

    localizacao_request = api.model(
        "LocalizacaoRequest",
        {
            "latitude": fields.Float(required=True, description="Latitude atual do ônibus"),
            "longitude": fields.Float(required=True, description="Longitude atual do ônibus"),
        },
    )

    viagem_aluno_confirmacao_response = api.model(
        "ViagemAlunoConfirmacaoResponse",
        {
            "aluno_id": fields.String(description="UUID do aluno"),
            "nome": fields.String(description="Nome do aluno"),
            "foto_url": fields.String(description="Caminho da foto (GET autenticado)"),
            "necessidades_acessibilidade": fields.List(fields.String),
            "observacao_acessibilidade": fields.String(),
            "confirmacao": fields.Boolean(description="Confirmado"),
            "ponto_embarque": fields.String(description="Apelido do ponto de embarque"),
            "ponto_destino": fields.String(description="Apelido do ponto de destino"),
        },
    )

    viagem_ponto_response = api.model(
        "ViagemPontoResponse",
        {
            "ponto_id": fields.String(description="UUID do ponto"),
            "apelido": fields.String(description="Apelido do ponto"),
            "ordem": fields.Integer(description="Ordem no roteiro"),
            "visitado": fields.Boolean(description="Ponto já visitado"),
            "chegada_real": fields.DateTime(description="Chegada real ao ponto"),
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
            "origem": fields.String(description="Apelido do primeiro ponto da rota"),
            "destino": fields.String(description="Apelido do último ponto da rota"),
            "pontos": fields.List(fields.Nested(viagem_ponto_response)),
            "alunos": fields.List(fields.Nested(viagem_aluno_confirmacao_response)),
            "total_alunos": fields.Integer(description="Alunos inscritos na rota"),
            "alunos_confirmados_count": fields.Integer(description="Alunos confirmados"),
            "alunos_embarcados_count": fields.Integer(description="Alunos embarcados"),
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
            "alunos_confirmados_count": fields.Integer(description="Alunos confirmados"),
            "total_alunos": fields.Integer(description="Alunos inscritos na rota"),
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

    viagem_cancelar_response = api.model(
        "ViagemCancelarResponse",
        {
            "message": fields.String(description="Mensagem de sucesso"),
            "alunos_notificados": fields.Integer(description="Alunos notificados"),
        },
    )

    localizacao_onibus_response = api.model(
        "LocalizacaoOnibusResponse",
        {
            "latitude": fields.Float(description="Latitude do ônibus"),
            "longitude": fields.Float(description="Longitude do ônibus"),
            "atualizado_em": fields.String(description="Hora do último GPS (ISO 8601)"),
        },
    )

    localizacao_motorista_response = api.model(
        "LocalizacaoMotoristaResponse",
        {
            "message": fields.String(description="Resultado"),
            "distancia_metros": fields.Integer(description="Distância até o próximo ponto"),
        },
    )

    localizacao_aluno_response = api.model(
        "LocalizacaoAlunoResponse",
        {
            "message": fields.String(description="Resultado"),
            "embarcou": fields.Boolean(description="Embarque já registrado"),
        },
    )

    # ----- Declaração de trajeto sob demanda (RF-13) -----

    declaracao_trajeto_request = api.model(
        "DeclaracaoTrajetoRequest",
        {
            "ponto_origem_id": fields.String(
                required=True, description="UUID do ponto de embarque"
            ),
            "ponto_destino_id": fields.String(
                required=True, description="UUID do ponto de desembarque"
            ),
        },
    )

    return {
        "declaracao_trajeto_request": declaracao_trajeto_request,
        "viagem_create_request": viagem_create_request,
        "viagem_confirmacao_request": viagem_confirmacao_request,
        "viagem_acao_request": viagem_acao_request,
        "viagem_response": viagem_response,
        "viagem_list_response": viagem_list_response,
        "viagem_aluno_confirmacao_response": viagem_aluno_confirmacao_response,
        "viagem_agenda_aluno_list_response": viagem_agenda_aluno_list_response,
        "viagem_agenda_aluno_response": viagem_agenda_aluno_response,
        "localizacao_request": localizacao_request,
        "viagem_cancelar_response": viagem_cancelar_response,
        "localizacao_onibus_response": localizacao_onibus_response,
        "localizacao_motorista_response": localizacao_motorista_response,
        "localizacao_aluno_response": localizacao_aluno_response,
    }
