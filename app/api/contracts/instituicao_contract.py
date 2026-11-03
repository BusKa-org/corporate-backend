"""Instituicao endpoint documentation models."""

from flask_restx import fields

from app.api.contracts.aluno_contract import endereco_input_fields
from app.models.enum import TipoInstituicao


def register_models(api):
    """Register instituicao models with the API namespace."""

    instituicao_endereco_input = api.model(
        "InstituicaoEnderecoInput",
        {
            **endereco_input_fields(),
            "uf": fields.String(
                pattern="^[A-Za-z]{2}$",
                description="UF (2 letras); sem ela, vale o estado da organização",
            ),
        },
    )

    # Endereco has no coordinates; they come from the ponto (top-level latitude/longitude).
    instituicao_endereco_response = api.model(
        "InstituicaoEnderecoResponse",
        {
            "logradouro": fields.String(description="Logradouro"),
            "numero": fields.String(description="Número"),
            "bairro": fields.String(description="Bairro"),
            "cidade": fields.String(description="Cidade"),
            "cep": fields.String(description="CEP"),
        },
    )

    instituicao_create_request = api.model(
        "InstituicaoCreateRequest",
        {
            "nome": fields.String(
                required=True, min_length=1, max_length=200, description="Nome da instituição"
            ),
            "cnpj": fields.String(
                required=True,
                description="CNPJ com ou sem máscara; gravado com 14 dígitos e único entre "
                "todas as organizações",
            ),
            "tipo": fields.String(
                required=True,
                enum=[t.name for t in TipoInstituicao],
                description="Nome do tipo (TipoInstituicao)",
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
            "endereco": fields.Nested(instituicao_endereco_response, description="Endereço"),
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
