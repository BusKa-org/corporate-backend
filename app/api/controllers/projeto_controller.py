from typing import Any

from flask import request
from flask_jwt_extended import get_jwt_identity, jwt_required
from flask_restx import Namespace, Resource

from app.api.contracts import projeto_contract
from app.schemas.projeto_schema import (
    ProjetoCreateRequestSchema,
    ProjetoListResponseSchema,
    ProjetoResponseSchema,
    ProjetoUpdateRequestSchema,
)
from app.services import projeto_service

api = Namespace("projetos", description="Projetos dos alunos da organização")

# API contracts (Swagger documentation)
models = projeto_contract.register_models(api)

# Validation schemas (Marshmallow)
projeto_create_request_schema = ProjetoCreateRequestSchema()
projeto_update_request_schema = ProjetoUpdateRequestSchema()
projeto_response_schema = ProjetoResponseSchema()
projeto_list_response_schema = ProjetoListResponseSchema()


@api.route("")
class ProjetoListResource(Resource):
    @api.doc("list_projetos", responses={403: "Não é gestor"})
    @api.response(200, "Success", models["projeto_list_response"])
    @jwt_required()
    def get(self) -> tuple[dict[str, Any], int]:
        """Lists the organization's projects, active and inactive (gestor)"""
        projetos = projeto_service.listar(get_jwt_identity())
        return projeto_list_response_schema.dump({"items": projetos, "total": len(projetos)}), 200

    @api.doc(
        "create_projeto",
        responses={400: "Nome inválido", 403: "Não é gestor ativo", 409: "Nome já usado"},
    )
    @api.expect(models["projeto_create_request"])
    @api.response(201, "Created", models["projeto_response"])
    @jwt_required()
    def post(self) -> tuple[dict[str, Any], int]:
        """Creates a project in the organization (gestor)"""
        payload = projeto_create_request_schema.load(request.get_json(silent=True) or {})
        projeto = projeto_service.criar(get_jwt_identity(), payload)
        return projeto_response_schema.dump(projeto), 201


@api.route("/<string:projeto_id>")
class ProjetoResource(Resource):
    @api.doc(
        "update_projeto",
        responses={
            400: "Dados inválidos",
            403: "Não é gestor ativo",
            404: "Projeto não encontrado na organização",
            409: "Nome já usado",
        },
    )
    @api.expect(models["projeto_update_request"])
    @api.response(200, "Success", models["projeto_response"])
    @jwt_required()
    def patch(self, projeto_id: str) -> tuple[dict[str, Any], int]:
        """Renames, deactivates or reactivates a project (gestor)"""
        payload = projeto_update_request_schema.load(request.get_json(silent=True) or {})
        projeto = projeto_service.atualizar(get_jwt_identity(), projeto_id, payload)
        return projeto_response_schema.dump(projeto), 200
