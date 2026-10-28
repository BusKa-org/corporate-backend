import logging

from app.extensions import scheduler
from app.services.convite_service import processar_envios

logger = logging.getLogger(__name__)


def enviar_convites_pendentes():
    """Job: envia os e-mails de convite que estão na fila."""
    # Sem `args=[app]`: o jobstore compartilhado serializa o job com pickle, e o objeto
    # Flask não serializa. O app vem do próprio agendador.
    app = scheduler.app
    if not app:
        logger.error("Erro fatal: Instância do Flask (app) não encontrada no Scheduler.")
        return

    with app.app_context():
        processar_envios()
