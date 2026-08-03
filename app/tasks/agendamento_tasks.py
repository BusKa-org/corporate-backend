import logging

from app.models.enum import UserRole
from app.models.user import User
from app.services.viagens_service import gerar_viagens_periodo

logger = logging.getLogger(__name__)


def job_gerar_viagens_semanais(app):
    """Job diário que mantém a agenda dos próximos 14 dias preenchida."""
    with app.app_context():
        logger.info("Job de geração de viagens iniciado.")

        try:
            gestores = User.query.filter_by(role=UserRole.GESTOR).distinct(User.prefeitura_id).all()
        except Exception as e:
            logger.error(f"Erro ao buscar gestores no job de geração de viagens: {e}")
            return

        total = 0
        for gestor in gestores:
            # Um gestor com problema não pode derrubar a agenda das outras prefeituras.
            try:
                total += gerar_viagens_periodo(gestor_id=str(gestor.id), dias_futuros=14)
            except Exception as e:
                logger.error(f"Erro ao gerar viagens para o gestor {gestor.id}: {e}")

        logger.info(
            f"Job de geração de viagens concluído: "
            f"{total} viagens criadas para {len(gestores)} gestores."
        )
