"""Onibus endpoint documentation models."""

from flask_restx import fields


def register_models(api):
    """Register onibus models with the API namespace."""

    onibus_create_request = api.model(
        "OnibusCreateRequest",
        {
            "placa": fields.String(required=True, description="Placa do veículo"),
            "modelo": fields.String(description="Modelo"),
            "capacidade": fields.Integer(description="Capacidade de passageiros"),
            "ano": fields.Integer(description="Ano de fabricação"),
        },
    )

    onibus_response = api.model(
        "OnibusResponse",
        {
            "id": fields.String(description="UUID do ônibus"),
            "placa": fields.String(description="Placa"),
            "modelo": fields.String(description="Modelo"),
            "capacidade": fields.Integer(description="Capacidade"),
            "ano": fields.Integer(description="Ano"),
        },
    )

    onibus_list_response = api.model(
        "OnibusListResponse",
        {
            "items": fields.List(fields.Nested(onibus_response)),
            "total": fields.Integer(description="Total de ônibus"),
        },
    )

    onibus_update_request = api.model(
        "OnibusUpdateRequest",
        {
            "placa": fields.String(description="Nova placa do veículo"),
            "modelo": fields.String(description="Novo modelo"),
            "capacidade": fields.Integer(description="Nova capacidade de passageiros"),
        },
    )

    return {
        "onibus_create_request": onibus_create_request,
        "onibus_update_request": onibus_update_request,
        "onibus_response": onibus_response,
        "onibus_list_response": onibus_list_response,
    }
