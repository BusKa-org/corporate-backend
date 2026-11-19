"""Projeto endpoint documentation models."""

from flask_restx import fields


def register_models(api):
    """Register projeto models with the API namespace."""

    projeto_create_request = api.model(
        "ProjetoCreateRequest",
        {
            "nome": fields.String(
                required=True,
                min_length=1,
                max_length=100,
                description="Nome do projeto, único na organização (sem diferenciar maiúsculas)",
            ),
        },
    )

    projeto_update_request = api.model(
        "ProjetoUpdateRequest",
        {
            "nome": fields.String(min_length=1, max_length=100, description="Novo nome"),
            "ativo": fields.Boolean(description="false desativa, true reativa"),
        },
    )

    projeto_response = api.model(
        "ProjetoResponse",
        {
            "id": fields.String(description="UUID"),
            "nome": fields.String(description="Nome"),
            "ativo": fields.Boolean(description="Projeto ativo"),
            "created_at": fields.DateTime(description="Data de criação"),
        },
    )

    projeto_list_response = api.model(
        "ProjetoListResponse",
        {
            "items": fields.List(fields.Nested(projeto_response)),
            "total": fields.Integer(description="Total de projetos"),
        },
    )

    return {
        "projeto_create_request": projeto_create_request,
        "projeto_update_request": projeto_update_request,
        "projeto_response": projeto_response,
        "projeto_list_response": projeto_list_response,
    }
