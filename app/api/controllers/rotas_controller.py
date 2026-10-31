from typing import Any

from flask import request
from flask_jwt_extended import get_jwt_identity, jwt_required
from flask_restx import Namespace, Resource

from app.api.contracts import ponto_contract, rota_contract, solicitacao_contract
from app.schemas.horario_schema import (
    HorarioCreateRequestSchema,
    HorarioListResponseSchema,
    HorarioResponseSchema,
)
from app.schemas.ponto_schema import (
    PontoFlatListResponseSchema,
)
from app.schemas.rota_schema import (
    RotaCreateRequestSchema,
    RotaDetailResponseSchema,
    RotaListResponseSchema,
    RotaPontosAddRequestSchema,
    RotaResponseSchema,
    RotaUpdateRequestSchema,
)
from app.schemas.solicitacao_schema import RodadaAtivaResponseSchema, SolicitacaoResponseSchema
from app.services import rotas_service, solicitacoes_service
from app.services.consentimento_service import exige_consentimento

api = Namespace("rotas", description="Gestão de Rotas")

# API contracts (Swagger documentation)
models = rota_contract.register_models(api)
ponto_models = ponto_contract.register_models(api)
solicitacao_models = solicitacao_contract.register_models(api)

# Validation schemas (Marshmallow)
rota_response_schema = RotaResponseSchema()
rota_list_response_schema = RotaListResponseSchema()
rota_detail_response_schema = RotaDetailResponseSchema()

rota_create_request_schema = RotaCreateRequestSchema()
rota_update_request_schema = RotaUpdateRequestSchema()
pontos_add_request_schema = RotaPontosAddRequestSchema()
solicitacao_response_schema = SolicitacaoResponseSchema()
rodada_ativa_response_schema = RodadaAtivaResponseSchema()

horario_create_request_schema = HorarioCreateRequestSchema()
horario_response_schema = HorarioResponseSchema()
horario_list_response_schema = HorarioListResponseSchema()

ponto_flat_list_response_schema = PontoFlatListResponseSchema()


@api.route("/")
class RotasListResource(Resource):
    @api.doc("list_rotas")
    @api.response(200, "Success", models["rota_list_response"])
    @jwt_required()
    def get(self) -> tuple[dict[str, Any], int]:
        current_user_id = get_jwt_identity()
        rotas = rotas_service.list_all_rotas(current_user_id)
        return (
            rota_list_response_schema.dump(
                {
                    "items": rotas,
                    "total": len(rotas),
                }
            ),
            200,
        )

    @api.doc("create_rota")
    @api.expect(models["rota_create_request"])
    @api.response(201, "Created", models["rota_response"])
    @jwt_required()
    def post(self) -> tuple[dict[str, Any], int]:
        current_user_id = get_jwt_identity()
        data = request.get_json(silent=True) or {}
        payload = rota_create_request_schema.load(data)

        rota = rotas_service.create_rota(current_user_id, payload)
        return rota_response_schema.dump(rota), 201


@api.route("/me")
class MyRotasResource(Resource):
    @api.doc("list_my_rotas")
    @api.response(200, "Success", models["rota_list_response"])
    @jwt_required()
    def get(self) -> tuple[dict[str, Any], int]:
        current_user_id = get_jwt_identity()
        rotas = rotas_service.list_my_rotas(current_user_id)
        return (
            rota_list_response_schema.dump(
                {
                    "items": rotas,
                    "total": len(rotas),
                }
            ),
            200,
        )


@api.route("/<string:id>/pontos")
class RotaPontosResource(Resource):
    @api.doc("list_rota_pontos")
    @api.response(200, "Success", ponto_models["ponto_flat_list_response"])
    @jwt_required()
    def get(self, id: str) -> tuple[dict[str, Any], int]:
        current_user_id = get_jwt_identity()
        pontos = rotas_service.get_pontos_by_rota(current_user_id, id)
        return (
            ponto_flat_list_response_schema.dump(
                {
                    "items": pontos,
                    "total": len(pontos),
                }
            ),
            200,
        )

    @api.doc("add_rota_pontos")
    @api.expect(models["rota_pontos_add_request"])
    @api.response(200, "Success")
    @jwt_required()
    def post(self, id: str) -> tuple[dict[str, Any], int]:
        current_user_id = get_jwt_identity()
        data = request.get_json(silent=True) or {}
        payload = pontos_add_request_schema.load(data)

        rotas_service.add_ponto(current_user_id, id, payload)
        return {"message": "Pontos adicionados com sucesso"}, 200


@api.route("/<string:id>/pontos/<string:ponto_id>")
class RotaPontoResource(Resource):
    @api.doc("remove_rota_ponto")
    @api.response(200, "Success")
    @jwt_required()
    def delete(self, id: str, ponto_id: str) -> tuple[dict[str, Any], int]:
        current_user_id = get_jwt_identity()
        rotas_service.remover_ponto(current_user_id, id, ponto_id)
        return {"message": "Ponto removido do circuito com sucesso"}, 200


@api.route("/<string:id>/horarios")
class RotaHorariosResource(Resource):
    @api.doc("list_rota_horarios")
    @api.response(200, "Success", models["rota_horario_list_response"])
    @jwt_required()
    def get(self, id: str) -> tuple[dict[str, Any], int]:
        current_user = get_jwt_identity()
        horarios = rotas_service.get_horarios(current_user, id)
        return (
            horario_list_response_schema.dump(
                {
                    "items": horarios,
                    "total": len(horarios),
                }
            ),
            200,
        )

    @api.doc("add_rota_horario")
    @api.expect(models["rota_horario_create_request"])
    @api.response(201, "Created", models["rota_horario_response"])
    @jwt_required()
    def post(self, id: str) -> tuple[dict[str, Any], int]:
        current_user = get_jwt_identity()
        data = request.get_json(silent=True) or {}
        payload = horario_create_request_schema.load(data)

        horario = rotas_service.add_horario(current_user, id, payload)
        return horario_response_schema.dump(horario), 201


@api.route("/<string:id>")
class RotaResource(Resource):
    @api.doc("get_rota")
    @api.response(200, "Success", models["rota_detail_response"])
    @jwt_required()
    def get(self, id: str) -> tuple[dict[str, Any], int]:
        current_user_id = get_jwt_identity()
        rota = rotas_service.get_by_id(current_user_id, id)
        return rota_detail_response_schema.dump(rota), 200

    @api.doc("update_rota")
    @api.expect(models["rota_update_request"])
    @api.response(200, "Success")
    @jwt_required()
    def put(self, id: str) -> tuple[dict[str, Any], int]:
        current_user_id = get_jwt_identity()
        data = request.get_json(silent=True) or {}
        payload = rota_update_request_schema.load(data)

        rota = rotas_service.update_rota(current_user_id, id, payload)
        return rota_response_schema.dump(rota), 200

    @api.doc("delete_rota")
    @api.response(200, "Success")
    @jwt_required()
    def delete(self, id: str) -> tuple[dict[str, Any], int]:
        current_user_id = get_jwt_identity()
        rotas_service.delete_rota(current_user_id, id)
        return {"message": "Rota removida com sucesso"}, 200


@api.route("/<string:id>/solicitacoes")
class RotaSolicitacoesResource(Resource):
    @api.doc("solicitar_viagem")
    @api.response(201, "Created", solicitacao_models["solicitacao_response"])
    @jwt_required()
    @exige_consentimento
    def post(self, id: str) -> tuple[dict[str, Any], int]:
        """(Aluno) Solicita o veículo da rota sob demanda dentro da janela de disponibilidade."""
        user_id = get_jwt_identity()
        solicitacao = solicitacoes_service.solicitar_viagem(user_id, id)
        return solicitacao_response_schema.dump(solicitacao), 201


@api.route("/<string:id>/viagem-ativa")
class RotaViagemAtivaResource(Resource):
    @api.doc("rodada_ativa")
    @api.response(200, "Success", solicitacao_models["rodada_ativa_response"])
    @jwt_required()
    def get(self, id: str) -> tuple[dict[str, Any], int]:
        """Rodada ativa da rota sob demanda (viagem null quando ociosa) e as janelas de hoje."""
        user_id = get_jwt_identity()
        rodada = solicitacoes_service.buscar_rodada_ativa(user_id, id)
        return rodada_ativa_response_schema.dump(rodada), 200
