from typing import Any

from flask import request
from flask_jwt_extended import get_jwt_identity, jwt_required
from flask_restx import Namespace, Resource

from app.schemas.grupo_schema import (
    GrupoCreateRequestSchema,
    GrupoResponseSchema,
    GrupoUpdateRequestSchema,
    MembroAddRequestSchema,
    MembroResponseSchema,
)
from app.services import grupo_service

api = Namespace("grupos", description="Grupos de passageiros")

grupo_create_schema = GrupoCreateRequestSchema()
grupo_update_schema = GrupoUpdateRequestSchema()
membro_add_schema = MembroAddRequestSchema()
grupo_response_schema = GrupoResponseSchema()
membro_response_schema = MembroResponseSchema()


@api.route("")
class GrupoListResource(Resource):
    @api.doc("listar_grupos", responses={200: "Grupos da organização", 403: "Não é gestor"})
    @jwt_required()
    def get(self) -> tuple[dict[str, Any], int]:
        """(Gestor) Lista os grupos da organização"""
        grupos = grupo_service.listar_grupos(get_jwt_identity())
        return {"items": grupo_response_schema.dump(grupos, many=True), "total": len(grupos)}, 200

    @api.doc(
        "criar_grupo",
        responses={201: "Grupo criado", 400: "Dados inválidos", 409: "Nome já usado"},
    )
    @jwt_required()
    def post(self) -> tuple[dict[str, Any], int]:
        """(Gestor) Cria um grupo. Corpo: nome, descricao?, data_inicio?, data_fim?, grupo_pai_id?"""
        payload = grupo_create_schema.load(request.get_json(silent=True) or {})
        grupo = grupo_service.criar_grupo(get_jwt_identity(), payload)
        return grupo_response_schema.dump(grupo), 201


@api.route("/<string:grupo_id>")
class GrupoResource(Resource):
    @api.doc(
        "atualizar_grupo",
        responses={200: "Grupo atualizado", 404: "Não encontrado", 409: "Nome já usado"},
    )
    @jwt_required()
    def put(self, grupo_id: str) -> tuple[dict[str, Any], int]:
        """(Gestor) Muda só os campos enviados. Encerrar ou renovar é mandar data_fim."""
        payload = grupo_update_schema.load(request.get_json(silent=True) or {})
        grupo = grupo_service.atualizar_grupo(get_jwt_identity(), grupo_id, payload)
        return grupo_response_schema.dump(grupo), 200

    @api.doc(
        "apagar_grupo",
        responses={200: "Apagado", 404: "Não encontrado", 409: "Tem subgrupos"},
    )
    @jwt_required()
    def delete(self, grupo_id: str) -> tuple[dict[str, str], int]:
        """(Gestor) Apaga o grupo e o histórico de vínculos dele"""
        grupo_service.apagar_grupo(get_jwt_identity(), grupo_id)
        return {"message": "Grupo apagado"}, 200


@api.route("/<string:grupo_id>/membros")
class GrupoMembrosResource(Resource):
    @api.doc("listar_membros_do_grupo", responses={200: "Vínculos do grupo"})
    @jwt_required()
    def get(self, grupo_id: str) -> tuple[dict[str, Any], int]:
        """(Gestor) Vínculos do grupo e dos subgrupos, atuais e antigos, com as viagens no período"""
        membros = grupo_service.listar_membros(get_jwt_identity(), grupo_id)
        return {
            "items": membro_response_schema.dump(membros, many=True),
            "total": len(membros),
        }, 200

    @api.doc(
        "adicionar_membro_ao_grupo",
        responses={
            201: "Membro adicionado",
            404: "Não encontrado",
            409: "Já é membro ou grupo encerrado",
        },
    )
    @jwt_required()
    def post(self, grupo_id: str) -> tuple[dict[str, str], int]:
        """(Gestor) Adiciona um passageiro ao grupo. Corpo: {"usuario_id"}"""
        payload = membro_add_schema.load(request.get_json(silent=True) or {})
        grupo_service.adicionar_membro(get_jwt_identity(), grupo_id, payload["usuario_id"])
        return {"message": "Membro adicionado"}, 201


@api.route("/<string:grupo_id>/membros/<string:usuario_id>")
class GrupoMembroResource(Resource):
    @api.doc("remover_membro_do_grupo", responses={200: "Removido", 404: "Não participa do grupo"})
    @jwt_required()
    def delete(self, grupo_id: str, usuario_id: str) -> tuple[dict[str, str], int]:
        """(Gestor) Fecha o vínculo do passageiro. O histórico fica."""
        grupo_service.remover_membro(get_jwt_identity(), grupo_id, usuario_id)
        return {"message": "Membro removido"}, 200
