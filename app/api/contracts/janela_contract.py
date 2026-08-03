"""Janela de disponibilidade endpoint documentation models (RF-05)."""

from flask_restx import fields


def register_models(api):
    """Register availability-window models with the API namespace."""

    janela_request = api.model(
        "JanelaRequest",
        {
            "rota_id": fields.String(required=True, description="UUID do circuito"),
            "motorista_id": fields.String(required=True, description="UUID do motorista"),
            "veiculo_id": fields.String(description="UUID do veículo (opcional)"),
            "dia": fields.String(required=True, description="SEG, TER, QUA, QUI, SEX, SAB, DOM"),
            "hora_inicio": fields.String(required=True, description="HH:MM"),
            "hora_fim": fields.String(required=True, description="HH:MM"),
            "buffer_minutos": fields.Integer(description="N minutos do buffer (RF-11)"),
            "ativo": fields.Boolean(description="Janela ativa"),
        },
    )

    janela_response = api.model(
        "JanelaResponse",
        {
            "id": fields.String(description="UUID da janela"),
            "rota_id": fields.String(description="UUID do circuito"),
            "rota_nome": fields.String(description="Nome do circuito"),
            "motorista_id": fields.String(description="UUID do motorista"),
            "motorista_nome": fields.String(description="Nome do motorista"),
            "veiculo_id": fields.String(description="UUID do veículo"),
            "dia": fields.String(description="Dia da semana"),
            "hora_inicio": fields.String(description="Início da operação"),
            "hora_fim": fields.String(description="Fim da operação"),
            "buffer_minutos": fields.Integer(description="N minutos do buffer"),
            "ativo": fields.Boolean(description="Janela ativa"),
        },
    )

    janela_list_response = api.model(
        "JanelaListResponse",
        {
            "items": fields.List(fields.Nested(janela_response)),
            "total": fields.Integer(description="Total de janelas"),
        },
    )

    janela_vigente_response = api.model(
        "JanelaVigenteResponse",
        {
            "em_operacao": fields.Boolean(description="Há janela em vigor agora"),
            "janela": fields.Nested(janela_response, allow_null=True),
            "horarios_hoje": fields.List(fields.Nested(janela_response)),
        },
    )

    message_response = api.model(
        "JanelaMessageResponse",
        {"message": fields.String(description="Mensagem de confirmação")},
    )

    return {
        "janela_request": janela_request,
        "janela_response": janela_response,
        "janela_list_response": janela_list_response,
        "janela_vigente_response": janela_vigente_response,
        "message_response": message_response,
    }
