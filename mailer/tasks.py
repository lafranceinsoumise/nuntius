from smtplib import SMTPServerDisconnected, SMTPRecipientsRefused, SMTPSenderRefused

from django.core import mail
from django.core.mail import EmailMultiAlternatives
from django.db import transaction

from mailer.celery import mailer_celery_app
from mailer.models import Campaign, BaseSubscriber, CampaignSentEvent


@mailer_celery_app.task()
def send_campaign(campaign_pk):
    campaign = Campaign.objects.get(pk=campaign_pk)
    campaign.status = Campaign.STATUS_SENDING
    campaign.save()

    try:
        with mail.get_connection() as connection:
            for subscriber in campaign.segment.get_queryset().iterator():
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

                        message = EmailMultiAlternatives(
                            subject=campaign.message_subject,
                            body=campaign.message_content_text,
                            from_email=campaign.message_from_email,
                            to=[email],
                            reply_to=campaign.message_reply_to_email,
                            connection=connection,
                        )
                        message.attach_alternative(campaign.message_content_html, 'text/html')
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

