"""Boarding credential (dynamic QR, RF-15).

Receives a boarding decision already made elsewhere in the system and issues
the matching credential. It does not decide who boards.

The QR changes every `QR_PASSO_SEGUNDOS`: the student app receives the
credential secret and computes the current step's code offline (TOTP, RFC 6238,
HMAC-SHA1). The QR is `<credencial_id>.<codigo>`, so a screenshot stops working
within seconds. The boarding rules that use the credential live in `embarque_service`.
"""

import hashlib
import hmac
import secrets
import uuid
from datetime import datetime, timedelta
from typing import Any

from flask import current_app

from app.core.exceptions import ForbiddenError, NotFoundError, ValidationError
from app.core.transaction import transactional
from app.models.base import db
from app.models.credencial_embarque import CredencialEmbarque
from app.models.enum import StatusViagem, UserRole
from app.models.user import User
from app.models.viagem import AlunosConfirmados, Viagem
from app.utils import tempo

EXPIRACAO_PADRAO = timedelta(hours=4)


def gerar_credencial(viagem_id: str, aluno_id: str, ponto_embarque_id: str) -> CredencialEmbarque:
    """Generate the boarding credential of a student already confirmed on a trip.

    Raises: NotFoundError, ValidationError
    """
    with transactional():
        viagem = db.session.get(Viagem, viagem_id)
        if not viagem:
            raise NotFoundError("Viagem não encontrada")

        if viagem.status in (StatusViagem.CANCELADA, StatusViagem.FINALIZADA):
            raise ValidationError("Viagem cancelada ou finalizada não emite credencial de embarque")

        return criar_credencial(viagem_id, aluno_id, ponto_embarque_id)


def credencial_ativa(viagem_id, aluno_id) -> CredencialEmbarque | None:
    """The student's non-revoked credential on the trip; the unique index guarantees at most one."""
    return CredencialEmbarque.query.filter_by(
        viagem_id=viagem_id, aluno_id=aluno_id, revogada_em=None
    ).one_or_none()


def criar_credencial(viagem_id, aluno_id, ponto_embarque_id) -> CredencialEmbarque:
    """Create the credential in the caller's transaction, without committing.

    Idempotent per (trip, student): if an active one already exists for the same
    stop, it is returned. If the stop changed, the old one is revoked and a new one
    issued, because a credential is only valid for the stop it was issued for.
    """
    agora = tempo.agora_utc()

    atual = credencial_ativa(viagem_id, aluno_id)
    if atual is not None:
        if str(atual.ponto_embarque_id) == str(ponto_embarque_id):
            return atual
        atual.revogada_em = agora
        # The unique index only accepts the new one after the old one is revoked in the database.
        db.session.flush()

    credencial = CredencialEmbarque(
        viagem_id=viagem_id,
        aluno_id=aluno_id,
        ponto_embarque_id=ponto_embarque_id,
        segredo=secrets.token_hex(32),
        created_at=agora,
        expires_at=agora + EXPIRACAO_PADRAO,
    )
    db.session.add(credencial)
    db.session.flush()
    return credencial


def buscar_credencial_do_aluno(user_id: str, viagem_id: str) -> dict[str, Any]:
    """Get the authenticated student's boarding credential for a trip, for the app to draw the QR.

    The credential that counts is the one for the stop the student is on today in the boarding list.

    Raises: ForbiddenError, NotFoundError
    """
    user = db.session.get(User, user_id)
    if not user or user.role != UserRole.ALUNO:
        raise ForbiddenError("Acesso restrito a alunos")

    try:
        viagem_uuid = uuid.UUID(str(viagem_id))
    except ValueError as e:
        raise NotFoundError("Credencial de embarque não encontrada") from e

    registro = db.session.get(AlunosConfirmados, (viagem_uuid, user.id))
    credencial = credencial_ativa(viagem_uuid, user.id)
    if registro is None or credencial is None:
        raise NotFoundError("Credencial de embarque não encontrada")
    if credencial.ponto_embarque_id != registro.ponto_embarque_id:
        raise NotFoundError("Credencial de embarque não encontrada")

    return {
        "credencial_id": credencial.id,
        "segredo": credencial.segredo,
        "algoritmo": "SHA1",
        "passo_segundos": current_app.config["QR_PASSO_SEGUNDOS"],
        "digitos": current_app.config["QR_DIGITOS"],
        "ponto_embarque_id": credencial.ponto_embarque_id,
        "expires_at": credencial.expires_at,
        "usado": credencial.usado,
    }


def gerar_codigo(segredo: bytes, contador: int, digitos: int) -> str:
    """HOTP (RFC 4226) of the counter; with the time-step counter, it is the RFC 6238 TOTP."""
    resumo = hmac.new(segredo, contador.to_bytes(8, "big"), hashlib.sha1).digest()
    deslocamento = resumo[-1] & 0x0F
    numero = int.from_bytes(resumo[deslocamento : deslocamento + 4], "big") & 0x7FFFFFFF
    return str(numero % (10**digitos)).zfill(digitos)


def codigo_confere(credencial: CredencialEmbarque, codigo: str, momento: datetime) -> bool:
    """The code is valid at the `momento` step or up to `QR_JANELA_PASSOS` before or after."""
    passo = current_app.config["QR_PASSO_SEGUNDOS"]
    digitos = current_app.config["QR_DIGITOS"]
    janela = current_app.config["QR_JANELA_PASSOS"]

    segredo = bytes.fromhex(credencial.segredo)
    contador = int(momento.timestamp()) // passo
    confere = False
    for desvio in range(-janela, janela + 1):
        esperado = gerar_codigo(segredo, contador + desvio, digitos)
        if hmac.compare_digest(esperado, codigo):
            confere = True
    return confere


def separar_qr(qr: str) -> tuple[uuid.UUID, str] | None:
    """`<credencial_id>.<codigo>` into (id, code); None if the format does not match."""
    credencial_id, _, codigo = (qr or "").strip().partition(".")
    if not codigo.isdigit():
        return None
    try:
        return uuid.UUID(credencial_id), codigo
    except ValueError:
        return None
