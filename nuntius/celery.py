from __future__ import absolute_import, unicode_literals
from celery import Celery

nuntius_celery_app = Celery("nuntius", set_as_current=False)

nuntius_celery_app.config_from_object(
    "django.conf:settings", namespace="NUNTIUS_CELERY"
)
nuntius_celery_app.conf.worker_send_task_events = True
nuntius_celery_app.conf.task_send_sent_event = True
nuntius_celery_app.conf.task_track_started = True
nuntius_celery_app.conf.task_routes = {"nuntius._tasks.*": {"queue": "nuntius"}}
