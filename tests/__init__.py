"""
We test that having another celery app in the project does not conflict
"""
import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "tests.test_settings")

app = Celery()
app.config_from_object("django.conf:settings", namespace="CELERY")
app.conf.task_always_eager = True
app.autodiscover_tasks()
