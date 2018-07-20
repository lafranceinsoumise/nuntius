import re
from smtplib import SMTPServerDisconnected, SMTPRecipientsRefused, SMTPSenderRefused
from time import sleep

from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.core import mail
from django.core.mail import EmailMultiAlternatives
from django.db import transaction
from django.template import Template, Context

from nuntius.celery import nuntius_celery_app
from nuntius.models import Campaign, BaseSubscriber, CampaignSentEvent


def replace_vars(string, data):
    var_regex = re.compile(r'\[([-a-zA-Z_]+)\]')
    context = Context(data)

    return Template(var_regex.sub(r'{{ \1 }}', string)).render(context=context)


@nuntius_celery_app.task()
def send_campaign(campaign_pk):
    campaign = Campaign.objects.get(pk=campaign_pk)
    campaign.status = Campaign.STATUS_SENDING
    campaign.save()

    if campaign.segment is None:
        model = settings.NUNTIUS_SUBSCRIBER_MODEL
        model_class = ContentType.objects.get(app_label=model.split('.')[0], model=model.split('.')[1].lower()).model_class()
        queryset = model_class.objects.all()
    else:
        queryset = campaign.segment.get_subscribers_queryset().exclude(campaignsentevent__campaign=campaign)

    try:
        with mail.get_connection() as connection:
            for subscriber in queryset.iterator():
                def send_subscriber(subscriber, retries=10):
                    if subscriber.get_subscriber_status() != BaseSubscriber.STATUS_SUBSCRIBED:
                        return

                    email = subscriber.get_subscriber_email()

                    (event, created) = CampaignSentEvent.objects.get_or_create(
                        campaign=campaign,
                        subscriber=subscriber,
                        email=email,
                    )

                    if event.result != CampaignSentEvent.RESULT_PENDING:
                        return

                    with transaction.atomic():
                        event = CampaignSentEvent.objects.select_for_update()\
                            .get(subscriber=subscriber, campaign=campaign)

                        if event.result != CampaignSentEvent.RESULT_PENDING:
                            return

                        subscriber_data = subscriber.get_subscriber_data()

                        message = EmailMultiAlternatives(
                            subject=campaign.message_subject,
                            body=replace_vars(campaign.message_content_text, subscriber_data),
                            from_email=campaign.message_from_email,
                            to=[email],
                            reply_to=campaign.message_reply_to_email,
                            connection=connection,
                        )
                        message.attach_alternative(replace_vars(campaign.message_content_html, subscriber_data), 'text/html')
                        try:
                            message.send()
                            event.result = CampaignSentEvent.RESULT_OK
                            event.save()
                        except SMTPServerDisconnected as e:
                            if retries == 0:
                                campaign.status = Campaign.STATUS_ERROR
                                campaign.save()
                                raise e
                            connection.close()

                            sleep(1/retries)

                            connection.open()
                            send_subscriber(subscriber, retries=retries-1)
                        except SMTPRecipientsRefused:
                            event.result = CampaignSentEvent.RESULT_BLOCKED
                            event.save()

                send_subscriber(subscriber)

            campaign.status = Campaign.STATUS_SENT
            campaign.save()
    except ConnectionError:
        campaign.status = Campaign.STATUS_ERROR
        campaign.save()

