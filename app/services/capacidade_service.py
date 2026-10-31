"""Validação de capacidade por segmento do circuito (RF-13, RF-14, RF-19).

O circuito tem n pontos ordenados, logo n-1 segmentos. Um trajeto Pi -> Pj
ocupa os segmentos i-1 .. j-2 (índices do vetor, base 0). A solicitação é
aceita se `PicoTrecho = max(C[i-1:j-1])` for menor que a capacidade do veículo;
assentos se liberam sozinhos depois do desembarque, então trajetos disjuntos
reusam o mesmo lugar.

O vetor é derivado das solicitações ATIVA com trajeto declarado. Cancelar
(CANCELADA) já devolve os segmentos; a desistência depois da partida não reabre
o lugar porque o buffer já fechou e ninguém mais declara.
"""

import logging
import uuid

from sqlalchemy import select

from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError, ValidationError
from app.core.transaction import transactional
from app.models.base import db
from app.models.enum import StatusSolicitacao, StatusViagem
from app.models.rota import Rota
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
    # `pontos_padrao` já vem ordenado por RotaPonto.ordem.
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
    """Reconstrói o vetor a partir das solicitações ATIVA com trajeto declarado."""
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
    """Ocupação por segmento. Índice k = trecho entre a parada k+1 e k+2."""
    viagem = _get_viagem(viagem_id)
    return _carga(viagem.id, _pontos_ordenados(_rota_da_viagem(viagem)))


def capacidade_viagem(viagem_id: IdLike) -> int:
    """Limite de assentos: a capacidade do veículo da viagem."""
    viagem = _get_viagem(viagem_id)
    return _capacidade(viagem, _rota_da_viagem(viagem))


def validar_e_reservar(
    viagem_id: IdLike,
    aluno_id: IdLike,
    ponto_origem_id: IdLike,
    ponto_destino_id: IdLike,
) -> SolicitacaoViagem:
    """RF-13/RF-14. Grava o trajeto na solicitação ATIVA do aluno, ou levanta
    ConflictError se PicoTrecho já está no limite. A solicitação negada fica como
    NEGADA antes do erro, porque o RF-21 conta negações por ponto."""
    negada = False

    with transactional():
        # shortcut: o RF-14 cita Redis; aqui as declarações concorrentes serializam
        # neste lock da viagem. Trocar por contador por segmento se virar gargalo.
        viagem = db.session.execute(
            select(Viagem)
            .where(Viagem.id == validate_uuid(str(viagem_id), "ID da viagem"))
            .with_for_update()
        ).scalar_one_or_none()
        if not viagem:
            raise NotFoundError("Viagem não encontrada")

        if viagem.status != StatusViagem.BUFFER_ABERTO:
            raise ValidationError("A viagem não está aceitando declarações de trajeto")

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

        # Redeclarar não pode fazer o aluno concorrer com a própria reserva.
        vetor = _carga(viagem.id, pontos, excluir_solicitacao_id=solicitacao.id)
        negada = max(vetor[i:j]) >= _capacidade(viagem, rota)

        if negada and solicitacao.ponto_embarque_id is not None:
            # Trocar de trajeto não pode custar o lugar já garantido, então essa
            # tentativa não vira NEGADA.
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
