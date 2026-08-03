import atexit
import os

from flask import Flask
from flask_apscheduler import APScheduler

from app.tasks.notificacao_tasks import verificar_viagens_10min, verificar_viagens_24h
from app.tasks.viagem_tasks import processar_rodadas


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

    # Rodada sob demanda: fecha buffers vencidos (RF-15) e cobra o motorista
    # que não iniciou o percurso (RF-11). O minuto é a granularidade útil —
    # o buffer é contado em minutos.
    scheduler.add_job(
        id="job_rodadas",
        func=processar_rodadas,
        args=[app],
        trigger="interval",
        minutes=1,
        replace_existing=True,
    )

    scheduler.start()

    atexit.register(lambda: scheduler.running and scheduler.shutdown())
