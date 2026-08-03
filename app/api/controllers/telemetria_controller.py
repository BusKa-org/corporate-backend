"""RF-22 — ingestão e consulta de telemetria da bateria.

Namespace registrado vazio de propósito: o registro em `app/__init__.py` é
feito uma vez, antes dos planos rodarem, para que nenhum deles precise editar
o app factory. Os recursos entram aqui.
"""

from typing import Any

from flask import request
from flask_jwt_extended import get_jwt_identity, jwt_required
from flask_restx import Namespace, Resource

from app.api.contracts import telemetria_contract
from app.schemas.telemetria_schema import (
    ConsumoViagemListResponseSchema,
    IngestaoResponseSchema,
    IngestaoTelemetriaRequestSchema,
    PeriodoQuerySchema,
    TelemetriaListResponseSchema,
)
from app.services import telemetria_service

api = Namespace("telemetria", description="Telemetria do Veículo Elétrico")

# API contracts (Swagger documentation)
models = telemetria_contract.register_models(api)

# Validation schemas (Marshmallow)
ingestao_request_schema = IngestaoTelemetriaRequestSchema()
ingestao_response_schema = IngestaoResponseSchema()
periodo_query_schema = PeriodoQuerySchema()
telemetria_list_response_schema = TelemetriaListResponseSchema()
consumo_viagem_list_response_schema = ConsumoViagemListResponseSchema()


@api.route("/ingestao")
class TelemetriaIngestaoResource(Resource):
    @api.doc("ingerir_telemetria")
    @api.expect(models["ingestao_request"])
    @api.response(201, "Lote processado", models["ingestao_response"])
    @jwt_required()
    def post(self) -> tuple[dict[str, Any], int]:
        """(Veículo) Envia um lote de amostras de telemetria"""
        current_user_id = get_jwt_identity()
        data = request.get_json(silent=True) or {}
        payload = ingestao_request_schema.load(data)
        resultado = telemetria_service.ingerir(
            current_user_id, payload["veiculo_id"], payload["amostras"]
        )
        return ingestao_response_schema.dump(resultado), 201


@api.route("/ultimo")
class TelemetriaUltimoResource(Resource):
    @api.doc("ultimo_por_veiculo")
    @api.response(200, "Success", models["telemetria_list_response"])
    @jwt_required()
    def get(self) -> tuple[dict[str, Any], int]:
        """(Gestor) Última leitura de cada veículo da frota"""
        current_user_id = get_jwt_identity()
        leituras = telemetria_service.ultimo_por_veiculo(current_user_id)
        return (
            telemetria_list_response_schema.dump(
                {"items": leituras, "total": len(leituras)},
            ),
            200,
        )


@api.route("/serie")
class TelemetriaSerieResource(Resource):
    @api.doc("serie_telemetria")
    @api.param("veiculo_id", "Filtra por veículo", _in="query")
    @api.param("inicio", "Início do período, inclusivo (ISO 8601)", _in="query")
    @api.param("fim", "Fim do período, inclusivo (ISO 8601)", _in="query")
    @api.response(200, "Success", models["telemetria_list_response"])
    @jwt_required()
    def get(self) -> tuple[dict[str, Any], int]:
        """(Gestor) Série temporal de telemetria no período"""
        current_user_id = get_jwt_identity()
        filtros = periodo_query_schema.load(request.args.to_dict())
        leituras = telemetria_service.serie(
            current_user_id,
            veiculo_id=filtros["veiculo_id"],
            inicio=filtros["inicio"],
            fim=filtros["fim"],
        )
        return (
            telemetria_list_response_schema.dump(
                {"items": leituras, "total": len(leituras)},
            ),
            200,
        )


@api.route("/consumo-por-viagem")
class TelemetriaConsumoViagemResource(Resource):
    @api.doc("consumo_por_viagem")
    @api.param("inicio", "Início do período, inclusivo (ISO 8601)", _in="query")
    @api.param("fim", "Fim do período, inclusivo (ISO 8601)", _in="query")
    @api.response(200, "Success", models["consumo_viagem_list_response"])
    @jwt_required()
    def get(self) -> tuple[dict[str, Any], int]:
        """(Gestor) Consumo energético agregado por viagem"""
        current_user_id = get_jwt_identity()
        filtros = periodo_query_schema.load(request.args.to_dict())
        agregados = telemetria_service.consumo_por_viagem(
            current_user_id, inicio=filtros["inicio"], fim=filtros["fim"]
        )
        return (
            consumo_viagem_list_response_schema.dump(
                {"items": agregados, "total": len(agregados)},
            ),
            200,
        )
