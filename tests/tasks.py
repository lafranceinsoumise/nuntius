from celery import shared_task


@shared_task
def dumb_task():
    pass
