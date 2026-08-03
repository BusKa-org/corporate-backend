"""RF-09 / RF-20 — consentimento LGPD e exclusão de conta.

Namespace registrado vazio de propósito: o registro em `app/__init__.py` é
feito uma vez, antes dos planos rodarem, para que nenhum deles precise editar
o app factory. Os recursos entram aqui.
"""

from typing import Any

from flask import request
from flask_jwt_extended import get_jwt_identity, jwt_required
from flask_restx import Namespace, Resource

from app.api.contracts import consentimento_contract
from app.schemas.consentimento_schema import (
    ConsentimentoResponseSchema,
    ConsentimentoStatusResponseSchema,
    ExclusaoContaRequestSchema,
    MessageResponseSchema,
)
from app.services import consentimento_service, user_service

api = Namespace("consentimento", description="Consentimento LGPD e Direitos do Titular")

# API contracts (Swagger documentation)
models = consentimento_contract.register_models(api)

# Validation schemas (Marshmallow)
status_response_schema = ConsentimentoStatusResponseSchema()
consentimento_response_schema = ConsentimentoResponseSchema()
exclusao_conta_schema = ExclusaoContaRequestSchema()
message_response_schema = MessageResponseSchema()


def _ip_origem() -> str | None:
    """IP do titular no momento do aceite, exigido como contexto da prova."""
    encaminhado = request.headers.get("X-Forwarded-For", "")
    return encaminhado.split(",")[0].strip() or request.remote_addr


@api.route("")
class ConsentimentoResource(Resource):
    @api.doc("get_consentimento_status", responses={200: "Success", 404: "Usuário não encontrado"})
    @api.response(200, "Success", models["consentimento_status_response"])
    @jwt_required()
    def get(self) -> tuple[dict[str, Any], int]:
        """Situação do usuário logado perante a versão vigente do termo"""
        status = consentimento_service.get_status(get_jwt_identity())
        return status_response_schema.dump(status), 200

    @api.doc("registrar_consentimento", responses={201: "Aceite registrado", 404: "Não encontrado"})
    @api.response(201, "Aceite registrado", models["consentimento_response"])
    @jwt_required()
    def post(self) -> tuple[dict[str, Any], int]:
        """Registra o aceite do Termo e da Política de Privacidade"""
        aceite = consentimento_service.registrar_aceite(get_jwt_identity(), _ip_origem())
        return consentimento_response_schema.dump(aceite), 201


@api.route("/conta")
class ExclusaoContaResource(Resource):
    @api.doc(
        "excluir_conta",
        responses={
            200: "Conta excluída",
            400: "Dados inválidos",
            401: "Credenciais inválidas",
            409: "Viagem em andamento com embarque confirmado",
        },
    )
    @api.expect(models["exclusao_conta_request"])
    @api.response(200, "Conta excluída", models["message_response"])
    @jwt_required()
    def delete(self) -> tuple[dict[str, Any], int]:
        """Exclui a conta e anonimiza os dados pessoais do titular (Art. 18 LGPD)"""
        payload = exclusao_conta_schema.load(request.get_json(silent=True) or {})
        user_service.excluir_conta(get_jwt_identity(), payload)
        return (
            message_response_schema.dump(
                {"message": "Conta excluída e dados pessoais anonimizados"}
            ),
            200,
        )
