"""Credencial de embarque (QR dinâmico, RF-15).

Recebe uma decisão de embarque já tomada por outra parte do sistema e emite a
credencial correspondente. Não decide quem embarca.

O QR muda a cada `QR_PASSO_SEGUNDOS`: o app do aluno recebe o segredo da
credencial e calcula o código do passo corrente sem rede (TOTP, RFC 6238, com
HMAC-SHA1). O QR é `<credencial_id>.<codigo>`, então uma captura de tela deixa
de valer em poucos segundos. As regras de embarque que usam a credencial ficam
em `embarque_service`.
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
    """
    Gera a credencial de embarque de um aluno já confirmado numa viagem.

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
    """A credencial não revogada do aluno na viagem; o índice único garante no máximo uma."""
    return CredencialEmbarque.query.filter_by(
        viagem_id=viagem_id, aluno_id=aluno_id, revogada_em=None
    ).one_or_none()


def criar_credencial(viagem_id, aluno_id, ponto_embarque_id) -> CredencialEmbarque:
    """
    Cria a credencial na transação de quem chamou, sem commit.

    Idempotente por (viagem, aluno): se já existe uma ativa para o mesmo ponto,
    devolve ela. Se o ponto mudou, revoga a antiga e emite outra, porque a
    credencial vale só para o ponto em que foi emitida.
    """
    agora = tempo.agora_utc()

    atual = credencial_ativa(viagem_id, aluno_id)
    if atual is not None:
        if str(atual.ponto_embarque_id) == str(ponto_embarque_id):
            return atual
        atual.revogada_em = agora
        # O índice único só aceita a nova depois que a antiga está revogada no banco.
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
    """
    Busca a credencial de embarque do aluno autenticado para uma viagem, para
    o app do passageiro gerar o QR.

    Vale a credencial do ponto em que o aluno está hoje na lista de embarque.

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
    """HOTP (RFC 4226) do contador; com o contador do passo de tempo, é o TOTP da RFC 6238."""
    resumo = hmac.new(segredo, contador.to_bytes(8, "big"), hashlib.sha1).digest()
    deslocamento = resumo[-1] & 0x0F
    numero = int.from_bytes(resumo[deslocamento : deslocamento + 4], "big") & 0x7FFFFFFF
    return str(numero % (10**digitos)).zfill(digitos)


def codigo_confere(credencial: CredencialEmbarque, codigo: str, momento: datetime) -> bool:
    """O código vale no passo de `momento` ou até `QR_JANELA_PASSOS` antes ou depois."""
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
    """`<credencial_id>.<codigo>` em (id, código); None se o formato não bate."""
    credencial_id, _, codigo = (qr or "").strip().partition(".")
    if not codigo.isdigit():
        return None
    try:
        return uuid.UUID(credencial_id), codigo
    except ValueError:
        return None
