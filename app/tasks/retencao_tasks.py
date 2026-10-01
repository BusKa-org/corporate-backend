import logging

from app.extensions import scheduler
from app.services.conta_service import anonimizar_retencoes_vencidas

logger = logging.getLogger(__name__)


def job_anonimizar_retencoes():
    """Job diário: anonimiza e-mail e CPF retidos cujo prazo de retenção acabou."""
    # Sem `args=[app]`: o jobstore compartilhado serializa o job com pickle, e o objeto
    # Flask não serializa. O app vem do próprio agendador.
    app = scheduler.app
    if not app:
        logger.error("Erro fatal: Instância do Flask (app) não encontrada no Scheduler.")
        return

    with app.app_context():
        quantidade = anonimizar_retencoes_vencidas()
        logger.info("Retenção legal: %d linha(s) anonimizada(s).", quantidade)
