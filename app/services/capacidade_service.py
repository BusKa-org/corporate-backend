"""Validação de capacidade por segmento do circuito (RF-13, RF-14, RF-19).

O circuito tem n pontos ordenados, logo n-1 segmentos. Um trajeto Pi -> Pj
ocupa os segmentos i-1 .. j-2 (índices do vetor, base 0). A solicitação é
aceita se `PicoTrecho = max(C[i-1:j-1])` for menor que a capacidade do veículo;
assentos se liberam sozinhos depois do desembarque, então trajetos disjuntos
reusam o mesmo lugar.
"""

import logging
import uuid
from datetime import UTC, datetime

from sqlalchemy import select

from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError, ValidationError
from app.core.transaction import transactional
from app.models.base import db
from app.models.enum import StatusSolicitacao, StatusViagem
from app.models.rota import Rota
from app.models.user import Aluno
from app.models.viagem import AlunosConfirmados, Viagem

logger = logging.getLogger(__name__)

IdLike = str | uuid.UUID


def _uuid(valor: IdLike, rotulo: str) -> uuid.UUID:
    try:
        return uuid.UUID(str(valor))
    except (AttributeError, TypeError, ValueError) as e:
        raise ValidationError(f"{rotulo} inválido") from e


def _get_viagem(viagem_id: IdLike) -> Viagem:
    viagem = db.session.get(Viagem, _uuid(viagem_id, "ID da viagem"))
    if not viagem:
        raise NotFoundError("Viagem não encontrada")
    return viagem


def _rota_da_viagem(viagem: Viagem) -> Rota:
    """A rodada sob demanda aponta direto para o circuito; a viagem programada
    herdada chega pela grade de horários."""
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
    excluir_aluno_id: uuid.UUID | None = None,
) -> list[int]:
    """Reconstrói o vetor a partir das solicitações CONFIRMADO da viagem."""
    posicao = {ponto_id: k for k, ponto_id in enumerate(pontos)}
    vetor = [0] * max(len(pontos) - 1, 0)

    aceitas = (
        db.session.query(AlunosConfirmados)
        .filter_by(viagem_id=viagem_id, status=StatusSolicitacao.CONFIRMADO)
        .all()
    )
    for linha in aceitas:
        if excluir_aluno_id is not None and linha.aluno_id == excluir_aluno_id:
            continue
        i = posicao.get(linha.ponto_embarque_id)
        j = posicao.get(linha.ponto_destino_id)
        if i is None or j is None or i >= j:
            continue
        for k in range(i, j):
            vetor[k] += 1

    return vetor


def _posicao(posicoes: dict[uuid.UUID, int], ponto_id: IdLike, rotulo: str) -> int:
    k = posicoes.get(_uuid(ponto_id, rotulo))
    if k is None:
        raise ValidationError(f"{rotulo} não pertence ao circuito desta rodada")
    return k


def vetor_carga(viagem_id: IdLike) -> list[int]:
    """Ocupação por segmento. Índice k = trecho entre a parada k+1 e k+2."""
    viagem = _get_viagem(viagem_id)
    return _carga(viagem.id, _pontos_ordenados(_rota_da_viagem(viagem)))


def capacidade_viagem(viagem_id: IdLike) -> int:
    """Limite de assentos: capacidade do veículo da viagem (17 no PaqTcPB)."""
    viagem = _get_viagem(viagem_id)
    return _capacidade(viagem, _rota_da_viagem(viagem))


def validar_e_reservar(
    viagem_id: IdLike,
    aluno_id: IdLike,
    ponto_origem_id: IdLike,
    ponto_destino_id: IdLike,
) -> AlunosConfirmados:
    """RF-13/RF-14. Aceita e devolve a linha AlunosConfirmados CONFIRMADO,
    ou levanta ConflictError se PicoTrecho já está no limite (a linha é
    gravada como NEGADO antes de levantar — RF-21 conta negações por ponto)."""
    negado = False

    with transactional():
        # ponytail: o RF-14 cita Redis, mas aqui o vetor é derivado das linhas
        # CONFIRMADO e as declarações concorrentes serializam neste lock de
        # linha — exato, transacional e sem infraestrutura nova. O teto é a
        # serialização por viagem; se um dia isso virar gargalo, troque por um
        # contador por segmento em Redis com reconciliação contra o banco.
        viagem = db.session.execute(
            select(Viagem).where(Viagem.id == _uuid(viagem_id, "ID da viagem")).with_for_update()
        ).scalar_one_or_none()
        if not viagem:
            raise NotFoundError("Viagem não encontrada")

        if viagem.status != StatusViagem.BUFFER_ABERTO:
            raise ValidationError("A rodada não está aceitando declarações de trajeto")

        agora = datetime.now(UTC)
        if not viagem.buffer_expira_em or viagem.buffer_expira_em <= agora:
            raise ValidationError("O tempo para declarar o trajeto desta rodada já encerrou")

        aluno = db.session.get(Aluno, _uuid(aluno_id, "ID do aluno"))
        if not aluno:
            raise NotFoundError("Aluno não encontrado")

        rota = _rota_da_viagem(viagem)
        if aluno.organizacao_id != rota.organizacao_id:
            raise ForbiddenError("Aluno não pertence à organização desta rodada")

        pontos = _pontos_ordenados(rota)
        posicoes = {ponto_id: k for k, ponto_id in enumerate(pontos)}
        i = _posicao(posicoes, ponto_origem_id, "Ponto de origem")
        j = _posicao(posicoes, ponto_destino_id, "Ponto de destino")
        if i >= j:
            raise ValidationError("A origem precisa vir antes do destino na ordem do circuito")

        # Redeclarar não pode fazer o aluno concorrer com a própria reserva.
        vetor = _carga(viagem.id, pontos, excluir_aluno_id=aluno.usuario_id)
        pico_trecho = max(vetor[i:j])
        negado = pico_trecho >= _capacidade(viagem, rota)

        registro = db.session.get(AlunosConfirmados, (viagem.id, aluno.usuario_id))

        if negado and registro is not None and registro.status == StatusSolicitacao.CONFIRMADO:
            # Tentar trocar de trajeto não pode custar o lugar já garantido.
            # Sem esta guarda a linha seria sobrescrita como NEGADO e o aluno
            # sairia da rodada por ter pedido um trecho lotado. A negação não
            # é registrada aqui de propósito: gravá-la exigiria destruir a
            # reserva, e o estrangulamento que o RF-21 procura é a negação de
            # quem ainda não tem lugar.
            raise ConflictError(
                "Sem lugar disponível no trecho solicitado; sua reserva anterior foi mantida"
            )

        if not registro:
            registro = AlunosConfirmados(viagem_id=viagem.id, aluno_id=aluno.usuario_id)
            db.session.add(registro)

        registro.ponto_embarque_id = pontos[i]
        registro.ponto_destino_id = pontos[j]
        registro.declarado_em = agora
        registro.status = StatusSolicitacao.NEGADO if negado else StatusSolicitacao.CONFIRMADO
        registro.confirmacao = not negado

    if negado:
        logger.info(f"Trajeto negado por capacidade: viagem={viagem_id} aluno={aluno_id}")
        raise ConflictError("Sem lugar disponível no trecho solicitado nesta rodada")

    return registro


def liberar(viagem_id: IdLike, aluno_id: IdLike) -> None:
    """RF-19: devolve a capacidade dos segmentos e marca CANCELADO."""
    with transactional():
        registro = db.session.get(
            AlunosConfirmados,
            (_uuid(viagem_id, "ID da viagem"), _uuid(aluno_id, "ID do aluno")),
        )
        if not registro:
            raise NotFoundError("Solicitação não encontrada")

        # O vetor só conta linhas CONFIRMADO, então sair desse estado já
        # devolve a capacidade dos segmentos do trajeto.
        registro.status = StatusSolicitacao.CANCELADO
        registro.confirmacao = False
