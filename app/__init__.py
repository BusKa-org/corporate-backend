import json
import logging
import os
from collections.abc import Callable
from datetime import timedelta
from importlib.metadata import entry_points
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

from .api.controllers.aluno_controller import api as alunos_ns
from .api.controllers.auth_controller import api as auth_ns
from .api.controllers.consentimento_controller import api as consentimento_ns
from .api.controllers.dashboard_controller import api as dashboard_ns
from .api.controllers.embarque_controller import api as embarque_ns
from .api.controllers.instituicao_controller import api as inst_ns
from .api.controllers.janelas_controller import api as janelas_ns
from .api.controllers.notificacao_controller import api as notificacoes_ns
from .api.controllers.ocorrencia_controller import api as ocorrencias_ns
from .api.controllers.onibus_controller import api as onibus_ns
from .api.controllers.pontos_controller import api as pontos_ns
from .api.controllers.rotas_controller import api as rotas_ns
from .api.controllers.routing_controller import api as routing_ns
from .api.controllers.telemetria_controller import api as telemetria_ns
from .api.controllers.user_controller import api as user_ns
from .api.controllers.viagens_controller import api as viagem_ns
from .core.config import Settings
from .models import Ocorrencia  # noqa: F401 — registers table with SQLAlchemy
from .models.base import db
from .utils import (
    check_production_security,
    setup_logging,
    setup_request_id_middleware,
    setup_security_headers,
)

jwt = JWTManager()
logger = logging.getLogger(__name__)


def _discover_plugins() -> list[Callable[[Flask, Api], None]]:
    """Load registration callables published under the 'mebuska.plugins' group.

    Deployment repos (e.g. mebuska-deploy) declare their plugins in
    pyproject.toml so the product never imports client code by name.
    """
    eps = sorted(entry_points(group="mebuska.plugins"), key=lambda ep: ep.name)
    logger.info("Plugins discovered", extra={"plugins": [ep.name for ep in eps]})
    return [ep.load() for ep in eps]


def create_app(
    *,
    config_overrides: dict[str, Any] | None = None,
    # `plugins=None` (default) discovers via entry points; `plugins=[]` disables
    # discovery entirely — see the registration loop below for the contract.
    plugins: list[Callable[[Flask, Api], None]] | None = None,
) -> Flask:
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
    # RF-09: versão vigente do Termo de Aceite. Fica no config para que os
    # testes troquem a versão e exercitem o reaceite sem mexer no ambiente.
    app.config["TERMO_VERSAO"] = settings.TERMO_VERSAO

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
        title="MeBusKá API",
        version="1.0.0",
        description="""
## Sistema de Mobilidade Corporativa sob Demanda

API para solicitação de viagens, janela de buffer, validação de capacidade por
segmento, embarque por QR Code e rastreamento de veículos institucionais.

### Autenticação
Todos os endpoints (exceto `/auth/login`) requerem autenticação JWT.
Inclua o header: `Authorization: Bearer <seu_token>`

### Roles
- **ALUNO**: Solicita viagens, declara origem/destino, acompanha o veículo
- **MOTORISTA**: Inicia percurso, valida embarques, executa o roteiro
- **GESTOR**: Acesso completo à organização (pontos, janelas, frota, relatórios)
        """,
        doc="/docs",
        authorizations=authorizations,
        security="Bearer",
        contact="BusKá Team",
    )

    # API v1 routes
    api.add_namespace(auth_ns, path="/v1/auth")
    api.add_namespace(user_ns, path="/v1/users")
    api.add_namespace(notificacoes_ns, path="/v1/notificacoes")
    api.add_namespace(onibus_ns, path="/v1/onibus")
    api.add_namespace(rotas_ns, path="/v1/rotas")
    api.add_namespace(pontos_ns, path="/v1/pontos")
    api.add_namespace(routing_ns, path="/v1/routing")
    api.add_namespace(viagem_ns, path="/v1/viagens")
    api.add_namespace(inst_ns, path="/v1/instituicoes")
    api.add_namespace(alunos_ns, path="/v1/alunos")
    api.add_namespace(ocorrencias_ns, path="/v1/ocorrencias")
    api.add_namespace(dashboard_ns, path="/v1/dashboard")
    api.add_namespace(janelas_ns, path="/v1/janelas")
    api.add_namespace(consentimento_ns, path="/v1/consentimento")
    api.add_namespace(embarque_ns, path="/v1/embarque")
    api.add_namespace(telemetria_ns, path="/v1/telemetria")

    # Client-specific extensions — see `plugins` param contract on the signature.
    for register in (_discover_plugins() if plugins is None else plugins):
        register(app, api)

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
                service="mebuska-corporate",
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
