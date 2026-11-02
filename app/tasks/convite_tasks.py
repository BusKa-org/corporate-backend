import logging

from app.extensions import scheduler
from app.services.convite_service import processar_envios

logger = logging.getLogger(__name__)


def enviar_convites_pendentes():
    """Job: sends the queued invite e-mails."""
    # No `args=[app]`: the shared jobstore pickles the job, and the Flask object is
    # not picklable. The app comes from the scheduler itself.
    app = scheduler.app
    if not app:
        logger.error("Erro fatal: Instância do Flask (app) não encontrada no Scheduler.")
        return

    with app.app_context():
        processar_envios()
