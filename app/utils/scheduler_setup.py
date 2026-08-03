import atexit
import os

from flask import Flask
from flask_apscheduler import APScheduler

from app.tasks.notificacao_tasks import verificar_viagens_10min, verificar_viagens_24h


def init_scheduler(app: Flask, scheduler: APScheduler):
    """Inicializa e registra todas as tarefas de background."""

    # Opt-in explícito, e única condição. Só o processo dedicado
    # (app.scheduler_main) liga essa variável; os workers do gunicorn e a suíte
    # de testes ficam sem scheduler.
    #
    # A checagem anterior dependia de app.debug e de WERKZEUG_RUN_MAIN para
    # driblar o reloader do servidor de desenvolvimento. Sob o gunicorn, onde
    # WERKZEUG_RUN_MAIN nunca existe, ela desligava todos os jobs em produção.
    if os.getenv("RUN_SCHEDULER", "").lower() not in ("1", "true"):
        app.logger.info("RUN_SCHEDULER desligado: nenhum job registrado neste processo.")
        return

    scheduler.add_job(
        id="job_24h",
        func=verificar_viagens_24h,
        args=[app],
        trigger="interval",
        minutes=60,
        replace_existing=True,
    )

    scheduler.add_job(
        id="job_10min",
        func=verificar_viagens_10min,
        args=[app],
        trigger="interval",
        minutes=10,
        replace_existing=True,
    )

    scheduler.start()

    atexit.register(lambda: scheduler.running and scheduler.shutdown())
