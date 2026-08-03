"""Background tasks for trip management, including automated geofence-based check-ins."""

import logging
from datetime import UTC, datetime, timedelta

from app.extensions import scheduler
from app.models.base import db
from app.models.viagem import AlunosConfirmados, Viagem
from app.services.notificacao_service import NotificacaoService
from app.utils.geo_utils import calcular_distancia_metros

logger = logging.getLogger(__name__)


def realizar_auto_checkin(viagem_id: str, aluno_id: str, tentativa: int) -> None:
    """
    Verifica o embarque do aluno comparando GPS.
    """
    if tentativa > 3:
        logger.warning(
            f"Auto-checkin abortado: Limite de tentativas excedido para o aluno {aluno_id}"
        )
        return

    app = scheduler.app

    if not app:
        logger.error("Erro fatal: Instância do Flask (app) não encontrada no Scheduler.")
        return

    with app.app_context():
        conf = AlunosConfirmados.query.filter_by(viagem_id=viagem_id, aluno_id=aluno_id).first()
        viagem = db.session.get(Viagem, viagem_id)

        if not conf or not viagem or conf.embarcou:
            return

        agora = datetime.now(UTC)
        DISTANCIA_EMBARQUE = 50

        if conf.aluno_lat and viagem.motorista_lat:
            distancia = calcular_distancia_metros(
                viagem.motorista_lat, viagem.motorista_lon, conf.aluno_lat, conf.aluno_lon
            )

            if distancia <= DISTANCIA_EMBARQUE:
                conf.embarcou = True
                db.session.commit()

                NotificacaoService._criar_notificacao_interna(
                    usuario_id=aluno_id,
                    titulo="✅ Embarque Confirmado!",
                    mensagem="Detectamos você no ônibus. Boa viagem!",
                )
                return

        if tentativa < 3:
            conf.tentativas_auto_checkin = tentativa
            db.session.commit()

            nova_data = agora + timedelta(minutes=5)
            job_id = f"checkin_{viagem_id}_{aluno_id}_{tentativa+1}"

            scheduler.add_job(
                id=job_id,
                func=realizar_auto_checkin,
                args=[viagem_id, aluno_id, tentativa + 1],
                trigger="date",
                run_date=nova_data,
            )
