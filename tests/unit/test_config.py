"""Settings validation for the on-demand route limits. No DB required."""

import pytest

from app.core.config import ConfigurationError, Settings


def test_lower_max_without_padrao_keeps_dev_default_in_range(monkeypatch):
    """Dev only logs the error, but the default must not end up above the max."""
    monkeypatch.setenv("FLASK_ENV", "development")
    monkeypatch.setenv("ROTA_BUFFER_MINUTOS_MAX", "3")
    monkeypatch.delenv("ROTA_BUFFER_MINUTOS_PADRAO", raising=False)

    settings = Settings()

    assert settings.ROTA_BUFFER_MINUTOS_MAX == 3
    assert settings.ROTA_BUFFER_MINUTOS_PADRAO == 3


def test_lower_max_without_padrao_fails_fast_in_production(monkeypatch):
    monkeypatch.setenv("FLASK_ENV", "production")
    monkeypatch.setenv("JWT_SECRET_KEY", "a-long-and-strong-secret-for-tests")
    monkeypatch.setenv("ROTA_BUFFER_MINUTOS_MAX", "3")
    monkeypatch.setenv("ROTA_BUFFER_MINUTOS_PADRAO", "5")

    with pytest.raises(ConfigurationError, match="ROTA_BUFFER_MINUTOS_PADRAO must be <= 3"):
        Settings()
