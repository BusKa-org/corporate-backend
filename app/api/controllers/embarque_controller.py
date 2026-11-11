"""Boarding credential, driver itinerary and offline sync (RF-15 to RF-18).

QR boarding has two steps (RF-17): `checkin` checks the credential and returns
the passenger with the photo; the driver then calls `confirmacao` or `recusa`.
`validacao`, the old single step, answers 410 for outdated apps.
"""

from typing import Any
from uuid import UUID

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


@api.route("/viagens/<uuid:viagem_id>/roteiro")
class RoteiroResource(Resource):
    @api.doc("get_roteiro")
    @api.response(200, "Success", models["roteiro_response"])
    @jwt_required()
    def get(self, viagem_id: UUID) -> tuple[dict[str, Any], int]:
        """Driver's consolidated itinerary, with pickups and drop-offs (RF-16)"""
        return (
            roteiro_response_schema.dump(embarque_service.roteiro(get_jwt_identity(), viagem_id)),
            200,
        )


@api.route("/viagens/<uuid:viagem_id>/roteiro/avancar")
class AvancarPontoResource(Resource):
    @api.doc("avancar_ponto")
    @api.expect(models["avancar_request"])
    @api.response(200, "Success", models["roteiro_response"])
    @jwt_required()
    @limite_tempo_real
    def post(self, viagem_id: UUID) -> tuple[dict[str, Any], int]:
        """Completes the current stop and moves to the next one (RF-16)"""
        payload = avancar_request_schema.load(_body())
        roteiro = embarque_service.avancar_ponto(
            get_jwt_identity(), viagem_id, payload["ocorrido_em"]
        )
        return roteiro_response_schema.dump(roteiro), 200


# <string:...> on purpose: the id is never read, so any id (even a non-UUID) gets the 410.
@api.route("/viagens/<string:viagem_id>/validacao")
class ValidacaoDescontinuadaResource(Resource):
    @api.doc("validar_embarque_descontinuado")
    @api.response(410, "ENDPOINT_DESCONTINUADO: use /checkin e depois /confirmacao")
    def post(self, viagem_id: str) -> tuple[dict[str, Any], int]:
        """Deprecated: boarded on scan, without checking the photo (RF-17)"""
        embarque_service.endpoint_descontinuado()
        return {}, 410


@api.route("/viagens/<uuid:viagem_id>/checkin")
class CheckinResource(Resource):
    @api.doc("checkin_embarque")
    @api.expect(models["qr_request"])
    @api.response(200, "Credencial válida, passageiro a conferir", models["checkin_response"])
    @api.response(404, "CREDENCIAL_DESCONHECIDA")
    @api.response(409, CODIGOS_RECUSA)
    @jwt_required()
    @limite_tempo_real
    def post(self, viagem_id: UUID) -> tuple[dict[str, Any], int]:
        """Checks the scanned QR and returns the passenger photo, without boarding (RF-17)"""
        payload = qr_request_schema.load(_body())
        resultado = embarque_service.checkin_embarque(
            get_jwt_identity(), viagem_id, payload["qr_token"]
        )
        return checkin_response_schema.dump(resultado), 200


@api.route("/viagens/<uuid:viagem_id>/confirmacao")
class ConfirmacaoResource(Resource):
    @api.doc("confirmar_embarque")
    @api.expect(models["qr_request"])
    @api.response(200, "Embarque registrado", models["embarque_response"])
    @api.response(404, "CREDENCIAL_DESCONHECIDA")
    @api.response(409, f"{CODIGOS_RECUSA} ou SEM_FOTO_EXIGE_MANUAL")
    @jwt_required()
    @limite_tempo_real
    def post(self, viagem_id: UUID) -> tuple[dict[str, Any], int]:
        """Photo matches: records the boarding and consumes the credential (RF-17)"""
        payload = qr_request_schema.load(_body())
        resultado = embarque_service.confirmar_embarque(
            get_jwt_identity(), viagem_id, payload["qr_token"]
        )
        return embarque_response_schema.dump(resultado), 200


@api.route("/viagens/<uuid:viagem_id>/recusa")
class RecusaResource(Resource):
    @api.doc("recusar_embarque")
    @api.expect(models["recusar_request"])
    @api.response(200, "Recusa registrada", models["recusa_response"])
    @api.response(404, "CREDENCIAL_DESCONHECIDA")
    @api.response(409, CODIGOS_RECUSA)
    @jwt_required()
    @limite_tempo_real
    def post(self, viagem_id: UUID) -> tuple[dict[str, Any], int]:
        """Photo does not match: no boarding, rejects the QR and opens an incident (RF-17)"""
        payload = recusar_request_schema.load(_body())
        resultado = embarque_service.recusar_embarque(
            get_jwt_identity(),
            viagem_id,
            payload["qr_token"],
            payload["motivo"],
            payload["observacao"],
        )
        return recusa_response_schema.dump(resultado), 200


@api.route("/viagens/<uuid:viagem_id>/manual")
class EmbarqueManualResource(Resource):
    @api.doc("confirmar_embarque_manual")
    @api.expect(models["manual_request"])
    @api.response(200, "Embarque registrado", models["embarque_response"])
    @jwt_required()
    @limite_tempo_real
    def post(self, viagem_id: UUID) -> tuple[dict[str, Any], int]:
        """Manual fallback: driver finds the student in the stop's list (RF-17)"""
        payload = manual_request_schema.load(_body())
        resultado = embarque_service.confirmar_manual(
            get_jwt_identity(), viagem_id, payload["aluno_id"]
        )
        return embarque_response_schema.dump(resultado), 200


@api.route("/viagens/<uuid:viagem_id>/sincronizacao")
class SincronizacaoResource(Resource):
    @api.doc("sincronizar_eventos_offline")
    @api.expect(models["sincronizacao_request"])
    @api.response(200, "Lote processado", models["sincronizacao_response"])
    @jwt_required()
    @limite_tempo_real
    def post(self, viagem_id: UUID) -> tuple[dict[str, Any], int]:
        """Applies in batch the queue of events recorded offline (RF-18)"""
        payload = sincronizacao_request_schema.load(_body())
        resultado = embarque_service.sincronizar(get_jwt_identity(), viagem_id, payload["eventos"])
        return sincronizacao_response_schema.dump(resultado), 200
