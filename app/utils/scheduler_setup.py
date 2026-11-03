import atexit
import os

from flask import Flask
from flask_apscheduler import APScheduler

from app.tasks.convite_tasks import enviar_convites_pendentes
from app.tasks.notificacao_tasks import (
    INTERVALO_JOB_10MIN_MINUTOS,
    INTERVALO_JOB_24H_MINUTOS,
    verificar_viagens_10min,
    verificar_viagens_24h,
)
from app.tasks.retencao_tasks import job_anonimizar_retencoes
from app.tasks.viagem_tasks import job_alertar_prazo_inicio, job_fechar_buffers_expirados


def init_scheduler(app: Flask, scheduler: APScheduler):
    """Initialize and register all background tasks."""

    # Explicit opt-in, and the only condition. Only the dedicated process
    # (app.scheduler_main) sets this variable; gunicorn workers and the test suite
    # run without a scheduler. The previous check relied on app.debug and
    # WERKZEUG_RUN_MAIN, which never exists under gunicorn, so it disabled every
    # job in production.
    if os.getenv("RUN_SCHEDULER", "").lower() not in ("1", "true"):
        app.logger.info("RUN_SCHEDULER desligado: nenhum job registrado neste processo.")
        return

    scheduler.add_job(
        id="job_24h",
        func=verificar_viagens_24h,
        args=[app],
        trigger="interval",
        minutes=INTERVALO_JOB_24H_MINUTOS,
        replace_existing=True,
    )

    scheduler.add_job(
        id="job_10min",
        func=verificar_viagens_10min,
        args=[app],
        trigger="interval",
        minutes=INTERVALO_JOB_10MIN_MINUTOS,
        replace_existing=True,
    )

    scheduler.add_job(
        id="job_convites",
        func=enviar_convites_pendentes,
        trigger="interval",
        minutes=1,
        replace_existing=True,
    )

    scheduler.add_job(
        id="job_retencao",
        func=job_anonimizar_retencoes,
        # ponytail: trimestral (jan, abr, jul, out). O jobstore é em memória e não recupera
        # execução perdida: se o scheduler estiver fora do ar nesse dia, o job só roda no
        # trimestre seguinte. Rodar nos dias 1 a 7 cobre isso, o job é idempotente.
        trigger="cron",
        month="1,4,7,10",
        day=1,
        hour=3,
        minute=0,
        replace_existing=True,
    )

    scheduler.add_job(
        id="job_fechar_buffers",
        func=job_fechar_buffers_expirados,
        args=[app],
        trigger="interval",
        seconds=app.config["JOB_BUFFER_INTERVALO_SEGUNDOS"],
        replace_existing=True,
    )

    scheduler.add_job(
        id="job_prazo_inicio",
        func=job_alertar_prazo_inicio,
        args=[app],
        trigger="interval",
        seconds=app.config["JOB_PRAZO_INICIO_INTERVALO_SEGUNDOS"],
        replace_existing=True,
    )

    scheduler.start()

    atexit.register(lambda: scheduler.running and scheduler.shutdown())
