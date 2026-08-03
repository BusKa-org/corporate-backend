"""Contract tests for create_app(). No DB required."""

from app import create_app


def test_create_app_applies_config_overrides_before_engine_binding():
    """Overrides must reach db.init_app, not arrive after it."""
    app = create_app(config_overrides={"SQLALCHEMY_DATABASE_URI": "postgresql+psycopg2://x:y@nowhere/z"})
    assert app.config["SQLALCHEMY_DATABASE_URI"] == "postgresql+psycopg2://x:y@nowhere/z"


def test_create_app_override_reaches_the_bound_engine():
    """The engine Flask-SQLAlchemy actually bound must use the overridden URI."""
    from app.models.base import db

    uri = "postgresql+psycopg2://override:pass@127.0.0.1:6543/override_db"
    app = create_app(config_overrides={"SQLALCHEMY_DATABASE_URI": uri})
    engine = db._app_engines[app][None]
    assert "override_db" in str(engine.url)


def test_create_app_without_overrides_still_works():
    app = create_app()
    assert app.config["SQLALCHEMY_DATABASE_URI"].startswith("postgresql")
