import atexit
import os

from flask import Flask
from flask_apscheduler import APScheduler


def init_scheduler(app: Flask, scheduler: APScheduler):
    """Inicializa o scheduler. Nenhum job registrado ainda — ver app/tasks/.

    Opt-in explícito, e única condição pra rodar jobs. Só o processo dedicado
    (app.scheduler_main) liga essa variável; os workers do gunicorn e a suíte
    de testes ficam sem scheduler.

    A checagem anterior dependia de app.debug e de WERKZEUG_RUN_MAIN para
    driblar o reloader do servidor de desenvolvimento. Sob o gunicorn, onde
    WERKZEUG_RUN_MAIN nunca existe, ela desligava todos os jobs em produção.
    """
    if os.getenv("RUN_SCHEDULER", "").lower() not in ("1", "true"):
        app.logger.info("RUN_SCHEDULER desligado: nenhum job registrado neste processo.")
        return

    # scheduler.add_job(...) entra aqui conforme app/tasks/ ganha jobs reais.

    scheduler.start()

    atexit.register(lambda: scheduler.running and scheduler.shutdown())
