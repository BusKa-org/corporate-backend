from http import HTTPStatus

from flask_jwt_extended import get_jwt_identity, jwt_required
from flask_restx import Namespace, Resource, reqparse

from app.api.contracts import dashboard_contract
from app.services.dashboard_service import (
    obter_progresso_viagem,
    obter_telemetria_viagem,
    relatorio_periodo_gestor,
)

api = Namespace("dashboard", description="Métricas e Relatórios para o Gestor")

models = dashboard_contract.register_models(api)

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
