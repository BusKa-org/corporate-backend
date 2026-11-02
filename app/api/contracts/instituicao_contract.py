"""Instituicao endpoint documentation models."""

from flask_restx import fields


def register_models(api):
    """Register instituicao models with the API namespace."""

    instituicao_endereco_input = api.model(
        "InstituicaoEnderecoInput",
        {
            "logradouro": fields.String(description="Logradouro"),
            "numero": fields.String(description="Número"),
            "bairro": fields.String(description="Bairro"),
            "cidade": fields.String(description="Cidade"),
            "cep": fields.String(description="CEP"),
            "latitude": fields.Float(description="Latitude"),
            "longitude": fields.Float(description="Longitude"),
        },
    )

    instituicao_create_request = api.model(
        "InstituicaoCreateRequest",
        {
            "nome": fields.String(required=True, description="Nome da instituição"),
            "cnpj": fields.String(required=True, description="CNPJ"),
            "tipo": fields.String(
                required=True,
                description="Tipo (INSTITUTO_FEDERAL, UNIVERSIDADE_PUBLICA, UNIVERSIDADE_PRIVADA, "
                "ESCOLA_PUBLICA, ESCOLA_PRIVADA, ESCOLA_COMUNITARIA)",
            ),
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
            "cnpj": fields.String(description="CNPJ"),
            "sigla": fields.String(description="Sigla"),
            "uf": fields.String(description="UF"),
            "tipo": fields.String(description="Tipo"),
            "endereco": fields.Nested(instituicao_endereco_input, description="Endereço"),
            "latitude": fields.Float(description="Latitude"),
            "longitude": fields.Float(description="Longitude"),
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
