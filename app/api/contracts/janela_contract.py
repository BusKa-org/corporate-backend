"""Janela de disponibilidade endpoint documentation models (RF-05)."""

from flask_restx import fields


def register_models(api):
    """Register janela models with the API namespace."""

    janela_create_request = api.model(
        "JanelaCreateRequest",
        {
            "motorista_id": fields.String(required=True, description="UUID do motorista"),
            "dia": fields.String(
                required=True,
                enum=["SEG", "TER", "QUA", "QUI", "SEX", "SAB", "DOM"],
                description="Dia da semana",
            ),
            "hora_inicio": fields.String(required=True, description="Início (HH:MM, hora local)"),
            "hora_fim": fields.String(required=True, description="Fim (HH:MM, exclusivo)"),
        },
    )

    janela_response = api.model(
        "JanelaResponse",
        {
            "id": fields.String(description="UUID da janela"),
            "onibus_id": fields.String(description="UUID do ônibus"),
            "motorista_id": fields.String(description="UUID do motorista"),
            "motorista_nome": fields.String(description="Nome do motorista"),
            "dia": fields.String(description="Dia da semana"),
            "hora_inicio": fields.String(description="Início (HH:MM)"),
            "hora_fim": fields.String(description="Fim (HH:MM)"),
            "created_at": fields.DateTime(description="Data de criação"),
        },
    )

    janela_list_response = api.model(
        "JanelaListResponse",
        {
            "items": fields.List(fields.Nested(janela_response)),
            "total": fields.Integer(description="Total de janelas"),
        },
    )

    return {
        "janela_create_request": janela_create_request,
        "janela_response": janela_response,
        "janela_list_response": janela_list_response,
    }
