from typing import Any

from flask import Response, request, send_file
from flask_jwt_extended import get_jwt_identity, jwt_required
from flask_restx import Namespace, Resource, reqparse
from werkzeug.datastructures import FileStorage

from app.api.contracts import aluno_contract
from app.core.exceptions import ValidationError
from app.schemas.aluno_schema import (
    AlunoListResponseSchema,
    AlunoMeUpdateRequestSchema,
    AlunoResponseSchema,
)
from app.services import aluno_service

api = Namespace("alunos", description="Área do Aluno (App)")

# API contracts (Swagger documentation)
models = aluno_contract.register_models(api)

# Validation / serialisation schemas (Marshmallow)
me_update_schema = AlunoMeUpdateRequestSchema()
aluno_response_schema = AlunoResponseSchema()
aluno_list_response_schema = AlunoListResponseSchema()

foto_upload_parser = reqparse.RequestParser()
foto_upload_parser.add_argument(
    "foto", location="files", type=FileStorage, required=True, help="JPEG, PNG ou WEBP"
)


@api.route("/me")
class AlunoMeResource(Resource):
    @api.doc("aluno_profile")
    @api.expect(models["me_update_request"])
    @api.response(200, "Success", models["aluno_response"])
    @jwt_required()
    def put(self) -> tuple[dict[str, Any], int]:
        """Aluno atualiza seu perfil (Dados Pessoais + Endereço)"""
        user_id = get_jwt_identity()
        data = request.get_json(silent=True) or {}
        payload = me_update_schema.load(data)

        aluno = aluno_service.update_me(user_id, payload)
        return aluno_response_schema.dump(aluno), 200


@api.route("/me/foto")
class AlunoMeFotoResource(Resource):
    @api.doc("aluno_upload_foto")
    @api.expect(foto_upload_parser)
    @api.response(200, "Success", models["aluno_response"])
    @jwt_required()
    def put(self) -> tuple[dict[str, Any], int]:
        """Aluno envia a própria foto (multipart, campo `foto`)"""
        user_id = get_jwt_identity()
        arquivo = request.files.get("foto")
        if arquivo is None:
            raise ValidationError("Envie a foto no campo 'foto' (multipart/form-data)")

        aluno = aluno_service.salvar_foto(user_id, arquivo.stream)
        return aluno_response_schema.dump(aluno), 200


@api.route("/<string:aluno_id>/foto")
class AlunoFotoResource(Resource):
    @api.doc("get_aluno_foto")
    @api.produces(["image/jpeg", "image/png", "image/webp"])
    @jwt_required()
    def get(self, aluno_id: str) -> Response:
        """Foto do aluno (o próprio aluno, gestor da organização ou motorista da viagem)"""
        user_id = get_jwt_identity()
        caminho, tipo = aluno_service.buscar_foto(user_id, aluno_id)
        return send_file(caminho, mimetype=tipo, max_age=0)


@api.route("/")
class AlunoListResource(Resource):
    @api.doc("list_alunos_gestor")
    @api.param("status", "Filter by status (PENDING_APPROVAL, ACTIVE, ...)", _in="query")
    @api.response(200, "Success", models["aluno_list_response"])
    @jwt_required()
    def get(self) -> tuple[dict[str, Any], int]:
        """Gestor vê lista de alunos cadastrados"""
        from flask import request as flask_request

        user_id = get_jwt_identity()
        status_filter = flask_request.args.get("status")
        alunos = aluno_service.list_alunos_gestor(user_id, status=status_filter)
        return (
            aluno_list_response_schema.dump(
                {
                    "items": alunos,
                    "total": len(alunos),
                }
            ),
            200,
        )


@api.route("/<string:aluno_id>")
class AlunoDetailResource(Resource):
    @api.doc("get_aluno_detail")
    @api.response(200, "Success", models["aluno_response"])
    @jwt_required()
    def get(self, aluno_id: str) -> tuple[dict[str, Any], int]:
        """(Gestor) Obtém detalhes completos de um aluno"""
        gestor_id = get_jwt_identity()
        aluno = aluno_service.get_aluno_by_id(gestor_id, aluno_id)
        return aluno_response_schema.dump(aluno), 200
