"""Application clock. Always call it through the module (tempo.agora_utc()) so tests
can pin the time with monkeypatch in a single place.
"""

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from flask import current_app


def agora_utc() -> datetime:
    return datetime.now(UTC)


def agora_local() -> datetime:
    """Time at the organization, used to match the availability windows."""
    fuso = ZoneInfo(current_app.config.get("TIMEZONE", "America/Sao_Paulo"))
    return agora_utc().astimezone(fuso)
