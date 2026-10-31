"""RF-05 — janelas de disponibilidade do veículo.

O gestor define em que dias e horários o veículo institucional aceita
solicitações. Dentro da janela o sistema fica *Ociosa* esperando o RF-10; fora
dela a solicitação é recusada e o aluno recebe os horários de operação.

A janela também carrega o N da contagem regressiva do buffer (RF-11), que o
requisito manda ser configurável pelo gestor — por isso ele mora aqui, e não
numa configuração global.
"""

import logging
from datetime import date, datetime, time
from typing import Any

from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError, ValidationError
from app.core.transaction import transactional
from app.models.base import db
from app.models.enum import DiaDaSemana, UserRole, UserStatus
from app.models.janela import JanelaDisponibilidade
from app.models.onibus import Onibus
from app.models.rota import Rota
from app.models.user import Motorista, User

logger = logging.getLogger(__name__)

# A ordem do enum acompanha date.weekday(): SEG=0 ... DOM=6.
_DIAS = list(DiaDaSemana)


def dia_da_semana(dia: date) -> DiaDaSemana:
    """Dia da semana de uma data, no enum do banco."""
    return _DIAS[dia.weekday()]


def _gestor(user_id: str) -> User:
    user = db.session.get(User, user_id)
    if not user or user.role != UserRole.GESTOR:
        raise ForbiddenError("Apenas gestores podem gerenciar janelas de disponibilidade")
    return user


def _get_janela(janela_id: str, organizacao_id: Any) -> JanelaDisponibilidade:
    janela = db.session.get(JanelaDisponibilidade, janela_id)
    if not janela or janela.organizacao_id != organizacao_id:
        raise NotFoundError("Janela de disponibilidade não encontrada")
    return janela


def _validar_rota(rota_id: Any, organizacao_id: Any) -> Rota:
    rota = db.session.get(Rota, rota_id)
    if not rota or rota.organizacao_id != organizacao_id:
        raise NotFoundError("Rota não encontrada")
    return rota


def _validar_motorista(motorista_id: Any, organizacao_id: Any) -> Motorista:
    """RF-05 fluxo secundário 1: motorista sem cadastro ativo é erro."""
    motorista = db.session.get(Motorista, motorista_id)
    if not motorista or motorista.organizacao_id != organizacao_id:
        raise NotFoundError("Motorista não encontrado")
    if motorista.status == UserStatus.DISABLED:
        raise ValidationError("Motorista sem cadastro ativo")
    return motorista


def _validar_veiculo(veiculo_id: Any, organizacao_id: Any) -> Onibus | None:
    if not veiculo_id:
        return None
    veiculo = db.session.get(Onibus, veiculo_id)
    if not veiculo or veiculo.organizacao_id != organizacao_id:
        raise NotFoundError("Veículo não encontrado")
    return veiculo


def _validar_sobreposicao(janela: JanelaDisponibilidade) -> None:
    """RF-05 fluxo secundário 1: duas janelas ativas do mesmo circuito não
    podem se cruzar no mesmo dia. Duas faixas se sobrepõem quando cada uma
    começa antes do fim da outra."""
    conflito = (
        db.session.query(JanelaDisponibilidade.id)
        .filter(
            JanelaDisponibilidade.rota_id == janela.rota_id,
            JanelaDisponibilidade.dia == janela.dia,
            JanelaDisponibilidade.ativo.is_(True),
            JanelaDisponibilidade.id != janela.id,
            JanelaDisponibilidade.hora_inicio < janela.hora_fim,
            JanelaDisponibilidade.hora_fim > janela.hora_inicio,
        )
        .first()
    )
    if conflito:
        raise ConflictError("Já existe uma janela ativa neste circuito, dia e faixa de horário")


def _aplicar(janela: JanelaDisponibilidade, data: dict[str, Any]) -> None:
    for campo in (
        "rota_id",
        "motorista_id",
        "veiculo_id",
        "dia",
        "hora_inicio",
        "hora_fim",
        "buffer_minutos",
        "ativo",
    ):
        if campo in data:
            setattr(janela, campo, data[campo])

    if janela.hora_fim <= janela.hora_inicio:
        raise ValidationError("A hora final precisa ser maior que a inicial")


# ==========================================
# CRUD do gestor
# ==========================================


def listar(user_id: str, filtros: dict[str, Any] | None = None) -> list[JanelaDisponibilidade]:
    """Janelas da organização do gestor."""
    gestor = _gestor(user_id)
    filtros = filtros or {}

    query = db.session.query(JanelaDisponibilidade).filter_by(organizacao_id=gestor.organizacao_id)
    if filtros.get("rota_id"):
        query = query.filter(JanelaDisponibilidade.rota_id == filtros["rota_id"])
    if filtros.get("dia"):
        query = query.filter(JanelaDisponibilidade.dia == filtros["dia"])

    return query.order_by(JanelaDisponibilidade.dia, JanelaDisponibilidade.hora_inicio).all()


def criar(user_id: str, data: dict[str, Any]) -> JanelaDisponibilidade:
    gestor = _gestor(user_id)

    _validar_rota(data["rota_id"], gestor.organizacao_id)
    _validar_motorista(data["motorista_id"], gestor.organizacao_id)
    _validar_veiculo(data.get("veiculo_id"), gestor.organizacao_id)

    janela = JanelaDisponibilidade(organizacao_id=gestor.organizacao_id)
    _aplicar(janela, data)
    _validar_sobreposicao(janela)

    with transactional():
        db.session.add(janela)

    return janela


def atualizar(user_id: str, janela_id: str, data: dict[str, Any]) -> JanelaDisponibilidade:
    gestor = _gestor(user_id)
    janela = _get_janela(janela_id, gestor.organizacao_id)

    if "rota_id" in data:
        _validar_rota(data["rota_id"], gestor.organizacao_id)
    if "motorista_id" in data:
        _validar_motorista(data["motorista_id"], gestor.organizacao_id)
    if data.get("veiculo_id"):
        _validar_veiculo(data["veiculo_id"], gestor.organizacao_id)

    _aplicar(janela, data)
    if janela.ativo:
        _validar_sobreposicao(janela)

    with transactional():
        db.session.add(janela)

    return janela


def remover(user_id: str, janela_id: str) -> None:
    gestor = _gestor(user_id)
    janela = _get_janela(janela_id, gestor.organizacao_id)

    with transactional():
        db.session.delete(janela)


# ==========================================
# Consulta operacional (RF-10)
# ==========================================


def agora_local() -> datetime:
    """Relógio da operação. A janela é uma faixa de horário local, não UTC."""
    return datetime.now()


def janelas_do_dia(
    organizacao_id: Any, momento: datetime | None = None
) -> list[JanelaDisponibilidade]:
    """Janelas ativas do dia — os horários de operação exibidos ao aluno."""
    momento = momento or agora_local()
    return (
        db.session.query(JanelaDisponibilidade)
        .filter_by(organizacao_id=organizacao_id, dia=dia_da_semana(momento.date()), ativo=True)
        .order_by(JanelaDisponibilidade.hora_inicio)
        .all()
    )


def janela_vigente(
    organizacao_id: Any, momento: datetime | None = None
) -> JanelaDisponibilidade | None:
    """Janela em efeito neste instante, ou None fora do horário de operação."""
    momento = momento or agora_local()
    hora: time = momento.time()

    return (
        db.session.query(JanelaDisponibilidade)
        .filter(
            JanelaDisponibilidade.organizacao_id == organizacao_id,
            JanelaDisponibilidade.dia == dia_da_semana(momento.date()),
            JanelaDisponibilidade.ativo.is_(True),
            JanelaDisponibilidade.hora_inicio <= hora,
            JanelaDisponibilidade.hora_fim >= hora,
        )
        .order_by(JanelaDisponibilidade.hora_inicio)
        .first()
    )


def vigente_para_usuario(user_id: str) -> dict[str, Any]:
    """RF-05: o que os apps mostram ao aluno — a janela em vigor e, fora dela,
    os horários de operação do dia."""
    user = db.session.get(User, user_id)
    if not user:
        raise NotFoundError("Usuário não encontrado")

    momento = agora_local()
    janela = janela_vigente(user.organizacao_id, momento)
    return {
        "em_operacao": janela is not None,
        "janela": janela,
        "horarios_hoje": janelas_do_dia(user.organizacao_id, momento),
    }
