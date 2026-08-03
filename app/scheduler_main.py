"""Entrypoint do container de scheduler: roda os jobs de background, sem HTTP.

A API sobe com 4 workers do gunicorn; se cada um iniciasse o próprio scheduler,
as notificações sairiam duplicadas. Por isso os jobs vivem aqui, em um processo
só, e os workers da API sobem com RUN_SCHEDULER desligado.
"""

import threading

from app import create_app
from app.extensions import scheduler

app = create_app()

if __name__ == "__main__":
    jobs = scheduler.get_jobs()

    # Falhar alto. Um scheduler mal configurado ficando ocioso em silêncio foi
    # exatamente o defeito que derrubou a geração de viagens em produção.
    if not jobs:
        raise SystemExit("Nenhum job registrado. RUN_SCHEDULER está ligado?")

    app.logger.info("Scheduler up with %d jobs: %s", len(jobs), [job.id for job in jobs])

    threading.Event().wait()  # O APScheduler roda na própria thread; só bloqueia aqui.
