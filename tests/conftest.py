"""Fixtures compartilhadas. Mínimas de propósito: sem modelo de domínio
ainda, só o suficiente pra `app` e `client` funcionarem em teste.
"""

import pytest

from app import create_app
from app.models.base import db


@pytest.fixture
def app():
    application = create_app(
        config_overrides={
            "TESTING": True,
            "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
        }
    )
    with application.app_context():
        db.create_all()
        yield application
        db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()
