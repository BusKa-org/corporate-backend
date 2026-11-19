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
from app.schemas.projeto_schema import AlunoProjetoRequestSchema
from app.schemas.user_schema import UserStatusQuerySchema
from app.services import aluno_service, projeto_service

api = Namespace("alunos", description="Área do Aluno (App)")

# API contracts (Swagger documentation)
models = aluno_contract.register_models(api)

# Validation schemas (Marshmallow)
me_update_schema = AlunoMeUpdateRequestSchema()
aluno_response_schema = AlunoResponseSchema()
aluno_list_response_schema = AlunoListResponseSchema()
aluno_projeto_request_schema = AlunoProjetoRequestSchema()
user_status_query_schema = UserStatusQuerySchema()

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
        """Student updates their profile (personal data + address)"""
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
        """Student uploads their own photo (multipart, field `foto`)"""
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
        """Student photo (the student, the organization's manager, or the trip's driver)"""
        user_id = get_jwt_identity()
        caminho, tipo = aluno_service.buscar_foto(user_id, aluno_id)
        return send_file(caminho, mimetype=tipo, max_age=0)


@api.route("/")
class AlunoListResource(Resource):
    @api.doc("list_alunos_gestor")
    @api.param("status", "Filter by status (PENDING_APPROVAL, ACTIVE, ...)", _in="query")
    @api.param("projeto_id", "Filtra pelo projeto (UUID de um projeto da organização)", _in="query")
    @api.response(200, "Success", models["aluno_list_response"])
    @jwt_required()
    def get(self) -> tuple[dict[str, Any], int]:
        """Manager lists registered students"""
        user_id = get_jwt_identity()
        filtros = user_status_query_schema.load(request.args.to_dict())
        alunos = aluno_service.list_alunos_gestor(
            user_id, status=filtros["status"], projeto_id=request.args.get("projeto_id")
        )
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
        """(Manager) Gets a student's full details"""
        gestor_id = get_jwt_identity()
        aluno = aluno_service.get_aluno_by_id(gestor_id, aluno_id)
        return aluno_response_schema.dump(aluno), 200


@api.route("/<string:aluno_id>/projeto")
class AlunoProjetoResource(Resource):
    @api.doc(
        "set_aluno_projeto",
        responses={
            400: "Dados inválidos ou projeto desativado",
            403: "Não é gestor ativo",
            404: "Aluno ou projeto não encontrado na organização",
        },
    )
    @api.expect(models["aluno_projeto_request"])
    @api.response(200, "Success", models["aluno_response"])
    @jwt_required()
    def put(self, aluno_id: str) -> tuple[dict[str, Any], int]:
        """(Manager) Assigns the student to a project, or removes them with null"""
        payload = aluno_projeto_request_schema.load(request.get_json(silent=True) or {})
        aluno = projeto_service.definir_projeto_do_aluno(
            get_jwt_identity(), aluno_id, payload["projeto_id"]
        )
        return aluno_response_schema.dump(aluno), 200
