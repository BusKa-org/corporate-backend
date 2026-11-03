from typing import Any

from flask import request
from flask_jwt_extended import get_jwt_identity, jwt_required
from flask_restx import Namespace, Resource

from app.api.contracts import consentimento_contract
from app.schemas.consentimento_schema import (
    AceiteRequestSchema,
    ConsentimentoEstadoResponseSchema,
)
from app.services import consentimento_service

api = Namespace("consentimento", description="Consentimento LGPD (termo e política de privacidade)")

# API contracts (Swagger documentation)
models = consentimento_contract.register_models(api)

# Validation schemas (Marshmallow)
aceite_request_schema = AceiteRequestSchema()
estado_response_schema = ConsentimentoEstadoResponseSchema()


@api.route("")
class ConsentimentoResource(Resource):
    @api.doc("get_consentimento", responses={200: "Estado do consentimento do usuário logado"})
    @api.response(200, "Success", models["consentimento_estado_response"])
    @jwt_required()
    def get(self) -> tuple[dict[str, Any], int]:
        """Current terms version and whether the logged-in user still needs to accept it"""
        estado = consentimento_service.get_estado(get_jwt_identity())
        return estado_response_schema.dump(estado), 200

    @api.doc(
        "aceitar_consentimento",
        responses={200: "Aceite registrado", 400: "Versão do termo inválida"},
    )
    @api.expect(models["aceite_request"])
    @api.response(200, "Success", models["consentimento_estado_response"])
    @jwt_required()
    def post(self) -> tuple[dict[str, Any], int]:
        """Records acceptance of the current terms version. Body: {"versao": "..."}"""
        payload = aceite_request_schema.load(request.get_json(silent=True) or {})
        estado = consentimento_service.aceitar(get_jwt_identity(), payload["versao"])
        return estado_response_schema.dump(estado), 200

    @api.doc(
        "revogar_consentimento",
        responses={200: "Consentimento revogado", 409: "Não há consentimento vigente"},
    )
    @api.response(200, "Success", models["consentimento_estado_response"])
    @jwt_required()
    def delete(self) -> tuple[dict[str, Any], int]:
        """Revokes consent. The user goes back to the pending state."""
        estado = consentimento_service.revogar(get_jwt_identity())
        return estado_response_schema.dump(estado), 200
