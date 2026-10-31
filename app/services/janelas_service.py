"""Janelas de disponibilidade do veículo (RF-05)."""

from datetime import datetime, time
from typing import Any

from sqlalchemy import select

from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError, ValidationError
from app.core.transaction import transactional
from app.models.base import db
from app.models.enum import DiaDaSemana, UserRole, UserStatus
from app.models.onibus import JanelaDisponibilidade, Onibus
from app.models.user import Motorista, User
from app.services import onibus_service
from app.services.viagens_service import _get_dia_semana_enum


def buscar_janela_ativa(onibus_id, momento_local: datetime) -> JanelaDisponibilidade | None:
    """Janela do veículo que contém o momento. Início inclusivo, fim exclusivo."""
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


# ==========================================
# CRUD das janelas (gestor)
# ==========================================

ORDEM_DIAS = list(DiaDaSemana)


def _exigir_gestor(user_id: str) -> None:
    user = db.session.get(User, user_id)
    if not user or user.role != UserRole.GESTOR:
        raise ForbiddenError("Apenas gestores podem gerenciar as janelas de disponibilidade")


def listar_janelas(user_id: str, onibus_id: str) -> list[JanelaDisponibilidade]:
    """Janelas do veículo, por dia da semana (SEG..DOM) e hora de início."""
    onibus = onibus_service.get_by_id(user_id, onibus_id)
    janelas = (
        db.session.query(JanelaDisponibilidade)
        .filter(JanelaDisponibilidade.onibus_id == onibus.id)
        .order_by(JanelaDisponibilidade.hora_inicio)
        .all()
    )
    # sort estável: mantém a ordem por hora dentro de cada dia
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
    """
    Cria uma janela de disponibilidade (gestor only).

    Raises: ForbiddenError, NotFoundError, ValidationError, ConflictError
    """
    _exigir_gestor(user_id)
    onibus = onibus_service.get_by_id(user_id, onibus_id)

    dia = data["dia"]
    hora_inicio = data["hora_inicio"]
    hora_fim = data["hora_fim"]
    if hora_fim <= hora_inicio:
        raise ValidationError("O horário de fim deve ser posterior ao horário de início")

    motorista = db.session.get(Motorista, data["motorista_id"])
    if not motorista:
        raise NotFoundError("Motorista não encontrado")
    if motorista.organizacao_id != onibus.organizacao_id:
        raise ValidationError("Motorista não pertence à organização do veículo")
    if motorista.status != UserStatus.ACTIVE:
        raise ValidationError("Motorista sem cadastro ativo")

    with transactional():
        # Trava veículo e motorista para que criações concorrentes não furem a checagem de conflito
        db.session.execute(select(Onibus.id).where(Onibus.id == onibus.id).with_for_update())
        db.session.execute(select(User.id).where(User.id == motorista.id).with_for_update())

        if _existe_sobreposicao(
            JanelaDisponibilidade.onibus_id == onibus.id, dia, hora_inicio, hora_fim
        ):
            raise ConflictError("Já existe uma janela deste veículo nesse dia e horário")
        if _existe_sobreposicao(
            JanelaDisponibilidade.motorista_id == motorista.id, dia, hora_inicio, hora_fim
        ):
            raise ConflictError("O motorista já possui uma janela nesse dia e horário")

        janela = JanelaDisponibilidade(
            onibus_id=onibus.id,
            motorista_id=motorista.id,
            dia=dia,
            hora_inicio=hora_inicio,
            hora_fim=hora_fim,
        )
        db.session.add(janela)

    return janela


def remover_janela(user_id: str, onibus_id: str, janela_id: str) -> None:
    """
    Remove uma janela do veículo (gestor only).

    Raises: ForbiddenError, NotFoundError
    """
    _exigir_gestor(user_id)
    onibus = onibus_service.get_by_id(user_id, onibus_id)

    janela = db.session.get(JanelaDisponibilidade, janela_id)
    if not janela or janela.onibus_id != onibus.id:
        raise NotFoundError("Janela de disponibilidade não encontrada")

    with transactional():
        db.session.delete(janela)
