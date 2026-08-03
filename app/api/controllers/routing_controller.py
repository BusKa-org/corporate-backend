from typing import Any

from flask import request
from flask_jwt_extended import jwt_required
from flask_restx import Namespace, Resource

from app.api.contracts import routing_contract
from app.core.exceptions import ValidationError
from app.services import routing_service

api = Namespace("routing", description="Roteamento e Cálculo de Rotas")

models = routing_contract.register_models(api)

_REQUIRED_PARAMS = ("origin_lat", "origin_lng", "dest_lat", "dest_lng")


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
        try:
            params = {k: float(request.args[k]) for k in _REQUIRED_PARAMS}
        except KeyError as exc:
            raise ValidationError(f"Parâmetro obrigatório ausente: {exc.args[0]}")
        except ValueError as exc:
            raise ValidationError(f"Parâmetro inválido (esperado número): {exc}")

        result = routing_service.get_route(
            origin_lat=params["origin_lat"],
            origin_lng=params["origin_lng"],
            dest_lat=params["dest_lat"],
            dest_lng=params["dest_lng"],
        )
        return result, 200
