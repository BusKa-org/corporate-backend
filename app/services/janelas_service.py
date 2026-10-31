"""Janelas de disponibilidade do veículo (RF-05)."""

from datetime import datetime

from app.models.base import db
from app.models.enum import DiaDaSemana
from app.models.onibus import JanelaDisponibilidade
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
