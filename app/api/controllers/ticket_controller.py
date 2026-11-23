from typing import Any

from flask import request
from flask_jwt_extended import get_jwt_identity, jwt_required
from flask_restx import Namespace, Resource

from app.schemas.ticket_schema import (
    ConcessaoRequestSchema,
    ConcessaoResponseSchema,
    ConsumoPassageiroResponseSchema,
    ConsumoPoliticaResponseSchema,
    ConsumoQuerySchema,
    MovimentoTicketResponseSchema,
    PoliticaTicketCreateRequestSchema,
    PoliticaTicketResponseSchema,
    PoliticaTicketUpdateRequestSchema,
)
from app.services import ticket_relatorio_service, ticket_service

api = Namespace("politicas-ticket", description="Políticas de ticket de viagem")

politica_create_schema = PoliticaTicketCreateRequestSchema()
politica_update_schema = PoliticaTicketUpdateRequestSchema()
politica_response_schema = PoliticaTicketResponseSchema()

tickets_api = Namespace("tickets", description="Concessões, histórico e consumo de tickets")

concessao_request_schema = ConcessaoRequestSchema()
concessao_response_schema = ConcessaoResponseSchema()
movimento_response_schema = MovimentoTicketResponseSchema()
consumo_query_schema = ConsumoQuerySchema()
consumo_politica_response_schema = ConsumoPoliticaResponseSchema()
consumo_passageiro_response_schema = ConsumoPassageiroResponseSchema()


@api.route("")
class PoliticaTicketListResource(Resource):
    @api.doc(
        "listar_politicas_ticket",
        params={"grupo_id": "Só as do grupo", "usuario_id": "Só as da pessoa"},
        responses={200: "Políticas da organização", 403: "Não é gestor"},
    )
    @jwt_required()
    def get(self) -> tuple[dict[str, Any], int]:
        """(Gestor) Lista as políticas de ticket da organização"""
        politicas = ticket_service.listar_politicas(
            get_jwt_identity(),
            request.args.get("grupo_id"),
            request.args.get("usuario_id"),
        )
        return {
            "items": politica_response_schema.dump(politicas, many=True),
            "total": len(politicas),
        }, 200

    @api.doc(
        "criar_politica_ticket",
        responses={201: "Política criada", 400: "Dados inválidos", 404: "Alvo não encontrado"},
    )
    @jwt_required()
    def post(self) -> tuple[dict[str, Any], int]:
        """(Gestor) Cria uma política. Sem grupo_id nem usuario_id, vale para a organização."""
        payload = politica_create_schema.load(request.get_json(silent=True) or {})
        politica = ticket_service.criar_politica(get_jwt_identity(), payload)
        return politica_response_schema.dump(politica), 201


@api.route("/<string:politica_id>")
class PoliticaTicketResource(Resource):
    @api.doc("obter_politica_ticket", responses={200: "Política", 404: "Não encontrada"})
    @jwt_required()
    def get(self, politica_id: str) -> tuple[dict[str, Any], int]:
        """(Gestor) Detalha uma política"""
        politica = ticket_service.obter_politica(get_jwt_identity(), politica_id)
        return politica_response_schema.dump(politica), 200

    @api.doc(
        "atualizar_politica_ticket",
        responses={200: "Política atualizada", 400: "Dados inválidos", 404: "Não encontrada"},
    )
    @jwt_required()
    def put(self, politica_id: str) -> tuple[dict[str, Any], int]:
        """(Gestor) Muda só os campos enviados. Encerrar é mandar vigencia_fim."""
        payload = politica_update_schema.load(request.get_json(silent=True) or {})
        politica = ticket_service.atualizar_politica(get_jwt_identity(), politica_id, payload)
        return politica_response_schema.dump(politica), 200

    @api.doc(
        "apagar_politica_ticket",
        responses={200: "Apagada", 404: "Não encontrada", 409: "Tem histórico"},
    )
    @jwt_required()
    def delete(self, politica_id: str) -> tuple[dict[str, str], int]:
        """(Gestor) Apaga uma política sem histórico"""
        ticket_service.apagar_politica(get_jwt_identity(), politica_id)
        return {"message": "Política apagada"}, 200


def _limite() -> int:
    try:
        return int(request.args.get("limite", 100))
    except ValueError:
        return 100


@tickets_api.route("/concessoes")
class ConcessaoResource(Resource):
    @tickets_api.doc(
        "conceder_tickets",
        responses={201: "Tickets concedidos", 400: "Dados inválidos", 404: "Não encontrado"},
    )
    @jwt_required()
    def post(self) -> tuple[dict[str, Any], int]:
        """(Gestor) Soma tickets ao bônus de uma pessoa ou dos membros atuais de um grupo.
        Corpo: politica_id, quantidade, motivo? e usuario_id ou grupo_id"""
        payload = concessao_request_schema.load(request.get_json(silent=True) or {})
        resultado = ticket_service.conceder_tickets(get_jwt_identity(), payload)
        return concessao_response_schema.dump(resultado), 201


@tickets_api.route("/movimentos")
class MovimentoListResource(Resource):
    @tickets_api.doc(
        "listar_movimentos_ticket",
        params={
            "usuario_id": "Só de um passageiro",
            "politica_id": "Só de uma política",
            "limite": "Máximo de linhas (padrão 100, teto 500)",
        },
    )
    @jwt_required()
    def get(self) -> tuple[dict[str, Any], int]:
        """(Gestor) Histórico de gasto, devolução, concessão e no-show, do mais novo ao mais velho"""
        linhas = ticket_service.listar_movimentos(
            get_jwt_identity(),
            request.args.get("usuario_id"),
            request.args.get("politica_id"),
            _limite(),
        )
        return {
            "items": movimento_response_schema.dump(linhas, many=True),
            "total": len(linhas),
        }, 200


@tickets_api.route("/consumo")
class ConsumoResource(Resource):
    @tickets_api.doc(
        "consumo_de_tickets",
        params={
            "de": "Início do período (AAAA-MM-DD)",
            "ate": "Fim do período, inclusive (AAAA-MM-DD)",
            "grupo_id": "Só as políticas deste grupo",
            "politica_id": "Detalha esta política por passageiro",
        },
        responses={200: "Consumo", 400: "Período inválido", 404: "Política não encontrada"},
    )
    @jwt_required()
    def get(self) -> tuple[dict[str, Any], int]:
        """(Gestor) Consumo de tickets por política. Com politica_id, detalha por passageiro.
        Tickets contam pela data do movimento e viagens pela data da viagem."""
        filtros = consumo_query_schema.load(request.args.to_dict())
        if filtros["politica_id"] is not None:
            linhas = ticket_relatorio_service.consumo_por_passageiro(
                get_jwt_identity(), filtros["politica_id"], filtros["de"], filtros["ate"]
            )
            return {
                "items": consumo_passageiro_response_schema.dump(linhas, many=True),
                "total": len(linhas),
            }, 200

        linhas = ticket_relatorio_service.consumo_por_politica(
            get_jwt_identity(), filtros["de"], filtros["ate"], filtros["grupo_id"]
        )
        return {
            "items": consumo_politica_response_schema.dump(linhas, many=True),
            "total": len(linhas),
        }, 200
