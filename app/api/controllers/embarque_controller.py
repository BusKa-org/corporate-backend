"""RF-15 a RF-18 — credencial de embarque, roteiro do motorista e sincronização.

O embarque por QR tem dois passos (RF-17): `validacao` confere a credencial e
devolve o passageiro com a foto; o motorista então `confirmacao` ou `recusa`.
"""

from typing import Any

from flask import request
from flask_jwt_extended import get_jwt_identity, jwt_required
from flask_restx import Namespace, Resource

from app.api.contracts import embarque_contract
from app.schemas.embarque_schema import (
    AvancarPontoRequestSchema,
    ConferenciaResponseSchema,
    EmbarqueManualRequestSchema,
    EmbarqueResponseSchema,
    RecusarEmbarqueRequestSchema,
    RecusaResponseSchema,
    RoteiroResponseSchema,
    SincronizacaoRequestSchema,
    SincronizacaoResponseSchema,
    ValidarEmbarqueRequestSchema,
)
from app.services import embarque_service

api = Namespace("embarque", description="Embarque por QR Code e Roteiro do Motorista")

# API contracts (Swagger documentation)
models = embarque_contract.register_models(api)

# Validation schemas (Marshmallow)
validar_request_schema = ValidarEmbarqueRequestSchema()
recusar_request_schema = RecusarEmbarqueRequestSchema()
manual_request_schema = EmbarqueManualRequestSchema()
avancar_request_schema = AvancarPontoRequestSchema()
sincronizacao_request_schema = SincronizacaoRequestSchema()
roteiro_response_schema = RoteiroResponseSchema()
embarque_response_schema = EmbarqueResponseSchema()
conferencia_response_schema = ConferenciaResponseSchema()
recusa_response_schema = RecusaResponseSchema()
sincronizacao_response_schema = SincronizacaoResponseSchema()


def _body() -> dict[str, Any]:
    return request.get_json(silent=True) or {}


@api.route("/viagens/<string:viagem_id>/roteiro")
class RoteiroResource(Resource):
    @api.doc("get_roteiro")
    @api.response(200, "Success", models["roteiro_response"])
    @jwt_required()
    def get(self, viagem_id: str) -> tuple[dict[str, Any], int]:
        """Roteiro consolidado do motorista, com embarques e desembarques (RF-16)"""
        return (
            roteiro_response_schema.dump(embarque_service.roteiro(get_jwt_identity(), viagem_id)),
            200,
        )


@api.route("/viagens/<string:viagem_id>/roteiro/avancar")
class AvancarPontoResource(Resource):
    @api.doc("avancar_ponto")
    @api.expect(models["avancar_request"])
    @api.response(200, "Success", models["roteiro_response"])
    @jwt_required()
    def post(self, viagem_id: str) -> tuple[dict[str, Any], int]:
        """Conclui a parada corrente e segue para a próxima (RF-16)"""
        payload = avancar_request_schema.load(_body())
        roteiro = embarque_service.avancar_ponto(
            get_jwt_identity(), viagem_id, payload["ocorrido_em"]
        )
        return roteiro_response_schema.dump(roteiro), 200


@api.route("/viagens/<string:viagem_id>/validacao")
class ValidacaoResource(Resource):
    @api.doc("validar_embarque")
    @api.expect(models["validar_request"])
    @api.response(200, "Credencial válida, passageiro a conferir", models["conferencia_response"])
    @api.response(404, "CREDENCIAL_DESCONHECIDA")
    @api.response(409, "CREDENCIAL_DE_OUTRA_VIAGEM, CREDENCIAL_DE_OUTRO_PONTO ou JA_UTILIZADA")
    @jwt_required()
    def post(self, viagem_id: str) -> tuple[dict[str, Any], int]:
        """Confere a credencial lida e devolve o passageiro com a foto, sem embarcar (RF-17)"""
        payload = validar_request_schema.load(_body())
        resultado = embarque_service.validar_embarque(
            get_jwt_identity(), viagem_id, payload["qr_token"], payload["ocorrido_em"]
        )
        return conferencia_response_schema.dump(resultado), 200


@api.route("/viagens/<string:viagem_id>/confirmacao")
class ConfirmacaoResource(Resource):
    @api.doc("confirmar_embarque")
    @api.expect(models["validar_request"])
    @api.response(200, "Embarque registrado", models["embarque_response"])
    @api.response(404, "CREDENCIAL_DESCONHECIDA")
    @api.response(409, "CREDENCIAL_DE_OUTRA_VIAGEM, CREDENCIAL_DE_OUTRO_PONTO ou JA_UTILIZADA")
    @jwt_required()
    def post(self, viagem_id: str) -> tuple[dict[str, Any], int]:
        """A foto confere: registra o embarque e consome a credencial (RF-17)"""
        payload = validar_request_schema.load(_body())
        resultado = embarque_service.confirmar_embarque(
            get_jwt_identity(), viagem_id, payload["qr_token"], payload["ocorrido_em"]
        )
        return embarque_response_schema.dump(resultado), 200


@api.route("/viagens/<string:viagem_id>/recusa")
class RecusaResource(Resource):
    @api.doc("recusar_embarque")
    @api.expect(models["recusar_request"])
    @api.response(200, "Recusa registrada", models["recusa_response"])
    @api.response(404, "CREDENCIAL_DESCONHECIDA")
    @api.response(409, "CREDENCIAL_DE_OUTRA_VIAGEM, CREDENCIAL_DE_OUTRO_PONTO ou JA_UTILIZADA")
    @jwt_required()
    def post(self, viagem_id: str) -> tuple[dict[str, Any], int]:
        """A foto não confere: não embarca e abre ocorrência para o gestor (RF-17)"""
        payload = recusar_request_schema.load(_body())
        resultado = embarque_service.recusar_embarque(
            get_jwt_identity(),
            viagem_id,
            payload["qr_token"],
            payload["motivo"],
            payload["observacao"],
            payload["ocorrido_em"],
        )
        return recusa_response_schema.dump(resultado), 200


@api.route("/viagens/<string:viagem_id>/manual")
class EmbarqueManualResource(Resource):
    @api.doc("confirmar_embarque_manual")
    @api.expect(models["manual_request"])
    @api.response(200, "Embarque registrado", models["embarque_response"])
    @jwt_required()
    def post(self, viagem_id: str) -> tuple[dict[str, Any], int]:
        """Fallback manual: motorista acha o aluno na lista do ponto (RF-17)"""
        payload = manual_request_schema.load(_body())
        resultado = embarque_service.confirmar_manual(
            get_jwt_identity(), viagem_id, payload["aluno_id"], payload["ocorrido_em"]
        )
        return embarque_response_schema.dump(resultado), 200


@api.route("/viagens/<string:viagem_id>/sincronizacao")
class SincronizacaoResource(Resource):
    @api.doc("sincronizar_eventos_offline")
    @api.expect(models["sincronizacao_request"])
    @api.response(200, "Lote processado", models["sincronizacao_response"])
    @jwt_required()
    def post(self, viagem_id: str) -> tuple[dict[str, Any], int]:
        """Aplica em lote a fila de eventos registrados sem conexão (RF-18)"""
        payload = sincronizacao_request_schema.load(_body())
        resultado = embarque_service.sincronizar(get_jwt_identity(), viagem_id, payload["eventos"])
        return sincronizacao_response_schema.dump(resultado), 200
