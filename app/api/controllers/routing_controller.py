import math
from typing import Any

from flask import request
from flask_jwt_extended import jwt_required
from flask_restx import Namespace, Resource

from app.api.contracts import routing_contract
from app.core.exceptions import ValidationError
from app.services import routing_service

api = Namespace("routing", description="Roteamento e Cálculo de Rotas")

# API contracts (Swagger documentation)
models = routing_contract.register_models(api)

_REQUIRED_PARAMS = ("origin_lat", "origin_lng", "dest_lat", "dest_lng")
_LAT_PARAMS = ("origin_lat", "dest_lat")


@api.route("/route")
class RouteResource(Resource):
    @api.doc(
        "get_route",
        params={
            "origin_lat": "Latitude da origem",
            "origin_lng": "Longitude da origem",
            "dest_lat": "Latitude do destino",
            "dest_lng": "Longitude do destino",
        },
    )
    @api.response(200, "Success", models["route_response"])
    @api.response(400, "Parâmetros inválidos ou ausentes")
    @api.response(404, "Nenhuma rota encontrada")
    @api.response(503, "Serviço de roteamento indisponível")
    @jwt_required()
    def get(self) -> tuple[dict[str, Any], int]:
        params: dict[str, float] = {}
        for nome in _REQUIRED_PARAMS:
            try:
                valor = float(request.args[nome])
            except KeyError:
                raise ValidationError(f"Parâmetro obrigatório ausente: {nome}")
            except ValueError as exc:
                raise ValidationError(f"Parâmetro inválido (esperado número): {exc}")

            # float() accepts "nan" and "inf", which would reach the routing engine.
            if not math.isfinite(valor):
                raise ValidationError(f"Parâmetro inválido (esperado número finito): {nome}")
            limite = 90 if nome in _LAT_PARAMS else 180
            if valor < -limite or valor > limite:
                raise ValidationError(f"Parâmetro fora do intervalo [-{limite}, {limite}]: {nome}")
            params[nome] = valor

        result = routing_service.get_route(
            origin_lat=params["origin_lat"],
            origin_lng=params["origin_lng"],
            dest_lat=params["dest_lat"],
            dest_lng=params["dest_lng"],
        )
        return result, 200
