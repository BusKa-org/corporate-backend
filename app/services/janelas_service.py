"""Vehicle availability windows (RF-05)."""

from datetime import datetime, time
from typing import Any

from sqlalchemy import select

from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError, ValidationError
from app.core.transaction import transactional
from app.models.base import db
from app.models.enum import DiaDaSemana, UserRole
from app.models.onibus import JanelaDisponibilidade, Onibus
from app.models.user import User
from app.services import onibus_service, viagens_service
from app.services.viagens_service import _get_dia_semana_enum
from app.utils.validators import validate_uuid


def buscar_janela_ativa(onibus_id, momento_local: datetime) -> JanelaDisponibilidade | None:
    """The vehicle's window containing the moment. Start inclusive, end exclusive."""
    dia = _get_dia_semana_enum(momento_local.date())
    hora = momento_local.time().replace(tzinfo=None)
    return (
        db.session.query(JanelaDisponibilidade)
        .filter(
            JanelaDisponibilidade.onibus_id == onibus_id,
            JanelaDisponibilidade.dia == dia,
            JanelaDisponibilidade.hora_inicio <= hora,
            JanelaDisponibilidade.hora_fim > hora,
        )
        .first()
    )


def listar_janelas_do_dia(onibus_id, dia: DiaDaSemana) -> list[JanelaDisponibilidade]:
    return (
        db.session.query(JanelaDisponibilidade)
        .filter(JanelaDisponibilidade.onibus_id == onibus_id, JanelaDisponibilidade.dia == dia)
        .order_by(JanelaDisponibilidade.hora_inicio)
        .all()
    )


# Window CRUD (manager)

ORDEM_DIAS = list(DiaDaSemana)


def _exigir_gestor(user_id: str) -> None:
    user = db.session.get(User, user_id)
    if not user or user.role != UserRole.GESTOR:
        raise ForbiddenError("Apenas gestores podem gerenciar as janelas de disponibilidade")


def listar_janelas(user_id: str, onibus_id: str) -> list[JanelaDisponibilidade]:
    """The vehicle's windows, by weekday (SEG..DOM) and start time."""
    onibus = onibus_service.get_by_id(user_id, onibus_id)
    janelas = (
        db.session.query(JanelaDisponibilidade)
        .filter(JanelaDisponibilidade.onibus_id == onibus.id)
        .order_by(JanelaDisponibilidade.hora_inicio)
        .all()
    )
    # stable sort: keeps the hour order within each day
    janelas.sort(key=lambda janela: ORDEM_DIAS.index(janela.dia))
    return janelas


def _existe_sobreposicao(filtro, dia: DiaDaSemana, hora_inicio: time, hora_fim: time) -> bool:
    conflito = (
        db.session.query(JanelaDisponibilidade.id)
        .filter(
            filtro,
            JanelaDisponibilidade.dia == dia,
            JanelaDisponibilidade.hora_inicio < hora_fim,
            JanelaDisponibilidade.hora_fim > hora_inicio,
        )
        .first()
    )
    return conflito is not None


def criar_janela(user_id: str, onibus_id: str, data: dict[str, Any]) -> JanelaDisponibilidade:
    """Create an availability window (gestor only).

    Raises: ForbiddenError, NotFoundError, ValidationError, ConflictError
    """
    _exigir_gestor(user_id)
    onibus = onibus_service.get_by_id(user_id, onibus_id)

    dia = data["dia"]
    hora_inicio = data["hora_inicio"]
    hora_fim = data["hora_fim"]
    if hora_fim <= hora_inicio:
        raise ValidationError("O horário de fim deve ser posterior ao horário de início")

    with transactional():
        # Lock vehicle and driver so concurrent creations cannot slip past the conflict check
        db.session.execute(select(Onibus.id).where(Onibus.id == onibus.id).with_for_update())
        motorista_id = viagens_service.exigir_motorista_ativo(
            data["motorista_id"], onibus.organizacao_id
        )

        if _existe_sobreposicao(
            JanelaDisponibilidade.onibus_id == onibus.id, dia, hora_inicio, hora_fim
        ):
            raise ConflictError("Já existe uma janela deste veículo nesse dia e horário")
        if _existe_sobreposicao(
            JanelaDisponibilidade.motorista_id == motorista_id, dia, hora_inicio, hora_fim
        ):
            raise ConflictError("O motorista já possui uma janela nesse dia e horário")

        janela = JanelaDisponibilidade(
            onibus_id=onibus.id,
            motorista_id=motorista_id,
            dia=dia,
            hora_inicio=hora_inicio,
            hora_fim=hora_fim,
        )
        db.session.add(janela)

    return janela


def remover_janela(user_id: str, onibus_id: str, janela_id: str) -> None:
    """Remove a window from the vehicle (gestor only).

    Raises: ForbiddenError, NotFoundError
    """
    _exigir_gestor(user_id)
    onibus = onibus_service.get_by_id(user_id, onibus_id)

    janela = db.session.get(JanelaDisponibilidade, validate_uuid(janela_id, "ID da janela"))
    if not janela or janela.onibus_id != onibus.id:
        raise NotFoundError("Janela de disponibilidade não encontrada")

    with transactional():
        db.session.delete(janela)
