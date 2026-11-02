"""Scheduler container entrypoint: runs the background jobs, without HTTP.

The API runs 4 gunicorn workers; if each started its own scheduler, the
notifications would go out duplicated. So the jobs live here, in a single
process, and the API workers start with RUN_SCHEDULER off.
"""

import threading

from app import create_app
from app.extensions import scheduler

app = create_app()

if __name__ == "__main__":
    jobs = scheduler.get_jobs()

    # Fail loudly. A misconfigured scheduler sitting idle in silence was exactly
    # the defect that broke trip generation in production.
    if not jobs:
        raise SystemExit("Nenhum job registrado. RUN_SCHEDULER está ligado?")

    app.logger.info("Scheduler up with %d jobs: %s", len(jobs), [job.id for job in jobs])

    threading.Event().wait()  # APScheduler runs in its own thread; this only blocks.
