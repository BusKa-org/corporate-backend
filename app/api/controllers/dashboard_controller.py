from http import HTTPStatus
from typing import Any

from flask import Response, request
from flask_jwt_extended import get_jwt_identity, jwt_required
from flask_restx import Namespace, Resource, reqparse

from app.api.contracts import dashboard_contract
from app.schemas.dashboard_schema import AusenciasQuerySchema, PeriodoRelatorioQuerySchema
from app.services.dashboard_service import (
    exportar_indicadores_csv,
    indicadores_periodo,
    listar_ausencias,
    obter_progresso_viagem,
    obter_telemetria_viagem,
    relatorio_periodo_gestor,
)

api = Namespace("dashboard", description="Métricas e Relatórios para o Gestor")

# API contracts (Swagger documentation)
models = dashboard_contract.register_models(api)

# Validation schemas (Marshmallow)
periodo_query_schema = PeriodoRelatorioQuerySchema()
ausencias_query_schema = AusenciasQuerySchema()

relatorio_parser = reqparse.RequestParser()
relatorio_parser.add_argument(
    "data_inicio", type=str, required=True, help="Data de início do relatório (YYYY-MM-DD)"
)
relatorio_parser.add_argument(
    "data_fim", type=str, required=True, help="Data de fim do relatório (YYYY-MM-DD)"
)


@api.route("/viagens/<uuid:viagem_id>/progresso")
class ProgressoViagemResource(Resource):
    @api.doc("progresso_viagem")
    @api.marshal_list_with(models["ponto_progresso"], code=HTTPStatus.OK)
    @jwt_required()
    def get(self, viagem_id):
        """Gets a trip's progress (the fixed stops visited)."""
        current_user_id = get_jwt_identity()
        progresso = obter_progresso_viagem(gestor_id=current_user_id, viagem_id=str(viagem_id))
        return progresso, 200


@api.route("/relatorios/periodo")
class RelatorioPeriodoResource(Resource):
    @api.doc("relatorio_periodo")
    @api.expect(relatorio_parser, validate=True)
    @api.marshal_with(models["relatorio_estatisticas"], code=HTTPStatus.OK)
    @jwt_required()
    def get(self):
        """Generates the operational report for a period."""
        args = relatorio_parser.parse_args()
        current_user_id = get_jwt_identity()

        relatorio = relatorio_periodo_gestor(
            gestor_id=current_user_id, data_inicio=args["data_inicio"], data_fim=args["data_fim"]
        )
        return relatorio, 200


@api.route("/indicadores")
class IndicadoresPeriodoResource(Resource):
    @api.doc("indicadores_periodo")
    @api.param("inicio", "Início do período, inclusivo (YYYY-MM-DD)", _in="query", required=True)
    @api.param("fim", "Fim do período, inclusivo (YYYY-MM-DD)", _in="query", required=True)
    @api.response(200, "Success", models["indicadores_periodo"])
    @jwt_required()
    def get(self) -> tuple[dict[str, Any], int]:
        """(Manager) Aggregated, anonymized indicators for the period (RF-21)"""
        filtros = periodo_query_schema.load(request.args.to_dict())
        dados = indicadores_periodo(
            gestor_id=get_jwt_identity(), inicio=filtros["inicio"], fim=filtros["fim"]
        )
        return dados, 200


@api.route("/indicadores/exportar")
class IndicadoresExportacaoResource(Resource):
    @api.doc("exportar_indicadores")
    @api.param("inicio", "Início do período, inclusivo (YYYY-MM-DD)", _in="query", required=True)
    @api.param("fim", "Fim do período, inclusivo (YYYY-MM-DD)", _in="query", required=True)
    @api.response(200, "Relatório em CSV")
    @api.produces(["text/csv"])
    @jwt_required()
    def get(self) -> Response:
        """(Manager) Exports the period report as CSV"""
        filtros = periodo_query_schema.load(request.args.to_dict())
        csv_texto = exportar_indicadores_csv(
            gestor_id=get_jwt_identity(), inicio=filtros["inicio"], fim=filtros["fim"]
        )
        nome = f"relatorio-{filtros['inicio'].isoformat()}-a-{filtros['fim'].isoformat()}.csv"
        return Response(
            csv_texto,
            mimetype="text/csv",
            headers={"Content-Disposition": f'attachment; filename="{nome}"'},
        )


@api.route("/viagens/<uuid:viagem_id>/trajeto-real")
class TrajetoRealViagemResource(Resource):
    @api.doc("trajeto_real_viagem")
    @api.marshal_list_with(models["ponto_telemetria"], code=200)
    @jwt_required()
    def get(self, viagem_id):
        """Gets the full GPS trail (actual route) of a trip."""
        current_user_id = get_jwt_identity()
        rastros = obter_telemetria_viagem(gestor_id=current_user_id, viagem_id=str(viagem_id))
        return rastros, 200


@api.route("/ausencias")
class AusenciasResource(Resource):
    @api.doc("listar_ausencias")
    @api.param("inicio", "Início do período, inclusivo (YYYY-MM-DD)", _in="query", required=True)
    @api.param("fim", "Fim do período, inclusivo (YYYY-MM-DD)", _in="query", required=True)
    @api.param("page", "Página (padrão 1)", _in="query", type=int)
    @api.param("per_page", "Itens por página (padrão 20, máximo 100)", _in="query", type=int)
    @api.response(200, "Success", models["ausencias_lista"])
    @jwt_required()
    def get(self) -> tuple[dict[str, Any], int]:
        """(Manager) Lists students who missed a confirmed trip or dropped out of it"""
        filtros = ausencias_query_schema.load(request.args.to_dict())
        dados = listar_ausencias(
            gestor_id=get_jwt_identity(),
            inicio=filtros["inicio"],
            fim=filtros["fim"],
            page=filtros["page"],
            per_page=filtros["per_page"],
        )
        return dados, 200
