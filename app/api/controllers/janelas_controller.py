"""RF-05 — janelas de disponibilidade do veículo.

Namespace registrado vazio de propósito: o registro em `app/__init__.py` é
feito uma vez, antes dos planos rodarem, para que nenhum deles precise editar
o app factory. Os recursos entram aqui.
"""

from typing import Any

from flask import request
from flask_jwt_extended import get_jwt_identity, jwt_required
from flask_restx import Namespace, Resource

from app.api.contracts import janela_contract
from app.schemas.janela_schema import (
    JanelaCreateRequestSchema,
    JanelaListQuerySchema,
    JanelaListResponseSchema,
    JanelaResponseSchema,
    JanelaUpdateRequestSchema,
    JanelaVigenteResponseSchema,
    MessageResponseSchema,
)
from app.services import janela_service

api = Namespace("janelas", description="Janelas de Disponibilidade do Veículo")

# API contracts (Swagger documentation)
models = janela_contract.register_models(api)

# Validation schemas (Marshmallow)
janela_create_request_schema = JanelaCreateRequestSchema()
janela_update_request_schema = JanelaUpdateRequestSchema()
janela_list_query_schema = JanelaListQuerySchema()
janela_response_schema = JanelaResponseSchema()
janela_list_response_schema = JanelaListResponseSchema()
janela_vigente_response_schema = JanelaVigenteResponseSchema()
message_response_schema = MessageResponseSchema()


@api.route("/")
class JanelaListResource(Resource):
    @api.doc("list_janelas")
    @api.response(200, "Success", models["janela_list_response"])
    @jwt_required()
    def get(self) -> tuple[dict[str, Any], int]:
        """Lista as janelas de disponibilidade da organização (Gestor)"""
        filtros = janela_list_query_schema.load(request.args.to_dict())
        janelas = janela_service.listar(get_jwt_identity(), filtros)
        return (
            janela_list_response_schema.dump({"items": janelas, "total": len(janelas)}),
            200,
        )

    @api.doc("create_janela")
    @api.expect(models["janela_request"])
    @api.response(201, "Created", models["janela_response"])
    @jwt_required()
    def post(self) -> tuple[dict[str, Any], int]:
        """Cria uma janela de disponibilidade (Gestor)"""
        payload = janela_create_request_schema.load(request.get_json(silent=True) or {})
        janela = janela_service.criar(get_jwt_identity(), payload)
        return janela_response_schema.dump(janela), 201


@api.route("/vigente")
class JanelaVigenteResource(Resource):
    @api.doc("get_janela_vigente")
    @api.response(200, "Success", models["janela_vigente_response"])
    @jwt_required()
    def get(self) -> tuple[dict[str, Any], int]:
        """Janela em vigor agora e horários de operação do dia"""
        vigente = janela_service.vigente_para_usuario(get_jwt_identity())
        return janela_vigente_response_schema.dump(vigente), 200


@api.route("/<string:id>")
class JanelaResource(Resource):
    @api.doc("update_janela")
    @api.expect(models["janela_request"])
    @api.response(200, "Updated", models["janela_response"])
    @jwt_required()
    def patch(self, id: str) -> tuple[dict[str, Any], int]:
        """Atualiza uma janela de disponibilidade (Gestor)"""
        payload = janela_update_request_schema.load(request.get_json(silent=True) or {})
        janela = janela_service.atualizar(get_jwt_identity(), id, payload)
        return janela_response_schema.dump(janela), 200

    @api.doc("delete_janela")
    @api.response(200, "Deleted", models["message_response"])
    @jwt_required()
    def delete(self, id: str) -> tuple[dict[str, Any], int]:
        """Remove uma janela de disponibilidade (Gestor)"""
        janela_service.remover(get_jwt_identity(), id)
        return message_response_schema.dump({"message": "Janela removida com sucesso"}), 200
