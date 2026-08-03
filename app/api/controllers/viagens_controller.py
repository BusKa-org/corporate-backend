from typing import Any

from flask import request
from flask_jwt_extended import get_jwt_identity, jwt_required
from flask_restx import Namespace, Resource

from app.api.contracts import ponto_contract, viagem_contract
from app.api.contracts.viagem_parsers import parsers
from app.core.exceptions import ValidationError
from app.schemas.ponto_schema import (
    PontoFlatListResponseSchema,
)
from app.schemas.viagem_schema import (
    CancelamentoResponseSchema,
    DeclaracaoResponseSchema,
    DeclaracaoTrajetoRequestSchema,
    MessageResponseSchema,
    RodadaAtivaResponseSchema,
    RodadaResponseSchema,
    ViagemAcaoRequestSchema,
    ViagemAgendaAlunoListResponseSchema,
    ViagemAlunoConfirmacaoResponseSchema,
    ViagemConfirmacaoRequestSchema,
    ViagemCreateRequestSchema,
    ViagemListQuerySchema,
    ViagemListResponseSchema,
    ViagemResponseSchema,
)
from app.services import viagens_service

api = Namespace("viagens", description="Execução de Viagens")

ponto_models = ponto_contract.register_models(api)

# API contracts (Swagger documentation)
models = viagem_contract.register_models(api)

# Validation schemas (Marshmallow)
viagem_response_schema = ViagemResponseSchema()
viagem_list_response_schema = ViagemListResponseSchema()

viagem_create_request_schema = ViagemCreateRequestSchema()
viagem_confirmacao_request_schema = ViagemConfirmacaoRequestSchema()
viagem_acao_request_schema = ViagemAcaoRequestSchema()

viagem_list_query_schema = ViagemListQuerySchema()

message_response_schema = MessageResponseSchema()
viagem_aluno_confirmacao_response_schema = ViagemAlunoConfirmacaoResponseSchema()
viagem_agenda_aluno_list_response_schema = ViagemAgendaAlunoListResponseSchema()


ponto_flat_list_response_schema = PontoFlatListResponseSchema()

declaracao_trajeto_request_schema = DeclaracaoTrajetoRequestSchema()
declaracao_response_schema = DeclaracaoResponseSchema()
rodada_response_schema = RodadaResponseSchema()
rodada_ativa_response_schema = RodadaAtivaResponseSchema()
cancelamento_response_schema = CancelamentoResponseSchema()


# ==========================================
# Rodada sob demanda — RF-10 a RF-13 e RF-19
# ==========================================


@api.route("/solicitar")
class ViagemSolicitarResource(Resource):
    @api.doc(
        "solicitar_viagem",
        responses={
            201: "Solicitação registrada",
            400: "Fora da janela de disponibilidade",
            403: "Sem consentimento vigente",
        },
    )
    @api.response(201, "Solicitação registrada", models["rodada_response"])
    @jwt_required()
    def post(self) -> tuple[dict[str, Any], int]:
        """(Aluno) Solicita o veículo dentro da janela de disponibilidade"""
        rodada = viagens_service.solicitar_viagem(get_jwt_identity())
        return rodada_response_schema.dump(rodada), 201


@api.route("/rodada-ativa")
class ViagemRodadaAtivaResource(Resource):
    @api.doc("get_rodada_ativa")
    @api.response(200, "Success", models["rodada_ativa_response"])
    @jwt_required()
    def get(self) -> tuple[dict[str, Any], int]:
        """(Aluno) Rodada em andamento e contagem regressiva do buffer"""
        return (
            rodada_ativa_response_schema.dump(viagens_service.rodada_ativa(get_jwt_identity())),
            200,
        )


@api.route("/<string:id>/iniciar-percurso")
class ViagemIniciarPercursoResource(Resource):
    @api.doc("iniciar_percurso", responses={200: "Buffer aberto", 400: "Rodada não solicitada"})
    @api.response(200, "Buffer aberto", models["rodada_response"])
    @jwt_required()
    def post(self, id: str) -> tuple[dict[str, Any], int]:
        """(Motorista) Inicia o percurso e abre a janela de buffer"""
        rodada = viagens_service.iniciar_percurso(get_jwt_identity(), id)
        return rodada_response_schema.dump(rodada), 200


@api.route("/<string:id>/declaracao")
class ViagemDeclaracaoResource(Resource):
    @api.doc(
        "declarar_trajeto",
        responses={
            201: "Embarque confirmado",
            400: "Rodada não aceita declarações",
            409: "Indisponibilidade momentânea",
        },
    )
    @api.expect(models["declaracao_trajeto_request"])
    @api.response(201, "Embarque confirmado", models["declaracao_response"])
    @jwt_required()
    def post(self, id: str) -> tuple[dict[str, Any], int]:
        """(Aluno) Declara origem e destino durante o buffer"""
        payload = declaracao_trajeto_request_schema.load(request.get_json(silent=True) or {})
        registro = viagens_service.declarar_trajeto(get_jwt_identity(), id, payload)
        return declaracao_response_schema.dump(registro), 201

    @api.doc("cancelar_solicitacao", responses={200: "Cancelada", 404: "Sem solicitação"})
    @api.response(200, "Cancelada", models["cancelamento_response"])
    @jwt_required()
    def delete(self, id: str) -> tuple[dict[str, Any], int]:
        """(Aluno) Cancela a solicitação da rodada"""
        resultado = viagens_service.cancelar_solicitacao(get_jwt_identity(), id)
        return cancelamento_response_schema.dump(resultado), 200


@api.route("/aluno/agenda")
class AlunoAgendaResource(Resource):
    @api.doc("list_viagens_aluno")
    @api.response(200, "Success", models["viagem_agenda_aluno_list_response"])
    @jwt_required()
    def get(self) -> tuple[dict[str, Any], int]:
        user_id = get_jwt_identity()
        agenda = viagens_service.get_proximas_viagens_aluno(user_id)
        return (
            viagem_agenda_aluno_list_response_schema.dump(
                {
                    "items": agenda,
                    "total": len(agenda),
                }
            ),
            200,
        )


@api.route("/<string:id>/pontos-embarque")
class ViagemPontosResource(Resource):
    @api.doc("list_pontos_embarque_viagem")
    @api.response(200, "Success", ponto_models["ponto_flat_list_response"])
    @jwt_required()
    def get(self, id: str) -> tuple[dict[str, Any], int]:
        """Lista todos os pontos de embarque disponíveis para esta viagem."""
        user_id = get_jwt_identity()
        pontos = viagens_service.listar_pontos_embarque(user_id, id)
        return (
            ponto_flat_list_response_schema.dump(
                {
                    "items": pontos,
                    "total": len(pontos),
                }
            ),
            200,
        )


@api.route("/<string:id>/confirmacao")
class ViagemConfirmacaoResource(Resource):
    @api.doc("confirmar_presenca")
    @api.expect(models["viagem_confirmacao_request"])
    @api.response(200, "Success", models["viagem_aluno_confirmacao_response"])
    @jwt_required()
    def put(self, id: str) -> tuple[dict[str, Any], int]:
        user_id = get_jwt_identity()
        data = request.get_json(silent=True) or {}
        payload = viagem_confirmacao_request_schema.load(data)
        result = viagens_service.confirmar_presenca_aluno(user_id, id, payload)
        return viagem_aluno_confirmacao_response_schema.dump(result), 200


@api.route("/")
class ViagemListResource(Resource):
    @api.doc("list_all_viagens")
    @api.expect(parsers["viagem_list"])
    @api.response(200, "Success", models["viagem_list_response"])
    @jwt_required()
    def get(self) -> tuple[dict[str, Any], int]:
        user_id = get_jwt_identity()
        filters = viagem_list_query_schema.load(request.args.to_dict())
        viagens = viagens_service.list_viagens_gestor(user_id, filters)
        return (
            viagem_list_response_schema.dump(
                {
                    "items": viagens,
                    "total": len(viagens),
                }
            ),
            200,
        )

    @api.doc("create_viagem")
    @api.expect(models["viagem_create_request"])
    @api.response(201, "Created", models["viagem_response"])
    @jwt_required()
    def post(self) -> tuple[dict[str, Any], int]:
        user_id = get_jwt_identity()
        data = request.get_json(silent=True) or {}
        payload = viagem_create_request_schema.load(data)
        result = viagens_service.gerar_viagem(user_id, payload)

        # gerar_viagem returns {message,id,dia}. If you want to return ViagemResponseSchema instead,
        # change service to return the Viagem ORM instance. For now, keep it consistent with existing behavior.
        return result, 201


@api.route("/minhas")
class MinhasViagensResource(Resource):
    @api.doc("list_my_viagens")
    @api.response(200, "Success", models["viagem_list_response"])
    @jwt_required()
    def get(self) -> tuple[dict[str, Any], int]:
        user_id = get_jwt_identity()
        viagens = viagens_service.list_viagens_motorista(user_id)
        return (
            viagem_list_response_schema.dump(
                {
                    "items": viagens,
                    "total": len(viagens),
                }
            ),
            200,
        )


@api.route("/<string:id>/acao")
class ViagemAcaoResource(Resource):
    @api.doc("control_viagem")
    @api.expect(models["viagem_acao_request"])
    @api.response(200, "Success", models["viagem_response"])
    @jwt_required()
    def put(self, id: str) -> tuple[dict[str, Any], int]:
        user_id = get_jwt_identity()
        data = request.get_json(silent=True) or {}
        payload = viagem_acao_request_schema.load(data)
        viagem = viagens_service.controlar_viagem(user_id, id, payload)
        return viagem_response_schema.dump(viagem), 200


@api.route("/<string:id>/cancelar")
class ViagemCancelarResource(Resource):
    @api.doc("cancelar_viagem")
    @api.response(200, "Trip cancelled successfully")
    @jwt_required()
    def put(self, id: str) -> tuple[dict[str, Any], int]:
        """Cancela uma viagem agendada e notifica alunos (Gestor)"""
        user_id = get_jwt_identity()
        result = viagens_service.cancelar_viagem(user_id, id)
        return result, 200


@api.route("/<string:id>/localizacao")
class ViagemLocalizacaoResource(Resource):
    @api.doc("atualizar_localizacao_onibus")
    @api.expect(models["localizacao_request"])
    @jwt_required()
    def post(self, id):
        """(Motorista) Envia coordenada GPS atual do ônibus em tempo real"""
        user_id = get_jwt_identity()
        data = request.get_json()

        result = viagens_service.atualizar_localizacao(user_id, id, data)
        return result, 200

    @api.doc("obter_localizacao_onibus")
    @jwt_required()
    def get(self, id):
        """(Aluno/Motorista) Obtém a localização atual do ônibus (viagem em andamento)."""
        user_id = get_jwt_identity()
        result = viagens_service.obter_localizacao_onibus(user_id, id)
        return result, 200


@api.route("/<uuid:viagem_id>/localizacao-aluno")
class ViagemLocalizacaoAluno(Resource):
    """Endpoint for students to broadcast their real-time location during an active trip."""

    @api.doc("atualizar_localizacao_aluno", security="Bearer Auth")
    @api.expect(models["localizacao_request"])
    @jwt_required()
    def post(self, viagem_id: str):
        """Recebe o GPS em tempo real do Aluno para o Auto-Checkin (Geofencing)."""
        current_user_id = get_jwt_identity()

        data = request.get_json() or {}

        if "latitude" not in data or "longitude" not in data:
            raise ValidationError("Latitude e longitude são obrigatórias na requisição.")

        resultado = viagens_service.atualizar_localizacao_aluno(
            user_id=current_user_id, viagem_id=str(viagem_id), data=data
        )

        return resultado, 200
