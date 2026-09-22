"""Credencial de embarque (QR dinâmico) — RF-15.

Recebe uma decisão de embarque já tomada por outra parte do sistema e emite
ou valida a credencial correspondente. Não decide quem embarca.
"""

import secrets
from datetime import UTC, datetime, timedelta

from app.core.exceptions import NotFoundError, ValidationError
from app.core.transaction import transactional
from app.models.base import db
from app.models.credencial_embarque import CredencialEmbarque
from app.models.enum import StatusViagem
from app.models.viagem import Viagem

# ponytail: janela fixa até o Plan 2 (ciclo de vida da viagem) dar um sinal
# real de duração da viagem; ajustar quando esse sinal existir.
EXPIRACAO_PADRAO = timedelta(hours=4)


def gerar_credencial(viagem_id: str, aluno_id: str, ponto_embarque_id: str) -> CredencialEmbarque:
    """
    Gera a credencial de embarque de um aluno já confirmado numa viagem.

    Raises: NotFoundError, ValidationError, ConflictError (via transactional())
    """
    with transactional():
        viagem = db.session.get(Viagem, viagem_id)
        if not viagem:
            raise NotFoundError("Viagem não encontrada")

        if viagem.status in (StatusViagem.CANCELADA, StatusViagem.FINALIZADA):
            raise ValidationError("Viagem cancelada ou finalizada não emite credencial de embarque")

        credencial = CredencialEmbarque(
            viagem_id=viagem_id,
            aluno_id=aluno_id,
            ponto_embarque_id=ponto_embarque_id,
            token=secrets.token_urlsafe(32),
            expires_at=datetime.now(UTC) + EXPIRACAO_PADRAO,
        )
        db.session.add(credencial)
        db.session.flush()

        return credencial


def validar_credencial(token: str) -> CredencialEmbarque:
    """
    Confere se um token de embarque existe, não foi usado e não expirou.

    Não marca a credencial como usada nem compara a foto do passageiro:
    isso é do RF-17, fora deste serviço. Só leitura, sem efeito colateral.

    Raises: NotFoundError, ValidationError
    """
    credencial = CredencialEmbarque.query.filter_by(token=token).first()
    if not credencial:
        raise NotFoundError("Credencial de embarque não encontrada")

    if credencial.usado:
        raise ValidationError("Credencial de embarque já foi usada")

    if credencial.is_expired():
        raise ValidationError("Credencial de embarque expirada")

    return credencial
