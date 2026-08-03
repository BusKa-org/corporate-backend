import logging
from datetime import datetime, timedelta

from app.models.base import db
from app.models.enum import StatusViagem
from app.models.rota import RotaAluno
from app.models.user import Aluno, User
from app.models.viagem import AlunosConfirmados, Viagem
from app.services.notificacao_service import NotificacaoService

logger = logging.getLogger(__name__)


def verificar_viagens_24h(app):
    """Job: Notifica alunos 24 horas antes da viagem"""
    with app.app_context():
        agora = datetime.now()
        amanha_inicio = agora + timedelta(hours=23, minutes=50)
        amanha_fim = agora + timedelta(hours=24, minutes=10)

        viagens = Viagem.query.filter(
            Viagem.status == StatusViagem.AGENDADA,
            Viagem.aviso_24h_enviado.is_(False),
            Viagem.data >= amanha_inicio.date(),
            Viagem.data <= amanha_fim.date(),
        ).all()

        for viagem in viagens:
            if not viagem.horario_rota:
                continue
            inscricoes = RotaAluno.query.filter_by(rota_id=viagem.horario_rota.rota_id).all()

            for insc in inscricoes:
                aluno = db.session.get(User, insc.aluno_id)
                if aluno and getattr(aluno, "receber_notificacoes", True):
                    NotificacaoService._criar_notificacao_interna(
                        usuario_id=aluno.id,
                        titulo="⏰ Lembrete de Viagem",
                        mensagem="A sua viagem da rota está agendada para amanhã. Não se esqueça de confirmar a sua presença no percurso!",
                    )

            viagem.aviso_24h_enviado = True

        try:
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            logger.error(f"Erro no Job de 24h: {e}")


def verificar_viagens_10min(app):
    """Job: Notifica o motorista 10 min antes com a lista de universidades"""
    with app.app_context():
        agora = datetime.now()

        viagens = Viagem.query.filter(
            Viagem.status == StatusViagem.AGENDADA,
            Viagem.aviso_10min_enviado.is_(False),
            Viagem.data == agora.date(),
        ).all()

        for viagem in viagens:
            confirmados = AlunosConfirmados.query.filter_by(
                viagem_id=viagem.id, confirmacao=True
            ).all()

            universidades = set()
            for conf in confirmados:
                aluno = db.session.get(Aluno, conf.aluno_id)

                if aluno and getattr(aluno, "instituicao", None):
                    universidades.add(aluno.instituicao.nome)

            lista_univ = ", ".join(universidades) if universidades else "Nenhum aluno confirmado"

            NotificacaoService._criar_notificacao_interna(
                usuario_id=viagem.motorista_id,
                titulo="🚌 Viagem a iniciar em 10 minutos",
                mensagem=f"Prepare-se! As paragens universitárias desta viagem serão: {lista_univ}.",
            )

            viagem.aviso_10min_enviado = True

        try:
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            logger.error(f"Erro no Job de 10min: {e}")
