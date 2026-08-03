"""Instituicao endpoint documentation models."""

from flask_restx import fields


def register_models(api):
    """Register instituicao models with the API namespace."""

    instituicao_endereco_input = api.model(
        "InstituicaoEnderecoInput",
        {
            "rua": fields.String(description="Nome da rua"),
            "numero": fields.String(description="Número"),
            "bairro": fields.String(description="Bairro"),
            "cidade": fields.String(description="Cidade"),
            "estado": fields.String(description="Estado (UF)"),
            "cep": fields.String(description="CEP"),
        },
    )

    instituicao_create_request = api.model(
        "InstituicaoCreateRequest",
        {
            "nome": fields.String(required=True, description="Nome da instituição"),
            "tipo": fields.String(description="Tipo (ESCOLA, CRECHE, UNIVERSIDADE)"),
            "endereco": fields.Nested(
                instituicao_endereco_input, required=True, description="Endereço"
            ),
        },
    )

    instituicao_response = api.model(
        "InstituicaoResponse",
        {
            "id": fields.String(description="UUID"),
            "nome": fields.String(description="Nome"),
            "sigla": fields.String(description="Sigla"),
            "uf": fields.String(description="UF"),
            "tipo": fields.String(description="Tipo"),
            "endereco": fields.String(description="Endereço formatado"),
        },
    )

    instituicao_list_response = api.model(
        "InstituicaoListResponse",
        {
            "items": fields.List(fields.Nested(instituicao_response)),
            "total": fields.Integer(description="Total de instituições"),
        },
    )

    return {
        "instituicao_create_request": instituicao_create_request,
        "instituicao_response": instituicao_response,
        "instituicao_list_response": instituicao_list_response,
    }
