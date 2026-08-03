from typing import Any

from flask import request
from flask_jwt_extended import get_jwt_identity, jwt_required
from flask_restx import Namespace, Resource

from app.api.contracts import ponto_contract
from app.schemas.ponto_schema import (
    PontoCreateRequestSchema,
    PontoListResponseSchema,
    PontoResponseSchema,
    PontoUpdateRequestSchema,
)
from app.services import pontos_service

api = Namespace("pontos", description="Gestão de Infraestrutura Geográfica")

# API contracts (Swagger documentation)
models = ponto_contract.register_models(api)

# Validation schemas (Marshmallow)
ponto_create_request_schema = PontoCreateRequestSchema()
ponto_update_request_schema = PontoUpdateRequestSchema()
ponto_response_schema = PontoResponseSchema()
ponto_list_response_schema = PontoListResponseSchema()


@api.route("/")
class PontosListResource(Resource):
    @api.doc("list_pontos")
    @api.response(200, "Success", models["ponto_list_response"])
    @jwt_required()
    def get(self) -> tuple[dict[str, Any], int]:
        user_id = get_jwt_identity()
        pontos = pontos_service.list_all(user_id)
        return (
            ponto_list_response_schema.dump(
                {
                    "items": pontos,
                    "total": len(pontos),
                }
            ),
            200,
        )

    @api.doc("create_ponto")
    @api.expect(models["ponto_create_request"])
    @api.response(201, "Created", models["ponto_response"])
    @jwt_required()
    def post(self) -> tuple[dict[str, Any], int]:
        user_id = get_jwt_identity()
        data = request.get_json(silent=True) or {}
        payload = ponto_create_request_schema.load(data)

        ponto = pontos_service.create_ponto(user_id, payload)
        return ponto_response_schema.dump(ponto), 201


@api.route("/<string:id>")
class PontoResource(Resource):
    @api.doc("get_ponto")
    @api.response(200, "Success", models["ponto_response"])
    @jwt_required()
    def get(self, id: str) -> tuple[dict[str, Any], int]:
        user_id = get_jwt_identity()
        ponto = pontos_service.get_by_id(user_id, id)
        return ponto_response_schema.dump(ponto), 200

    @api.doc("update_ponto")
    @api.expect(models["ponto_update_request"])
    @api.response(200, "Success", models["ponto_response"])
    @jwt_required()
    def put(self, id: str) -> tuple[dict[str, Any], int]:
        user_id = get_jwt_identity()
        data = request.get_json(silent=True) or {}
        payload = ponto_update_request_schema.load(data)

        ponto = pontos_service.update_ponto(user_id, id, payload)
        return ponto_response_schema.dump(ponto), 200

    @api.doc("delete_ponto")
    @api.response(200, "Success")
    @jwt_required()
    def delete(self, id: str) -> tuple[dict[str, Any], int]:
        user_id = get_jwt_identity()
        pontos_service.delete_ponto(user_id, id)
        return {"message": "Ponto removido com sucesso"}, 200
