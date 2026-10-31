from http import HTTPStatus
from typing import Any

from flask import Response, request
from flask_jwt_extended import get_jwt_identity, jwt_required
from flask_restx import Namespace, Resource, reqparse

from app.api.contracts import dashboard_contract
from app.schemas.dashboard_schema import PeriodoRelatorioQuerySchema
from app.services.dashboard_service import (
    exportar_indicadores_csv,
    indicadores_periodo,
    obter_progresso_viagem,
    obter_telemetria_viagem,
    relatorio_periodo_gestor,
)

api = Namespace("dashboard", description="Métricas e Relatórios para o Gestor")

models = dashboard_contract.register_models(api)

periodo_query_schema = PeriodoRelatorioQuerySchema()

relatorio_parser = reqparse.RequestParser()
relatorio_parser.add_argument(
    "data_inicio", type=str, required=True, help="Data de início do relatório (YYYY-MM-DD)"
)
relatorio_parser.add_argument(
    "data_fim", type=str, required=True, help="Data de fim do relatório (YYYY-MM-DD)"
)


@api.route("/viagens/<string:viagem_id>/progresso")
class ProgressoViagemResource(Resource):
    @api.doc("progresso_viagem")
    @api.marshal_list_with(models["ponto_progresso"], code=HTTPStatus.OK)
    @jwt_required()
    def get(self, viagem_id):
        """Obtém o progresso de uma viagem (os pontos fixos visitados)."""
        current_user_id = get_jwt_identity()
        progresso = obter_progresso_viagem(gestor_id=current_user_id, viagem_id=viagem_id)
        return progresso, 200


@api.route("/relatorios/periodo")
class RelatorioPeriodoResource(Resource):
    @api.doc("relatorio_periodo")
    @api.expect(relatorio_parser, validate=True)
    @api.marshal_with(models["relatorio_estatisticas"], code=HTTPStatus.OK)
    @jwt_required()
    def get(self):
        """Gera o relatório operacional de um período."""
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
        """(Gestor) Indicadores agregados e anonimizados do período (RF-21)"""
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
        """(Gestor) Exporta o relatório do período em CSV"""
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


@api.route("/viagens/<string:viagem_id>/trajeto-real")
class TrajetoRealViagemResource(Resource):
    @api.doc("trajeto_real_viagem")
    @api.marshal_list_with(models["ponto_telemetria"], code=200)
    @jwt_required()
    def get(self, viagem_id):
        """Obtém o rastro GPS completo (trajeto real) de uma viagem."""
        current_user_id = get_jwt_identity()
        rastros = obter_telemetria_viagem(gestor_id=current_user_id, viagem_id=viagem_id)
        return rastros, 200
