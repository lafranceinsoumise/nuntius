import re
from smtplib import SMTPServerDisconnected, SMTPRecipientsRefused, SMTPSenderRefused
from time import sleep

from django.core import mail
from django.core.mail import EmailMultiAlternatives
from django.db import transaction
from django.template import Template, Context

from mailer.celery import mailer_celery_app
from mailer.models import Campaign, BaseSubscriber, CampaignSentEvent


def replace_vars(string, data):
    var_regex = re.compile(r'\[([-a-zA-Z_]+)\]')
    context = Context(data)

    return Template(var_regex.sub(r'{{ \1 }}', string)).render(context=context)


@mailer_celery_app.task()
def send_campaign(campaign_pk):
    campaign = Campaign.objects.get(pk=campaign_pk)
    campaign.status = Campaign.STATUS_SENDING
    campaign.save()

    queryset = campaign.segment.get_queryset().exclude(campaignsentevent__campaign=campaign)

    try:
        with mail.get_connection() as connection:
            for subscriber in queryset.iterator():
                def send_subscriber(subscriber, retries=10):
                    if subscriber.get_subscriber_status() != BaseSubscriber.STATUS_SUBSCRIBED:
                        return

                    email = subscriber.get_subscriber_email()

                    (event, created) = CampaignSentEvent.objects.get_or_create(
                        campaign=campaign,
                        subscriber_id=subscriber.get_subscriber_id(),
                        email=email,
                    )

                    if event.result != CampaignSentEvent.RESULT_PENDING:
                        return

                    with transaction.atomic():
                        event = CampaignSentEvent.objects.select_for_update()\
                            .get(subscriber_id=subscriber.get_subscriber_id(), campaign=campaign)

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

