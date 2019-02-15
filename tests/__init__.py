"""
We test that having another celery app in the project does not conflict
"""
from celery import Celery

app = Celery()
app.conf.task_always_eager = True
app.autodiscover_tasks()
