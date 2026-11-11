from typing import Any

from flask import request
from flask_jwt_extended import get_jwt_identity, jwt_required
from flask_restx import Namespace, Resource

from app.api.contracts import parametros_operacao_contract
from app.schemas.parametros_operacao_schema import (
    ParametrosOperacaoRequestSchema,
    ParametrosOperacaoResponseSchema,
)
from app.services import parametros_operacao_service

api = Namespace("parametros-operacao", description="Parâmetros da operação sob demanda")

# API contracts (Swagger documentation)
models = parametros_operacao_contract.register_models(api)

# Validation schemas (Marshmallow)
parametros_request_schema = ParametrosOperacaoRequestSchema()
parametros_response_schema = ParametrosOperacaoResponseSchema()


@api.route("")
class ParametrosOperacaoResource(Resource):
    @api.doc("get_parametros_operacao", responses={403: "Não é gestor nem motorista"})
    @api.response(200, "Success", models["parametros_response"])
    @jwt_required()
    def get(self) -> tuple[dict[str, Any], int]:
        """On-demand operation parameters of the logged-in user's organization"""
        parametros = parametros_operacao_service.obter(get_jwt_identity())
        return parametros_response_schema.dump(parametros), 200

    @api.doc(
        "put_parametros_operacao",
        responses={400: "Valores inválidos", 403: "Não é gestor"},
    )
    @api.expect(models["parametros_request"])
    @api.response(200, "Success", models["parametros_response"])
    @jwt_required()
    def put(self) -> tuple[dict[str, Any], int]:
        """Saves the organization's on-demand operation parameters (gestor)"""
        payload = parametros_request_schema.load(request.get_json(silent=True) or {})
        parametros = parametros_operacao_service.atualizar(get_jwt_identity(), payload)
        return parametros_response_schema.dump(parametros), 200
