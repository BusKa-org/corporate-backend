"""Relógio da aplicação. Chame sempre pelo módulo (tempo.agora_utc()) para os testes
conseguirem fixar a hora com monkeypatch em um único lugar."""

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from flask import current_app


def agora_utc() -> datetime:
    return datetime.now(UTC)


def agora_local() -> datetime:
    """Hora na organização, usada para casar com as janelas de disponibilidade."""
    fuso = ZoneInfo(current_app.config.get("TIMEZONE", "America/Sao_Paulo"))
    return agora_utc().astimezone(fuso)
