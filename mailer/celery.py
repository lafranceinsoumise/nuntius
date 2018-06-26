from __future__ import absolute_import, unicode_literals
from celery import Celery

def monitor(app):
    state = app.events.State()

    def task_sent(event):
        from mailer.models import Campaign
        state.event(event)
        if event.name != 'mailer.tasks.send_campaign':
            return
        campaign_pk = event['args'][0]
        campaign = Campaign.objects.get(pk=campaign_pk)
        campaign.task_uuid = event['uuid']
        campaign.status = Campaign.STATUS_WAITING
        campaign.save()

    def task_started(event):
        from mailer.models import Campaign
        state.event(event)
        if event.name != 'mailer.tasks.send_campaign':
            return
        campaign = Campaign.objects.get(task_uuid=event['uuid'])
        campaign.status = Campaign.STATUS_SENDING
        campaign.save()

    def task_succeeded(event):
        from mailer.models import Campaign
        state.event(event)
        if event.name != 'mailer.tasks.send_campaign':
            return
        campaign = Campaign.objects.get(task_uuid=event['uuid'])
        campaign.status = Campaign.STATUS_SENT
        campaign.save()

    def task_failed(event):
        from mailer.models import Campaign
        state.event(event)
        if event.name != 'mailer.tasks.send_campaign':
            return
        campaign = Campaign.objects.get(task_uuid=event['uuid'])
        campaign.status = Campaign.STATUS_ERROR
        campaign.save()

    def worker_offline(event):
        from mailer.models import Campaign
        state.event(event)

        Campaign.objects.filter(status=Campaign.STATUS_SENDING).update(status=Campaign.STATUS_WAITING)


mailer_celery_app = Celery('mailer')

mailer_celery_app.conf.task_default_routing_key = 'mailer'
mailer_celery_app.task_send_sent_event = True
mailer_celery_app.conf.task_started = True

mailer_celery_app.config_from_object(
    'django.conf:settings',
    namespace='MAILER_CELERY'
)
