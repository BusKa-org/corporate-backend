"""Contract tests for create_app(). No DB required."""

from app import create_app


def test_create_app_applies_config_overrides():
    """Overrides must reach every config key, including ones set late (e.g.
    MAX_CONTENT_LENGTH) and read early (e.g. DEBUG, used by setup_logging)."""
    app = create_app(
        config_overrides={
            "SQLALCHEMY_DATABASE_URI": "postgresql+psycopg2://x:y@nowhere/z",
            "MAX_CONTENT_LENGTH": 1,
        }
    )
    assert app.config["SQLALCHEMY_DATABASE_URI"] == "postgresql+psycopg2://x:y@nowhere/z"
    assert app.config["MAX_CONTENT_LENGTH"] == 1


def test_create_app_override_reaches_the_bound_engine():
    """The engine Flask-SQLAlchemy actually bound must use the overridden URI."""
    from app.models.base import db

    uri = "postgresql+psycopg2://override:pass@127.0.0.1:6543/override_db"
    app = create_app(config_overrides={"SQLALCHEMY_DATABASE_URI": uri})
    with app.app_context():
        assert db.engine.url.database == "override_db"


def test_create_app_without_overrides_still_works():
    app = create_app()
    assert app.config["SQLALCHEMY_DATABASE_URI"].startswith("postgresql")


def test_create_app_calls_explicit_plugins():
    calls = []

    def fake_plugin(app, api):
        calls.append((app, api))

    create_app(plugins=[fake_plugin])
    assert len(calls) == 1
    app_arg, api_arg = calls[0]
    assert app_arg.name == "app"
    assert hasattr(api_arg, "add_namespace")


def test_create_app_empty_plugin_list_skips_discovery(monkeypatch):
    """plugins=[] means 'no plugins', not 'discover them'."""
    import app as app_module

    monkeypatch.setattr(
        app_module,
        "_discover_plugins",
        lambda: (_ for _ in ()).throw(AssertionError("discovery ran")),
    )
    create_app(plugins=[])  # must not raise


def test_plugin_can_register_a_namespace():
    from flask_restx import Namespace, Resource

    ns = Namespace("plugintest", path="/plugintest")

    @ns.route("/ping")
    class Ping(Resource):
        def get(self):
            return {"pong": True}

    def plugin(app, api):
        api.add_namespace(ns, path="/v1/plugintest")

    app = create_app(plugins=[plugin])
    client = app.test_client()
    assert client.get("/v1/plugintest/ping").status_code == 200
