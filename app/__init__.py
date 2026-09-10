import json
import logging
import os
from datetime import timedelta
from typing import Any

import firebase_admin
from dotenv import load_dotenv
from firebase_admin import credentials
from flask import Flask, Response, jsonify
from flask_cors import CORS
from flask_jwt_extended import JWTManager
from flask_restx import Api

from app.core.error_handlers import register_error_handlers, register_jwt_handlers
from app.extensions import scheduler
from app.utils.scheduler_setup import init_scheduler

from .core.config import Settings
from .models.base import db
from .utils import (
    check_production_security,
    setup_logging,
    setup_request_id_middleware,
    setup_security_headers,
)

jwt = JWTManager()
logger = logging.getLogger(__name__)


def create_app(*, config_overrides: dict[str, Any] | None = None) -> Flask:
    """App factory for the PaqTcPB product.

    No plugin discovery here: unlike the buska-org/corporate-backend fork
    this replaces, this repo is not a shared core other repos extend, it is
    the product for one client. See
    docs/adr/0001-produto-do-zero-em-vez-de-fork.md.
    """
    load_dotenv()
    settings = Settings()
    app = Flask(__name__)
    app.url_map.strict_slashes = False

    if not firebase_admin._apps:
        if settings.FIREBASE_CREDENTIALS:
            cert_dict = json.loads(settings.FIREBASE_CREDENTIALS)
            cred = credentials.Certificate(cert_dict)
            logger.info("Firebase initialized via GitHub Secrets (Environment Variable).")
            firebase_admin.initialize_app(cred)
        else:
            if settings.DEBUG and not os.path.exists("firebase-credentials.json"):
                logger.warning("Firebase credentials not found in environment variables.")
            else:
                cred = credentials.Certificate("firebase-credentials.json")
                logger.info("Firebase initialized via local file.")
                firebase_admin.initialize_app(cred)

    app.config["SQLALCHEMY_DATABASE_URI"] = settings.SQLALCHEMY_DATABASE_URI
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["JWT_SECRET_KEY"] = settings.JWT_SECRET_KEY
    app.config["JWT_ACCESS_TOKEN_EXPIRES"] = timedelta(hours=settings.JWT_EXPIRES_HOURS)
    app.config["DEBUG"] = settings.DEBUG

    # O flask_restx captura as exceções levantadas dentro dos Resources e
    # responde 500 genérico por conta própria; ele só delega para os
    # @app.errorhandler registrados abaixo quando PROPAGATE_EXCEPTIONS é
    # verdadeiro. Sem isso o valor cai para DEBUG or TESTING, ou seja, todo
    # erro de negócio (400, 401, 403, 404) virava 500 em produção.
    # As exceções inesperadas continuam cobertas pelo handler de Exception,
    # que devolve o 500 no formato padrão sem vazar traceback.
    app.config["PROPAGATE_EXCEPTIONS"] = True

    app.config["MAIL_SERVER"] = settings.MAIL_SERVER
    app.config["MAIL_PORT"] = settings.MAIL_PORT
    app.config["MAIL_USERNAME"] = settings.MAIL_USERNAME
    app.config["MAIL_PASSWORD"] = settings.MAIL_PASSWORD
    app.config["MAIL_USE_TLS"] = settings.MAIL_USE_TLS
    app.config["FRONTEND_URL"] = settings.FRONTEND_URL

    # Maximum request size (16MB)
    app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024

    # Test harness and embedding hosts inject config here. Must run before
    # anything reads config (setup_logging reads DEBUG below) and before
    # db.init_app(): Flask-SQLAlchemy 3.1 binds engines during init_app, so a
    # later app.config.update() would be silently ignored.
    if config_overrides:
        app.config.update(config_overrides)

    # ==========================================
    # Logging Configuration
    # ==========================================
    setup_logging(app)
    setup_request_id_middleware(app)

    logger.info(
        "Application starting",
        extra={
            "environment": settings.ENV,
            "debug": settings.DEBUG,
        },
    )

    # ==========================================
    # CORS Configuration
    # ==========================================
    CORS(
        app,
        origins=settings.CORS_ORIGINS,
        supports_credentials=True,
        allow_headers=["Content-Type", "Authorization"],
        methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        max_age=86400,  # Cache preflight for 24 hours
    )

    db.init_app(app)
    jwt.init_app(app)

    # ==========================================
    # Scheduler Configuration
    # ==========================================
    scheduler.init_app(app)

    init_scheduler(app, scheduler)

    # ==========================================
    # Security Headers
    # ==========================================
    setup_security_headers(app)

    # Check production security
    if not settings.DEBUG:
        security_warnings = check_production_security(app)
        if security_warnings:
            logger.warning(
                "Security configuration warnings",
                extra={"warnings": security_warnings},
            )

    authorizations = {
        "Bearer": {
            "type": "apiKey",
            "in": "header",
            "name": "Authorization",
            "description": "JWT token. Format: Bearer <token>",
        }
    }

    api = Api(
        app,
        title="PaqTcPB API",
        version="0.1.0",
        description="""
## Mobilidade corporativa sob demanda — Parque Tecnológico da Paraíba

Nenhum namespace registrado ainda: esqueleto inicial, sem regra de negócio.
Ver docs/adr/0001-produto-do-zero-em-vez-de-fork.md.
        """,
        doc="/docs",
        authorizations=authorizations,
        security="Bearer",
        contact="BusKá Team",
    )

    # API v1 routes — nenhuma ainda. Cada controller se registra aqui quando
    # o recurso correspondente ganhar schema e service reais.

    # ==========================================
    # Error Handlers
    # ==========================================

    register_jwt_handlers(jwt)
    register_error_handlers(app)

    # ==========================================
    # OpenAPI Export Endpoint
    # ==========================================

    @app.route("/openapi.json")
    def openapi_spec() -> Any:
        """Export OpenAPI specification as JSON."""
        return jsonify(api.__schema__)

    # ==========================================
    # CLI Commands
    # ==========================================

    @app.cli.command("export-openapi")
    def export_openapi() -> None:
        """Export OpenAPI specification to docs/openapi.json."""
        with app.test_request_context():
            spec = api.__schema__
            output_path = "docs/openapi.json"
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(spec, f, indent=2, ensure_ascii=False)
            print(f"[*] OpenAPI spec exported to {output_path}")

    # ==========================================
    # Health / Readiness Endpoints
    # ==========================================

    @app.get("/health")
    def health() -> tuple[Response, int]:
        """Liveness probe — server is running."""
        return (
            jsonify(
                status="ok",
                service="paqtcpb-backend",
                environment=settings.ENV,
            ),
            200,
        )

    @app.get("/ready")
    def ready() -> tuple[Response, int]:
        """Readiness probe — server can handle requests (DB reachable)."""
        try:
            # Minimal DB check (safe + fast)
            from sqlalchemy import text

            db.session.execute(text("SELECT 1"))
            return jsonify(status="ok", ready=True), 200
        except Exception:
            logger.error("Readiness check failed", exc_info=True)
            return jsonify(status="error", ready=False), 503

    return app
