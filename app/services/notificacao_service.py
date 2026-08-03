"""Notification service - management notifications for users."""

import logging
from datetime import UTC, datetime
from typing import Any

from firebase_admin import messaging

from app.core.exceptions import AppError, ForbiddenError, NotFoundError, ValidationError
from app.models.base import db
from app.models.enum import StatusSolicitacao, UserRole, UserStatus
from app.models.notificacao import Notificacao
from app.models.rota import RotaAluno
from app.models.user import Aluno, User
from app.models.viagem import AlunosConfirmados, Viagem
from app.utils import audit_logger

logger = logging.getLogger(__name__)


class NotificacaoService:

    @staticmethod
    def _criar_notificacao_interna(usuario_id: str, titulo: str, mensagem: str) -> Notificacao:
        nova = Notificacao(
            usuario_id=usuario_id,
            titulo=titulo,
            mensagem=mensagem,
            data_envio=datetime.now(UTC),
        )
        db.session.add(nova)

        usuario = db.session.get(User, usuario_id)

        if usuario and getattr(usuario, "fcm_token", None):
            try:
                mensagem_fcm = messaging.Message(
                    notification=messaging.Notification(
                        title=titulo,
                        body=mensagem,
                    ),
                    token=usuario.fcm_token,
                )
                response = messaging.send(mensagem_fcm)
                logger.info(f"Push enviado com sucesso para {usuario.email}. ID: {response}")

            except Exception as e:
                logger.error(
                    f"Falha ao enviar Push Notification via Firebase para {usuario.email}: {str(e)}"
                )

        return nova

    @staticmethod
    def notificar_por_gestor(user_id: str, dados: dict[str, Any]) -> dict[str, Any]:
        user = db.session.get(User, user_id)
        if not user:
            raise ForbiddenError("Usuário não encontrado.")

        viagem_id = dados.get("viagem_id")

        # Motoristas can broadcast to their own active trip only
        if user.role == UserRole.MOTORISTA:
            if not viagem_id:
                raise ForbiddenError("Motoristas devem informar viagem_id para enviar avisos.")
            viagem = db.session.get(Viagem, viagem_id)
            if not viagem or str(viagem.motorista_id) != str(user_id):
                raise ForbiddenError(
                    "Você só pode enviar avisos para viagens que você está conduzindo."
                )
            from app.models.enum import StatusViagem

            if viagem.status != StatusViagem.EM_ANDAMENTO:
                raise ForbiddenError("Você só pode enviar avisos durante uma viagem em andamento.")
        elif user.role != UserRole.GESTOR:
            raise ForbiddenError("Apenas gestores ou motoristas podem enviar comunicados.")

        titulo = dados.get("titulo")
        mensagem = dados.get("mensagem")
        rota_id = dados.get("rota_id")
        viagem_id = dados.get("viagem_id")

        if not titulo or not mensagem:
            raise ValidationError("Título e mensagem são obrigatórios.")

        usuarios_notificados = set()

        if rota_id:
            # Fluxo programado herdado: o público de uma *rota* é a lista de
            # inscritos. A rodada sob demanda não tem inscrição permanente —
            # nela o público é o da rodada, endereçado por viagem_id abaixo.
            inscricoes = RotaAluno.query.filter_by(rota_id=rota_id).all()
            for insc in inscricoes:
                usuarios_notificados.add(insc.aluno_id)
        elif viagem_id:
            # Numa rodada sob demanda o interessado ainda sem trajeto declarado
            # também precisa receber o aviso, então o corte é por status, não
            # pelo booleano de confirmação do fluxo programado.
            participantes = AlunosConfirmados.query.filter(
                AlunosConfirmados.viagem_id == viagem_id,
                AlunosConfirmados.status != StatusSolicitacao.CANCELADO,
            ).all()
            for conf in participantes:
                if conf.confirmacao or conf.status == StatusSolicitacao.INTERESSADO:
                    usuarios_notificados.add(conf.aluno_id)
        else:
            raise ValidationError("Informe o ID de uma rota (rota_id) ou viagem (viagem_id).")

        if not usuarios_notificados:
            raise NotFoundError("Nenhum aluno encontrado para receber este aviso.")

        try:
            for aluno_id in usuarios_notificados:
                NotificacaoService._criar_notificacao_interna(aluno_id, titulo, mensagem)

            db.session.commit()
            audit_logger.log_user_action(
                action="enviar_notificacao_massa", user_id=user_id, resource_type="notificacao"
            )

            return {
                "message": f"Notificação enviada para {len(usuarios_notificados)} aluno(s) com sucesso."
            }

        except Exception as e:
            db.session.rollback()
            logger.error(f"Erro ao disparar notificações: {e}")
            raise AppError(f"Erro ao enviar notificações: {str(e)}", 500)

    @staticmethod
    def listar_notificacoes(user_id: str) -> list[Notificacao]:
        """Lista avisos do usuário logado"""
        return (
            Notificacao.query.filter_by(usuario_id=user_id)
            .order_by(Notificacao.created_at.desc())
            .all()
        )

    @staticmethod
    def marcar_lida(user_id: str, notificacao_id: str) -> dict[str, str]:
        notificacao = db.session.get(Notificacao, notificacao_id)
        if not notificacao or str(notificacao.usuario_id) != str(user_id):
            raise NotFoundError("Notificação não encontrada.")

        try:
            notificacao.enviada = True
            db.session.commit()
            return {"message": "Notificação marcada como lida."}
        except Exception as e:
            db.session.rollback()
            raise AppError(f"Erro ao atualizar notificação: {str(e)}", 500)

    # ==========================================
    # Rodada sob demanda (RF-10 a RF-12, RF-15, RF-19)
    # ==========================================
    #
    # Nenhum dos métodos abaixo faz commit: são chamados de dentro da transação
    # que muda o estado da rodada, e a notificação não pode sobreviver a um
    # rollback dessa mudança.

    @staticmethod
    def notificar_motorista_demanda(viagem: Viagem) -> None:
        """RF-10: a primeira solicitação da rodada chama o motorista."""
        if not viagem.motorista_id:
            logger.warning(f"Rodada {viagem.id} sem motorista: demanda não notificada")
            return

        NotificacaoService._criar_notificacao_interna(
            usuario_id=viagem.motorista_id,
            titulo="🚌 Há demanda para o veículo",
            mensagem="Um aluno solicitou o veículo. Inicie o percurso para abrir a janela de declarações.",
        )

    @staticmethod
    def _alunos_aptos(organizacao_id: Any) -> list[Aluno]:
        """RF-12: aluno apto é o autenticável da organização, com consentimento
        vigente e que aceita notificações."""
        from app.services import consentimento_service

        alunos = (
            db.session.query(Aluno)
            .filter(Aluno.organizacao_id == organizacao_id, Aluno.status != UserStatus.DISABLED)
            .all()
        )
        # ponytail: uma consulta de consentimento por aluno. O circuito tem
        # dezenas de alunos, não milhares; se virar gargalo, troque por um JOIN
        # com consentimento na versão vigente do termo.
        return [
            a
            for a in alunos
            if getattr(a, "receber_notificacoes", True)
            and consentimento_service.tem_consentimento_vigente(str(a.usuario_id))
        ]

    @staticmethod
    def notificar_broadcast_buffer(viagem: Viagem, segundos_restantes: int) -> int:
        """RF-12: broadcast da abertura do buffer, com o tempo que resta."""
        rota = viagem.rota or (viagem.horario_rota.rota if viagem.horario_rota else None)
        if not rota:
            return 0

        minutos = max(1, round(segundos_restantes / 60))
        destinatarios = NotificacaoService._alunos_aptos(rota.organizacao_id)

        for aluno in destinatarios:
            NotificacaoService._criar_notificacao_interna(
                usuario_id=aluno.usuario_id,
                titulo="🚌 O veículo vai sair!",
                mensagem=(
                    f"O percurso começa em {minutos} min. "
                    "Declare seu ponto de embarque e desembarque agora para garantir a vaga."
                ),
            )

        return len(destinatarios)

    @staticmethod
    def notificar_gestor_demanda_nao_atendida(viagem: Viagem) -> None:
        """RF-11 fluxo secundário 1: motorista não iniciou dentro do prazo."""
        rota = viagem.rota
        if not rota:
            return

        gestores = (
            db.session.query(User)
            .filter_by(organizacao_id=rota.organizacao_id, role=UserRole.GESTOR)
            .all()
        )
        for gestor in gestores:
            NotificacaoService._criar_notificacao_interna(
                usuario_id=gestor.id,
                titulo="⚠️ Demanda sem atendimento",
                mensagem=(
                    f"Há solicitações no circuito {rota.nome} e o motorista não iniciou o "
                    "percurso dentro do prazo. Trate a demanda manualmente."
                ),
            )

    @staticmethod
    def notificar_motorista_desistencia(viagem: Viagem, aluno_nome: str) -> None:
        """RF-19 fluxo secundário 1: desistência depois da partida é no-show."""
        if not viagem.motorista_id:
            return

        NotificacaoService._criar_notificacao_interna(
            usuario_id=viagem.motorista_id,
            titulo="Passageiro desistiu",
            mensagem=f"{aluno_nome} não vai embarcar nesta rodada. A vaga não foi reaberta.",
        )

    @staticmethod
    def notificar_rodada_cancelada(viagem: Viagem) -> None:
        """RF-15 fluxo secundário 1: buffer encerrou sem nenhum embarque."""
        if not viagem.motorista_id:
            return

        NotificacaoService._criar_notificacao_interna(
            usuario_id=viagem.motorista_id,
            titulo="Rodada cancelada",
            mensagem="O tempo do buffer acabou sem embarques confirmados. O veículo volta a ficar ocioso.",
        )

    @staticmethod
    def notificar_rodada_consolidada(viagem: Viagem, alunos_ids: list[Any]) -> None:
        """Fim do buffer com embarques: avisa motorista e passageiros."""
        if viagem.motorista_id:
            NotificacaoService._criar_notificacao_interna(
                usuario_id=viagem.motorista_id,
                titulo="🚌 Roteiro fechado",
                mensagem=f"A rodada começou com {len(alunos_ids)} passageiro(s) confirmado(s).",
            )

        for aluno_id in alunos_ids:
            NotificacaoService._criar_notificacao_interna(
                usuario_id=aluno_id,
                titulo="✅ Embarque confirmado",
                mensagem="O veículo saiu para o percurso. Acompanhe a viagem pelo aplicativo.",
            )

    @staticmethod
    def notificar_alunos_viagem_iniciada(viagem_id: str) -> None:
        """Busca os alunos confirmados na viagem e dispara o aviso de partida."""
        try:
            confirmados = AlunosConfirmados.query.filter_by(
                viagem_id=viagem_id, confirmacao=True
            ).all()

            for conf in confirmados:
                NotificacaoService._criar_notificacao_interna(
                    usuario_id=conf.aluno_id,
                    titulo="🚌 Viagem Iniciada!",
                    mensagem="O motorista acabou de iniciar a rota. Acompanhe o trajeto no aplicativo!",
                )

            db.session.commit()
        except Exception as e:
            db.session.rollback()
            logger.error(
                f"Falha ao orquestrar notificações de início da viagem {viagem_id}: {str(e)}"
            )
