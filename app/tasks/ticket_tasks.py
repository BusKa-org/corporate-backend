import logging
from datetime import UTC, datetime

from app.models.base import db
from app.models.enum import TipoPoliticaTicket
from app.models.ticket import PoliticaTicket, SaldoTicket
from app.services.ticket_saldo import calcular_saldo
from app.services.ticket_service import avisar_passageiro

logger = logging.getLogger(__name__)

LIMITE_POR_EXECUCAO = 500


def avisar_tickets_recarregados(app):
    """Job: avisa quem ficou sem tickets e já recebeu de volta pela recarga ou pela nova janela.

    A conta do saldo continua sendo feita na leitura. Este job só decide quando notificar.
    """
    with app.app_context():
        agora = datetime.now(UTC)

        # skip_locked: quem está confirmando uma viagem agora fica para a próxima execução.
        pendentes = (
            SaldoTicket.query.filter(SaldoTicket.aguardando_aviso.is_(True))
            .with_for_update(skip_locked=True)
            .limit(LIMITE_POR_EXECUCAO)
            .all()
        )

        for saldo in pendentes:
            politica = db.session.get(PoliticaTicket, saldo.politica_id)
            if politica is None or politica.tipo == TipoPoliticaTicket.ILIMITADO:
                saldo.aguardando_aviso = False
                continue

            quantidade, referencia_em = calcular_saldo(
                politica, saldo.quantidade, saldo.referencia_em, agora
            )
            if quantidade + saldo.bonus == 0:
                continue

            saldo.quantidade = quantidade
            saldo.referencia_em = referencia_em
            saldo.aguardando_aviso = False
            avisar_passageiro(
                saldo.usuario_id,
                "Tickets recarregados",
                f"Você já tem tickets da política {politica.nome} para confirmar viagens.",
            )

        try:
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            logger.error(f"Erro no job de recarga de tickets: {e}")
