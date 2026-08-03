"""Flask extensions module to prevent circular imports."""

from flask_apscheduler import APScheduler

scheduler = APScheduler()
