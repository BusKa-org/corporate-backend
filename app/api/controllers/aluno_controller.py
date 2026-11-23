from typing import Any

from flask import request
from flask_jwt_extended import get_jwt_identity, jwt_required
from flask_restx import Namespace, Resource

from app.api.contracts import aluno_contract
from app.schemas.aluno_schema import (
    AlunoListResponseSchema,
    AlunoMeUpdateRequestSchema,
    AlunoResponseSchema,
)
from app.schemas.ticket_schema import MovimentoTicketResponseSchema, SaldoTicketResponseSchema
from app.services import aluno_service, ticket_service

api = Namespace("alunos", description="Área do Aluno (App)")

# API contracts (Swagger documentation)
models = aluno_contract.register_models(api)

# Validation / serialisation schemas (Marshmallow)
me_update_schema = AlunoMeUpdateRequestSchema()
aluno_response_schema = AlunoResponseSchema()
aluno_list_response_schema = AlunoListResponseSchema()
saldo_ticket_response_schema = SaldoTicketResponseSchema()
movimento_ticket_response_schema = MovimentoTicketResponseSchema()


@api.route("/me")
class AlunoMeResource(Resource):
    @api.doc("aluno_profile")
    @api.expect(models["me_update_request"])
    @api.response(200, "Success", models["aluno_response"])
    @jwt_required()
    def put(self) -> tuple[dict[str, Any], int]:
        """Aluno atualiza seu perfil (Dados Pessoais + Endereço)"""
        user_id = get_jwt_identity()
        data = request.get_json(silent=True) or {}
        payload = me_update_schema.load(data)

        aluno = aluno_service.update_me(user_id, payload)
        return aluno_response_schema.dump(aluno), 200


@api.route("/")
class AlunoListResource(Resource):
    @api.doc("list_alunos_gestor")
    @api.param("status", "Filter by status (PENDING_APPROVAL, ACTIVE, ...)", _in="query")
    @api.response(200, "Success", models["aluno_list_response"])
    @jwt_required()
    def get(self) -> tuple[dict[str, Any], int]:
        """Gestor vê lista de alunos cadastrados"""
        from flask import request as flask_request

        user_id = get_jwt_identity()
        status_filter = flask_request.args.get("status")
        alunos = aluno_service.list_alunos_gestor(user_id, status=status_filter)
        return (
            aluno_list_response_schema.dump(
                {
                    "items": alunos,
                    "total": len(alunos),
                }
            ),
            200,
        )


@api.route("/<string:aluno_id>")
class AlunoDetailResource(Resource):
    @api.doc("get_aluno_detail")
    @api.response(200, "Success", models["aluno_response"])
    @jwt_required()
    def get(self, aluno_id: str) -> tuple[dict[str, Any], int]:
        """(Gestor) Obtém detalhes completos de um aluno"""
        gestor_id = get_jwt_identity()
        aluno = aluno_service.get_aluno_by_id(gestor_id, aluno_id)
        return aluno_response_schema.dump(aluno), 200


@api.route("/me/tickets")
class AlunoMeTicketsResource(Resource):
    @api.doc("aluno_tickets", responses={200: "Saldo por política vigente"})
    @jwt_required()
    def get(self) -> tuple[dict[str, Any], int]:
        """Saldo de tickets do passageiro, uma linha por política vigente"""
        saldos = ticket_service.listar_saldos_do_aluno(get_jwt_identity())
        return {
            "items": saldo_ticket_response_schema.dump(saldos, many=True),
            "total": len(saldos),
        }, 200


@api.route("/me/tickets/movimentos")
class AlunoMeTicketsMovimentosResource(Resource):
    @api.doc("aluno_tickets_movimentos", params={"limite": "Máximo de linhas (padrão 100)"})
    @jwt_required()
    def get(self) -> tuple[dict[str, Any], int]:
        """Histórico de tickets do passageiro, do mais novo ao mais velho"""
        try:
            limite = int(request.args.get("limite", 100))
        except ValueError:
            limite = 100
        linhas = ticket_service.listar_movimentos_do_aluno(get_jwt_identity(), limite)
        return {
            "items": movimento_ticket_response_schema.dump(linhas, many=True),
            "total": len(linhas),
        }, 200
