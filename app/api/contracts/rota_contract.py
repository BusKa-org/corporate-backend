"""Rota endpoint documentation models."""

from flask_restx import fields

from app.api.contracts.ponto_contract import register_models as register_ponto_models


def register_models(api):
    """Register rota models with the API namespace."""

    ponto_models = register_ponto_models(api)
    ponto_flat_response = ponto_models["ponto_flat_response"]

    rota_horario_create_request = api.model(
        "RotaHorarioCreateRequest",
        {
            "horario_saida": fields.String(required=True, description="Horário (HH:MM)"),
            "sentido": fields.String(required=True, description="IDA, VOLTA ou CIRCULAR"),
            "dias": fields.List(
                fields.String, required=True, description="Dias da semana (SEG, TER, ...)"
            ),
        },
    )

    rota_ponto_add_request = api.model(
        "RotaPontoAddRequest",
        {
            "ponto_id": fields.String(required=True, description="UUID do ponto"),
            "ordem": fields.Integer(required=True, description="Ordem na rota"),
        },
    )

    rota_pontos_add_request = api.model(
        "RotaPontosAddRequest",
        {
            "pontos": fields.List(
                fields.Nested(rota_ponto_add_request), description="Pontos da rota"
            ),
        },
    )

    rota_create_request = api.model(
        "RotaCreateRequest",
        {
            "nome": fields.String(required=True, description="Nome da rota"),
            "motorista_padrao_id": fields.String(description="UUID do motorista padrão"),
            "veiculo_padrao_id": fields.String(description="UUID do veículo padrão"),
            "pontos": fields.List(
                fields.Nested(rota_ponto_add_request), description="Pontos da rota"
            ),
            "horarios": fields.List(
                fields.Nested(rota_horario_create_request), description="Grade de horários"
            ),
        },
    )

    rota_update_request = api.model(
        "RotaUpdateRequest",
        {
            "nome": fields.String(required=True, description="Nome da rota"),
            "motorista_padrao_id": fields.String(description="UUID do motorista padrão"),
            "veiculo_padrao_id": fields.String(description="UUID do veículo padrão"),
            "pontos": fields.List(
                fields.Nested(rota_ponto_add_request), description="Pontos da rota"
            ),
            "horarios": fields.List(
                fields.Nested(rota_horario_create_request), description="Grade de horários"
            ),
        },
    )

    rota_response = api.model(
        "RotaResponse",
        {
            "id": fields.String(description="UUID"),
            "nome": fields.String(description="Nome"),
            "motorista_id": fields.String(description="UUID do motorista padrão"),
            "veiculo_id": fields.String(description="UUID do veículo padrão"),
            "prefeitura_id": fields.String(description="UUID da prefeitura"),
            "municipio_nome": fields.String(description="Nome do município"),
            "municipio_uf": fields.String(description="UF do município"),
        },
    )

    rota_list_response = api.model(
        "RotaListResponse",
        {
            "items": fields.List(fields.Nested(rota_response)),
            "total": fields.Integer(description="Total de rotas"),
        },
    )

    rota_inscricao_request = api.model(
        "RotaInscricaoRequest",
        {"acao": fields.String(required=True, description="inscrever ou desinscrever")},
    )

    rota_horario_response = api.model(
        "RotaHorarioResponse",
        {
            "id": fields.String(description="UUID"),
            "horario_saida": fields.String(description="Horário"),
            "sentido": fields.String(description="Sentido"),
            "dias": fields.List(fields.String, description="Dias"),
        },
    )

    rota_horario_list_response = api.model(
        "RotaHorarioListResponse",
        {
            "items": fields.List(fields.Nested(rota_horario_response)),
            "total": fields.Integer(description="Total de horários"),
        },
    )

    rota_ponto_list_response = api.model(
        "RotaPontoListResponse",
        {
            "items": fields.List(fields.Nested(ponto_flat_response)),
            "total": fields.Integer(description="Total de pontos"),
        },
    )

    rota_detail_response = api.model(
        "RotaDetailResponse",
        {
            **rota_response,
            "pontos": fields.List(fields.Nested(ponto_flat_response)),
            "horarios": fields.List(fields.Nested(rota_horario_response)),
        },
    )

    return {
        "rota_create_request": rota_create_request,
        "rota_response": rota_response,
        "rota_update_request": rota_update_request,
        "rota_inscricao_request": rota_inscricao_request,
        "rota_horario_create_request": rota_horario_create_request,
        "rota_horario_response": rota_horario_response,
        "rota_horario_list_response": rota_horario_list_response,
        "rota_ponto_add_request": rota_ponto_add_request,
        "rota_ponto_list_response": rota_ponto_list_response,
        "rota_pontos_add_request": rota_pontos_add_request,
        "rota_list_response": rota_list_response,
        "rota_detail_response": rota_detail_response,
    }
