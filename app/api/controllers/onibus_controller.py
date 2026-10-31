from typing import Any

from flask import request
from flask_jwt_extended import get_jwt_identity, jwt_required
from flask_restx import Namespace, Resource

from app.api.contracts import janela_contract, onibus_contract
from app.schemas.janela_schema import (
    JanelaCreateRequestSchema,
    JanelaListResponseSchema,
    JanelaResponseSchema,
)
from app.schemas.onibus_schema import (
    OnibusCreateRequestSchema,
    OnibusListResponseSchema,
    OnibusResponseSchema,
    OnibusUpdateRequestSchema,
)
from app.services import janelas_service, onibus_service

api = Namespace("onibus", description="Gerenciamento da Frota")

# API contracts (Swagger documentation)
models = onibus_contract.register_models(api)
janela_models = janela_contract.register_models(api)

# Validation schemas (Marshmallow)
onibus_create_request_schema = OnibusCreateRequestSchema()
onibus_update_request_schema = OnibusUpdateRequestSchema()
onibus_response_schema = OnibusResponseSchema()
onibus_list_response_schema = OnibusListResponseSchema()
janela_create_request_schema = JanelaCreateRequestSchema()
janela_response_schema = JanelaResponseSchema()
janela_list_response_schema = JanelaListResponseSchema()


@api.route("/")
class OnibusListResource(Resource):
    @api.doc("list_onibus")
    @api.response(200, "Success", models["onibus_list_response"])
    @jwt_required()
    def get(self) -> tuple[dict[str, Any], int]:
        """Lista a frota da organização"""
        current_user_id = get_jwt_identity()
        onibus_list = onibus_service.list_all(current_user_id)
        return (
            onibus_list_response_schema.dump(
                {
                    "items": onibus_list,
                    "total": len(onibus_list),
                }
            ),
            200,
        )

    @api.doc("create_onibus")
    @api.expect(models["onibus_create_request"])
    @api.response(201, "Created", models["onibus_response"])
    @jwt_required()
    def post(self) -> tuple[dict[str, Any], int]:
        """Cadastra um novo ônibus"""
        current_user_id = get_jwt_identity()
        data = request.get_json(silent=True) or {}
        payload = onibus_create_request_schema.load(data)
        onibus = onibus_service.create_onibus(current_user_id, payload)
        return onibus_response_schema.dump(onibus), 201


@api.route("/<string:id>")
class OnibusResource(Resource):
    @api.doc("get_onibus")
    @api.response(200, "Success", models["onibus_response"])
    @jwt_required()
    def get(self, id: str) -> tuple[dict[str, Any], int]:
        """Detalhes de um ônibus"""
        current_user_id = get_jwt_identity()
        onibus = onibus_service.get_by_id(current_user_id, id)
        return onibus_response_schema.dump(onibus), 200

    @api.doc("update_onibus")
    @api.expect(models["onibus_update_request"])
    @api.response(200, "Updated", models["onibus_response"])
    @jwt_required()
    def patch(self, id: str) -> tuple[dict[str, Any], int]:
        """Atualiza dados de um ônibus"""
        current_user_id = get_jwt_identity()
        data = request.get_json(silent=True) or {}
        payload = onibus_update_request_schema.load(data)
        onibus = onibus_service.update_onibus(current_user_id, id, payload)
        return onibus_response_schema.dump(onibus), 200

    @api.doc("delete_onibus")
    @jwt_required()
    def delete(self, id: str) -> tuple[dict[str, Any], int]:
        """Remove um ônibus"""
        current_user_id = get_jwt_identity()
        onibus_service.delete_onibus(current_user_id, id)
        return {"message": "Ônibus removido com sucesso"}, 200


@api.route("/<string:id>/janelas")
class JanelaListResource(Resource):
    @api.doc("list_janelas")
    @api.response(200, "Success", janela_models["janela_list_response"])
    @jwt_required()
    def get(self, id: str) -> tuple[dict[str, Any], int]:
        """Lista as janelas de disponibilidade do ônibus"""
        current_user_id = get_jwt_identity()
        janelas = janelas_service.listar_janelas(current_user_id, id)
        return janela_list_response_schema.dump({"items": janelas, "total": len(janelas)}), 200

    @api.doc("create_janela")
    @api.expect(janela_models["janela_create_request"])
    @api.response(201, "Created", janela_models["janela_response"])
    @jwt_required()
    def post(self, id: str) -> tuple[dict[str, Any], int]:
        """Cria uma janela de disponibilidade para o ônibus"""
        current_user_id = get_jwt_identity()
        data = request.get_json(silent=True) or {}
        payload = janela_create_request_schema.load(data)
        janela = janelas_service.criar_janela(current_user_id, id, payload)
        return janela_response_schema.dump(janela), 201


@api.route("/<string:id>/janelas/<string:janela_id>")
class JanelaResource(Resource):
    @api.doc("delete_janela")
    @jwt_required()
    def delete(self, id: str, janela_id: str) -> tuple[dict[str, Any], int]:
        """Remove uma janela de disponibilidade"""
        current_user_id = get_jwt_identity()
        janelas_service.remover_janela(current_user_id, id, janela_id)
        return {"message": "Janela de disponibilidade removida com sucesso"}, 200
