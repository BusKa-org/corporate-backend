import logging

from app.extensions import scheduler
from app.services.conta_service import anonimizar_retencoes_vencidas

logger = logging.getLogger(__name__)


def job_anonimizar_retencoes():
    """Quarterly job: anonymizes retained e-mail and CPF whose retention period is over.

    Nothing expires before 10 years, so once every 3 months is enough. Expired data
    waits at most 3 months for anonymization.
    """
    # No `args=[app]`: the shared jobstore pickles the job, and the Flask object is
    # not picklable. The app comes from the scheduler itself.
    app = scheduler.app
    if not app:
        logger.error("Erro fatal: Instância do Flask (app) não encontrada no Scheduler.")
        return

    with app.app_context():
        quantidade = anonimizar_retencoes_vencidas()
        logger.info("Retenção legal: %d linha(s) anonimizada(s).", quantidade)
