from typing import Any

from flask import request
from flask_jwt_extended import get_jwt_identity, jwt_required
from flask_restx import Namespace, Resource, fields

from app.services.ocorrencia_service import OcorrenciaService

api = Namespace("ocorrencias", description="Registro de ocorrências / problemas")

_ocorrencia_input = api.model(
    "OcorrenciaInput",
    {
        "tipo": fields.String(
            required=True,
            description="ATRASO | SUPERLOTACAO | COMPORTAMENTO | CANCELAMENTO | OUTRO",
            example="ATRASO",
        ),
        "descricao": fields.String(description="Descrição opcional do problema"),
        "viagem_id": fields.String(description="ID da viagem relacionada (opcional)"),
    },
)

_ocorrencia_output = api.model(
    "OcorrenciaResponse",
    {
        "id": fields.String,
        "autor_id": fields.String,
        "autor_nome": fields.String,
        "viagem_id": fields.String,
        "tipo": fields.String,
        "descricao": fields.String,
        "status": fields.String,
        "created_at": fields.String,
    },
)


def _serialize(o) -> dict[str, Any]:
    return {
        "id": str(o.id),
        "autor_id": str(o.autor_id),
        "autor_nome": o.autor.nome if o.autor else "",
        "viagem_id": str(o.viagem_id) if o.viagem_id else None,
        "tipo": o.tipo.value,
        "descricao": o.descricao,
        "status": o.status.value,
        "created_at": str(o.created_at),
    }


@api.route("/")
class OcorrenciaListResource(Resource):
    @api.doc("criar_ocorrencia")
    @api.expect(_ocorrencia_input, validate=True)
    @api.response(201, "Ocorrência registrada", _ocorrencia_output)
    @jwt_required()
    def post(self) -> tuple[dict[str, Any], int]:
        """(Aluno / Motorista) Reporta um problema"""
        user_id = get_jwt_identity()
        data = request.get_json(silent=True) or {}
        ocorrencia = OcorrenciaService.criar(user_id, data)
        return _serialize(ocorrencia), 201

    @api.doc("listar_ocorrencias")
    @api.param("status", "Filter by status (ABERTA, RESOLVIDA)", _in="query")
    @api.response(200, "Success")
    @jwt_required()
    def get(self) -> tuple[list[dict[str, Any]], int]:
        """(Gestor) Lista ocorrências da prefeitura"""
        gestor_id = get_jwt_identity()
        status_filter = request.args.get("status")
        ocorrencias = OcorrenciaService.listar(gestor_id, status=status_filter)
        return [_serialize(o) for o in ocorrencias], 200


@api.route("/<string:ocorrencia_id>/resolver")
class OcorrenciaResolverResource(Resource):
    @api.doc("resolver_ocorrencia")
    @api.response(200, "Ocorrência resolvida", _ocorrencia_output)
    @jwt_required()
    def patch(self, ocorrencia_id: str) -> tuple[dict[str, Any], int]:
        """(Gestor) Marca uma ocorrência como resolvida"""
        gestor_id = get_jwt_identity()
        ocorrencia = OcorrenciaService.resolver(gestor_id, ocorrencia_id)
        return _serialize(ocorrencia), 200
