"""RF-15 a RF-18 — credencial de embarque, roteiro do motorista e sincronização.

O embarque por QR tem dois passos (RF-17): `checkin` confere a credencial e
devolve o passageiro com a foto; o motorista então `confirmacao` ou `recusa`.
`validacao`, o passo único antigo, responde 410 para o app desatualizado.
"""

from typing import Any

from flask import request
from flask_jwt_extended import get_jwt_identity, jwt_required
from flask_restx import Namespace, Resource

from app.api.contracts import embarque_contract
from app.extensions import limite_tempo_real
from app.schemas.embarque_schema import (
    AvancarPontoRequestSchema,
    CheckinResponseSchema,
    EmbarqueManualRequestSchema,
    EmbarqueResponseSchema,
    QrRequestSchema,
    RecusarEmbarqueRequestSchema,
    RecusaResponseSchema,
    RoteiroResponseSchema,
    SincronizacaoRequestSchema,
    SincronizacaoResponseSchema,
)
from app.services import embarque_service

api = Namespace("embarque", description="Embarque por QR Code e Roteiro do Motorista")

# API contracts (Swagger documentation)
models = embarque_contract.register_models(api)

# Validation schemas (Marshmallow)
qr_request_schema = QrRequestSchema()
recusar_request_schema = RecusarEmbarqueRequestSchema()
manual_request_schema = EmbarqueManualRequestSchema()
avancar_request_schema = AvancarPontoRequestSchema()
sincronizacao_request_schema = SincronizacaoRequestSchema()
roteiro_response_schema = RoteiroResponseSchema()
embarque_response_schema = EmbarqueResponseSchema()
checkin_response_schema = CheckinResponseSchema()
recusa_response_schema = RecusaResponseSchema()
sincronizacao_response_schema = SincronizacaoResponseSchema()


CODIGOS_RECUSA = (
    "CREDENCIAL_DE_OUTRA_VIAGEM, CREDENCIAL_DE_OUTRO_PONTO, CREDENCIAL_JA_UTILIZADA, "
    "CREDENCIAL_EXPIRADA, CREDENCIAL_RECUSADA, CREDENCIAL_DESATUALIZADA ou CODIGO_EXPIRADO"
)


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
    @limite_tempo_real
    def post(self, viagem_id: str) -> tuple[dict[str, Any], int]:
        """Conclui a parada corrente e segue para a próxima (RF-16)"""
        payload = avancar_request_schema.load(_body())
        roteiro = embarque_service.avancar_ponto(
            get_jwt_identity(), viagem_id, payload["ocorrido_em"]
        )
        return roteiro_response_schema.dump(roteiro), 200


@api.route("/viagens/<string:viagem_id>/validacao")
class ValidacaoDescontinuadaResource(Resource):
    @api.doc("validar_embarque_descontinuado")
    @api.response(410, "ENDPOINT_DESCONTINUADO: use /checkin e depois /confirmacao")
    def post(self, viagem_id: str) -> tuple[dict[str, Any], int]:
        """Descontinuado: embarcava na leitura, sem conferir a foto (RF-17)"""
        embarque_service.endpoint_descontinuado()
        return {}, 410


@api.route("/viagens/<string:viagem_id>/checkin")
class CheckinResource(Resource):
    @api.doc("checkin_embarque")
    @api.expect(models["qr_request"])
    @api.response(200, "Credencial válida, passageiro a conferir", models["checkin_response"])
    @api.response(404, "CREDENCIAL_DESCONHECIDA")
    @api.response(409, CODIGOS_RECUSA)
    @jwt_required()
    @limite_tempo_real
    def post(self, viagem_id: str) -> tuple[dict[str, Any], int]:
        """Confere o QR lido e devolve o passageiro com a foto, sem embarcar (RF-17)"""
        payload = qr_request_schema.load(_body())
        resultado = embarque_service.checkin_embarque(
            get_jwt_identity(), viagem_id, payload["qr_token"]
        )
        return checkin_response_schema.dump(resultado), 200


@api.route("/viagens/<string:viagem_id>/confirmacao")
class ConfirmacaoResource(Resource):
    @api.doc("confirmar_embarque")
    @api.expect(models["qr_request"])
    @api.response(200, "Embarque registrado", models["embarque_response"])
    @api.response(404, "CREDENCIAL_DESCONHECIDA")
    @api.response(409, f"{CODIGOS_RECUSA} ou SEM_FOTO_EXIGE_MANUAL")
    @jwt_required()
    @limite_tempo_real
    def post(self, viagem_id: str) -> tuple[dict[str, Any], int]:
        """A foto confere: registra o embarque e consome a credencial (RF-17)"""
        payload = qr_request_schema.load(_body())
        resultado = embarque_service.confirmar_embarque(
            get_jwt_identity(), viagem_id, payload["qr_token"]
        )
        return embarque_response_schema.dump(resultado), 200


@api.route("/viagens/<string:viagem_id>/recusa")
class RecusaResource(Resource):
    @api.doc("recusar_embarque")
    @api.expect(models["recusar_request"])
    @api.response(200, "Recusa registrada", models["recusa_response"])
    @api.response(404, "CREDENCIAL_DESCONHECIDA")
    @api.response(409, CODIGOS_RECUSA)
    @jwt_required()
    @limite_tempo_real
    def post(self, viagem_id: str) -> tuple[dict[str, Any], int]:
        """A foto não confere: não embarca, recusa o QR e abre ocorrência (RF-17)"""
        payload = recusar_request_schema.load(_body())
        resultado = embarque_service.recusar_embarque(
            get_jwt_identity(),
            viagem_id,
            payload["qr_token"],
            payload["motivo"],
            payload["observacao"],
        )
        return recusa_response_schema.dump(resultado), 200


@api.route("/viagens/<string:viagem_id>/manual")
class EmbarqueManualResource(Resource):
    @api.doc("confirmar_embarque_manual")
    @api.expect(models["manual_request"])
    @api.response(200, "Embarque registrado", models["embarque_response"])
    @jwt_required()
    @limite_tempo_real
    def post(self, viagem_id: str) -> tuple[dict[str, Any], int]:
        """Fallback manual: motorista acha o aluno na lista do ponto (RF-17)"""
        payload = manual_request_schema.load(_body())
        resultado = embarque_service.confirmar_manual(
            get_jwt_identity(), viagem_id, payload["aluno_id"]
        )
        return embarque_response_schema.dump(resultado), 200


@api.route("/viagens/<string:viagem_id>/sincronizacao")
class SincronizacaoResource(Resource):
    @api.doc("sincronizar_eventos_offline")
    @api.expect(models["sincronizacao_request"])
    @api.response(200, "Lote processado", models["sincronizacao_response"])
    @jwt_required()
    @limite_tempo_real
    def post(self, viagem_id: str) -> tuple[dict[str, Any], int]:
        """Aplica em lote a fila de eventos registrados sem conexão (RF-18)"""
        payload = sincronizacao_request_schema.load(_body())
        resultado = embarque_service.sincronizar(get_jwt_identity(), viagem_id, payload["eventos"])
        return sincronizacao_response_schema.dump(resultado), 200
