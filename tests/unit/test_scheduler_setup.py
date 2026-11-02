from pathlib import Path

import pytest
from flask import Flask
from flask_apscheduler import APScheduler

from app.utils.scheduler_setup import init_scheduler

REPO_ROOT = Path(__file__).parents[2]

# Variables that must reach the production containers. A missing FLASK_ENV was
# the root cause of the scheduler never running on the VM.
ENV_OBRIGATORIAS = [
    "FLASK_ENV",
    "TZ",
    "RUN_SCHEDULER",
    "FIREBASE_CREDENTIALS",
    "CORS_ORIGINS",
    "FRONTEND_URL",
    "MAIL_SERVER",
]

JOBS_ESPERADOS = {
    "job_24h",
    "job_10min",
    "job_convites",
    "job_retencao",
    "job_fechar_buffers",
    "job_prazo_inicio",
}


@pytest.fixture()
def scheduler_app():
    """Minimal, isolated app: init_scheduler only uses app.logger and app.debug."""
    app = Flask("scheduler_test")
    app.config["SCHEDULER_API_ENABLED"] = False
    app.config["JOB_BUFFER_INTERVALO_SEGUNDOS"] = 30
    app.config["JOB_PRAZO_INICIO_INTERVALO_SEGUNDOS"] = 60
    return app


@pytest.fixture()
def sched(scheduler_app):
    scheduler = APScheduler()
    scheduler.init_app(scheduler_app)
    yield scheduler
    if scheduler.running:
        scheduler.shutdown(wait=False)


def test_init_scheduler_registra_todos_os_jobs(scheduler_app, sched, monkeypatch):
    monkeypatch.setenv("RUN_SCHEDULER", "true")

    init_scheduler(scheduler_app, sched)

    assert {job.id for job in sched.get_jobs()} == JOBS_ESPERADOS


def test_init_scheduler_nao_registra_nada_sem_run_scheduler(scheduler_app, sched, monkeypatch):
    """Ensures the API's 4 workers (and the test suite) run without a scheduler."""
    monkeypatch.delenv("RUN_SCHEDULER", raising=False)

    init_scheduler(scheduler_app, sched)

    assert sched.get_jobs() == []


def test_compose_de_producao_repassa_env_obrigatorias():
    # Read as text, with no yaml dependency. Switch to yaml.safe_load if per-service
    # assertions are ever needed.
    texto = (REPO_ROOT / "docker-compose.prod.yml").read_text()

    ausentes = [chave for chave in ENV_OBRIGATORIAS if f"{chave}:" not in texto]

    assert not ausentes, f"faltando em docker-compose.prod.yml: {ausentes}"


def test_compose_de_producao_tem_servico_scheduler():
    texto = (REPO_ROOT / "docker-compose.prod.yml").read_text()

    assert "buska_scheduler" in texto
    assert "app.scheduler_main" in texto
