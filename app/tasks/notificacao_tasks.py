import logging
from datetime import datetime, timedelta

from app.models.base import db
from app.models.enum import StatusViagem
from app.models.rota import RotaAluno
from app.models.user import Aluno, User
from app.models.viagem import AlunosConfirmados, Viagem
from app.services.notificacao_service import NotificacaoService
from app.utils import tempo

logger = logging.getLogger(__name__)

# Job intervals, in minutes (used by scheduler_setup).
INTERVALO_JOB_24H_MINUTOS = 60
INTERVALO_JOB_10MIN_MINUTOS = 10

# Each send window is wider than its job interval, so one run always lands inside it.
# 24h reminder: between 25h and 23h before departure (2h window, job every 1h).
JANELA_24H_INICIO = timedelta(hours=25)
JANELA_24H_FIM = timedelta(hours=23)
# 10min reminder: between 20 and 5 min before departure (15 min window, job every 10 min).
JANELA_10MIN_INICIO = timedelta(minutes=20)
JANELA_10MIN_FIM = timedelta(minutes=5)


def _partida_local(viagem: Viagem, agora_local: datetime) -> datetime:
    # Trip date and time are stored in the app's local time (TIMEZONE setting).
    return datetime.combine(
        viagem.data, viagem.horario_rota.horario_saida, tzinfo=agora_local.tzinfo
    )


def verificar_viagens_24h(app):
    """Job: notifies students 24 hours before the trip"""
    with app.app_context():
        agora = tempo.agora_local()

        viagens = Viagem.query.filter(
            Viagem.status == StatusViagem.AGENDADA,
            # on-demand trips have no timetable, so no reminders
            Viagem.horario_rota_id.isnot(None),
            Viagem.aviso_24h_enviado.is_(False),
            Viagem.data >= agora.date(),
            Viagem.data <= (agora + JANELA_24H_INICIO).date(),
        ).all()

        for viagem in viagens:
            partida = _partida_local(viagem, agora)
            ainda_cedo = agora < partida - JANELA_24H_INICIO
            # Also skips trips created after the window: "amanhã" would be wrong for them,
            # and the driver's 10min reminder still goes out.
            tarde_demais = agora >= partida - JANELA_24H_FIM
            if ainda_cedo or tarde_demais:
                continue

            rota_id = viagem.rota_id or viagem.horario_rota.rota_id
            inscricoes = RotaAluno.query.filter_by(rota_id=rota_id).all()

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
    """Job: notifies the driver 10 min before with the list of universities"""
    with app.app_context():
        agora = tempo.agora_local()

        viagens = Viagem.query.filter(
            Viagem.status == StatusViagem.AGENDADA,
            Viagem.horario_rota_id.isnot(None),
            Viagem.motorista_id.isnot(None),
            Viagem.aviso_10min_enviado.is_(False),
            Viagem.data >= agora.date(),
            Viagem.data <= (agora + JANELA_10MIN_INICIO).date(),
        ).all()

        for viagem in viagens:
            partida = _partida_local(viagem, agora)
            ainda_cedo = agora < partida - JANELA_10MIN_INICIO
            tarde_demais = agora >= partida - JANELA_10MIN_FIM
            if ainda_cedo or tarde_demais:
                continue

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
