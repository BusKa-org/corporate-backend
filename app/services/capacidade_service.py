"""Capacity check per circuit segment (RF-13, RF-14, RF-19).

The circuit has n ordered stops, so n-1 segments. A route Pi -> Pj takes
segments i-1 .. j-2 (0-based vector indexes). The request is accepted if
`PicoTrecho = max(C[i-1:j-1])` is below the vehicle capacity; seats free up
after drop-off, so disjoint routes reuse the same seat.

The vector is derived from ATIVA requests with a declared route. Cancelling
(CANCELADA) gives the segments back; dropping out after departure does not
reopen the seat because the buffer is already closed and no one declares anymore.
"""

import logging
import uuid

from sqlalchemy import select

from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError, ValidationError
from app.core.transaction import transactional
from app.models.base import db
from app.models.enum import StatusSolicitacao, StatusViagem, UserStatus
from app.models.rota import Rota
from app.models.user import Aluno
from app.models.viagem import SolicitacaoViagem, Viagem
from app.utils import tempo
from app.utils.validators import validate_uuid

logger = logging.getLogger(__name__)

IdLike = str | uuid.UUID


def _get_viagem(viagem_id: IdLike) -> Viagem:
    viagem = db.session.get(Viagem, validate_uuid(str(viagem_id), "ID da viagem"))
    if not viagem:
        raise NotFoundError("Viagem não encontrada")
    return viagem


def _rota_da_viagem(viagem: Viagem) -> Rota:
    rota = viagem.rota or (viagem.horario_rota.rota if viagem.horario_rota else None)
    if not rota:
        raise ValidationError("Viagem sem circuito de pontos definido")
    return rota


def _pontos_ordenados(rota: Rota) -> list[uuid.UUID]:
    # `pontos_padrao` is already ordered by RotaPonto.ordem.
    return [rp.ponto_id for rp in rota.pontos_padrao]


def _capacidade(viagem: Viagem, rota: Rota) -> int:
    veiculo = viagem.veiculo or rota.veiculo_padrao
    if not veiculo:
        raise ValidationError("Viagem sem veículo definido: capacidade desconhecida")
    return int(veiculo.capacidade)


def _carga(
    viagem_id: uuid.UUID,
    pontos: list[uuid.UUID],
    excluir_solicitacao_id: uuid.UUID | None = None,
) -> list[int]:
    """Rebuild the vector from the ATIVA requests with a declared route."""
    posicao = {ponto_id: k for k, ponto_id in enumerate(pontos)}
    vetor = [0] * max(len(pontos) - 1, 0)

    aceitas = (
        db.session.query(SolicitacaoViagem)
        .filter(
            SolicitacaoViagem.viagem_id == viagem_id,
            SolicitacaoViagem.status == StatusSolicitacao.ATIVA,
            SolicitacaoViagem.ponto_embarque_id.isnot(None),
        )
        .all()
    )
    for linha in aceitas:
        if excluir_solicitacao_id is not None and linha.id == excluir_solicitacao_id:
            continue
        i = posicao.get(linha.ponto_embarque_id)
        j = posicao.get(linha.ponto_destino_id)
        if i is None or j is None or i >= j:
            continue
        for k in range(i, j):
            vetor[k] += 1

    return vetor


def _posicao(posicoes: dict[uuid.UUID, int], ponto_id: IdLike, rotulo: str) -> int:
    k = posicoes.get(validate_uuid(str(ponto_id), rotulo))
    if k is None:
        raise ValidationError(f"{rotulo} não pertence ao circuito desta viagem")
    return k


def vetor_carga(viagem_id: IdLike) -> list[int]:
    """Occupancy per segment. Index k = leg between stop k+1 and k+2."""
    viagem = _get_viagem(viagem_id)
    return _carga(viagem.id, _pontos_ordenados(_rota_da_viagem(viagem)))


def capacidade_viagem(viagem_id: IdLike) -> int:
    """Seat limit: the capacity of the trip's vehicle."""
    viagem = _get_viagem(viagem_id)
    return _capacidade(viagem, _rota_da_viagem(viagem))


def exigir_conta_ativa(aluno_id: IdLike) -> None:
    """Call after the locks: an account deletion holding them may already have
    anonymized the student, so re-read from the database.
    """
    aluno = db.session.get(Aluno, aluno_id, populate_existing=True)
    if aluno is None or aluno.status != UserStatus.ACTIVE:
        raise ForbiddenError("Conta inativa")


def validar_e_reservar(
    viagem_id: IdLike,
    aluno_id: IdLike,
    ponto_origem_id: IdLike,
    ponto_destino_id: IdLike,
) -> SolicitacaoViagem:
    """RF-13/RF-14. Saves the route on the student's ATIVA request, or raises
    ConflictError if PicoTrecho is already at the limit. The denied request is set
    to NEGADA before the error, because RF-21 counts denials per stop.
    """
    negada = False

    with transactional():
        # shortcut: o RF-14 cita Redis; aqui as declarações concorrentes serializam
        # neste lock da viagem. Trocar por contador por segmento se virar gargalo.
        viagem = db.session.execute(
            select(Viagem)
            .where(Viagem.id == validate_uuid(str(viagem_id), "ID da viagem"))
            .with_for_update(key_share=True)
            # Whoever waited for the lock must see the status saved by the lock holder.
            .execution_options(populate_existing=True)
        ).scalar_one_or_none()
        if not viagem:
            raise NotFoundError("Viagem não encontrada")

        if viagem.status != StatusViagem.BUFFER_ABERTO:
            raise ValidationError("A viagem não está aceitando declarações de trajeto")

        exigir_conta_ativa(aluno_id)

        agora = tempo.agora_utc()
        if not viagem.buffer_fim or viagem.buffer_fim <= agora:
            raise ValidationError("O tempo para declarar o trajeto desta viagem já encerrou")

        solicitacao = (
            db.session.query(SolicitacaoViagem)
            .filter_by(viagem_id=viagem.id, aluno_id=aluno_id, status=StatusSolicitacao.ATIVA)
            .first()
        )
        if not solicitacao:
            raise NotFoundError("Solicite a viagem pela rota antes de declarar o trajeto")

        rota = _rota_da_viagem(viagem)
        if solicitacao.aluno.organizacao_id != rota.organizacao_id:
            raise ForbiddenError("Aluno não pertence à organização desta viagem")

        pontos = _pontos_ordenados(rota)
        posicoes = {ponto_id: k for k, ponto_id in enumerate(pontos)}
        i = _posicao(posicoes, ponto_origem_id, "Ponto de origem")
        j = _posicao(posicoes, ponto_destino_id, "Ponto de destino")
        if i >= j:
            raise ValidationError("A origem precisa vir antes do destino na ordem do circuito")

        # Redeclaring must not make the student compete with their own reservation.
        vetor = _carga(viagem.id, pontos, excluir_solicitacao_id=solicitacao.id)
        negada = max(vetor[i:j]) >= _capacidade(viagem, rota)

        if negada and solicitacao.ponto_embarque_id is not None:
            # Changing route must not cost the seat already guaranteed, so this attempt
            # does not become NEGADA.
            raise ConflictError(
                "Sem lugar disponível no trecho solicitado; sua reserva anterior foi mantida"
            )

        solicitacao.ponto_embarque_id = pontos[i]
        solicitacao.ponto_destino_id = pontos[j]
        solicitacao.declarada_em = agora
        if negada:
            solicitacao.status = StatusSolicitacao.NEGADA

    if negada:
        logger.info(f"Trajeto negado por capacidade: viagem={viagem_id} aluno={aluno_id}")
        raise ConflictError("Sem lugar disponível no trecho solicitado nesta viagem")

    return solicitacao
