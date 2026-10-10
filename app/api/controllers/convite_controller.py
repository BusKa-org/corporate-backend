from typing import Any

from flask import request
from flask_jwt_extended import get_jwt_identity, jwt_required
from flask_restx import Namespace, Resource

from app.schemas.convite_schema import (
    ConviteAceiteRequestSchema,
    ConviteListQuerySchema,
    ConviteResponseSchema,
    ConvitesCreateRequestSchema,
    PinSolicitarRequestSchema,
    PinValidarRequestSchema,
)
from app.services import convite_service

api = Namespace("convites", description="Convites de cadastro de passageiros")

convites_create_schema = ConvitesCreateRequestSchema()
convite_list_query_schema = ConviteListQuerySchema()
convite_aceite_schema = ConviteAceiteRequestSchema()
convite_response_schema = ConviteResponseSchema()
pin_solicitar_schema = PinSolicitarRequestSchema()
pin_validar_schema = PinValidarRequestSchema()


@api.route("")
class ConviteListResource(Resource):
    @api.doc("listar_convites", responses={200: "Convites da organização", 403: "Não é gestor"})
    @jwt_required()
    def get(self) -> tuple[dict[str, Any], int]:
        """(Gestor) Lista os convites da organização. Filtro opcional: ?estado="""
        filtros = convite_list_query_schema.load(request.args.to_dict())
        convites = convite_service.listar_convites(get_jwt_identity(), filtros["estado"])
        return {
            "items": convite_response_schema.dump(convites, many=True),
            "total": len(convites),
        }, 200

    @api.doc(
        "criar_convites",
        responses={200: "Resultado por linha", 400: "Lote inválido", 403: "Não é gestor"},
    )
    @jwt_required()
    def post(self) -> tuple[dict[str, Any], int]:
        """(Gestor) Convida por e-mail, até 500 por chamada. Corpo: {"convites": [{"email", ...}]}"""
        payload = convites_create_schema.load(request.get_json(silent=True) or {})
        resultados = convite_service.criar_convites(get_jwt_identity(), payload["convites"])
        return {"resultados": resultados}, 200


@api.route("/<string:convite_id>")
class ConviteResource(Resource):
    @api.doc(
        "cancelar_convite", responses={200: "Cancelado", 404: "Não encontrado", 409: "Não pendente"}
    )
    @jwt_required()
    def delete(self, convite_id: str) -> tuple[dict[str, str], int]:
        """(Gestor) Cancela um convite pendente"""
        convite_service.cancelar_convite(get_jwt_identity(), convite_id)
        return {"message": "Convite cancelado"}, 200


@api.route("/<string:convite_id>/reenviar")
class ConviteReenviarResource(Resource):
    @api.doc(
        "reenviar_convite", responses={200: "Reenviado", 404: "Não encontrado", 409: "Não pendente"}
    )
    @jwt_required()
    def post(self, convite_id: str) -> tuple[dict[str, Any], int]:
        """(Gestor) Reenvia um convite pendente. O link anterior deixa de valer."""
        convite = convite_service.reenviar_convite(get_jwt_identity(), convite_id)
        return convite_response_schema.dump(convite), 200


@api.route("/aceite/<string:token>")
class ConviteAceiteResource(Resource):
    @api.doc(
        "consultar_convite",
        responses={200: "Dados do convite", 404: "Convite inválido ou expirado"},
    )
    def get(self, token: str) -> tuple[dict[str, Any], int]:
        """(Público) Dados preenchidos pelo gestor e os campos que ainda faltam"""
        return convite_service.consultar_por_token(token), 200

    @api.doc(
        "concluir_convite",
        responses={
            201: "Cadastro concluído",
            400: "Dados inválidos",
            404: "Convite inválido ou expirado",
            409: "E-mail ou CPF já cadastrado",
        },
    )
    def post(self, token: str) -> tuple[dict[str, str], int]:
        """(Público) Conclui o cadastro. Corpo: nome, cpf, telefone, instituicao_id, senha"""
        payload = convite_aceite_schema.load(request.get_json(silent=True) or {})
        convite_service.concluir_convite(token, payload)
        return {"message": "Cadastro concluído. Entre com seu e-mail e senha."}, 201


@api.route("/pin")
class ConvitePinSolicitarResource(Resource):
    @api.doc("solicitar_pin_do_convite", responses={200: "Resposta igual para qualquer e-mail"})
    def post(self) -> tuple[dict[str, str], int]:
        """(Público) Envia um PIN de 10 minutos ao e-mail, se ele estiver habilitado. Corpo: {"email"}"""
        payload = pin_solicitar_schema.load(request.get_json(silent=True) or {})
        convite_service.solicitar_pin(payload["email"])
        return {
            "message": "Se o e-mail estiver habilitado, enviamos um PIN válido por 10 minutos."
        }, 200


@api.route("/pin/validar")
class ConvitePinValidarResource(Resource):
    @api.doc(
        "validar_pin_do_convite", responses={200: "PIN correto", 400: "PIN inválido ou expirado"}
    )
    def post(self) -> tuple[dict[str, str], int]:
        """(Público) Confere o PIN. Devolve o token que abre /aceite/<token>. Corpo: {"email", "pin"}"""
        payload = pin_validar_schema.load(request.get_json(silent=True) or {})
        token = convite_service.validar_pin(payload["email"], payload["pin"])
        return {"token": token}, 200
