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
from nuntius.models import (
    Campaign,
    CampaignSentEvent,
    CampaignSentStatusType,
    AbstractSubscriber,
)

try:
    from anymail.exceptions import AnymailRecipientsRefused
except:

    class AnymailRecipientsRefused(BaseException):
        pass


def replace_vars(string, data):
    var_regex = re.compile(r"\[([-a-zA-Z_]+)\]")
    context = Context(data)

    return Template(var_regex.sub(r"{{ \1 }}", string)).render(context=context)


def reset_connection(connection):
    try:
        connection.close()
    except Exception:
        pass

    for retry in reversed(range(1, 11)):
        try:
            sleep(1 / retry)
            connection.open()
        except Exception:
            connection.close()
        else:
            break


@nuntius_celery_app.task()
def send_campaign(campaign_pk):
    campaign = Campaign.objects.get(pk=campaign_pk)
    campaign.status = Campaign.STATUS_SENDING
    campaign.save()

    if campaign.segment is None:
        model = settings.NUNTIUS_SUBSCRIBER_MODEL
        model_class = ContentType.objects.get(
            app_label=model.split(".")[0], model=model.split(".")[1].lower()
        ).model_class()
        queryset = model_class.objects.all()
    else:
        queryset = campaign.segment.get_subscribers_queryset()

    def send_message(connection, sent_event, message, retries=10):
        try:
            message.send()
        except SMTPServerDisconnected as e:
            if retries == 0:
                campaign.status = Campaign.STATUS_ERROR
                campaign.save()
                raise e

            reset_connection(connection)

            sleep(1 / retries)

            send_message(connection, sent_event, message, retries=retries - 1)
        except (SMTPRecipientsRefused, AnymailRecipientsRefused):
            sent_event.result = CampaignSentStatusType.BLOCKED
            sent_event.save()
        else:
            if hasattr(message, "anymail_status"):
                if message.anymail_status.recipients[sent_event.email].status in [
                    "invalid",
                    "rejected",
                    "failed",
                ]:
                    sent_event.result = CampaignSentStatusType.REJECTED
                else:
                    sent_event.result = CampaignSentStatusType.UNKNOWN
                sent_event.esp_message_id = message.anymail_status.recipients[
                    sent_event.email
                ].message_id
            else:
                sent_event.result = CampaignSentStatusType.UNKNOWN
            sent_event.save()

    try:
        with mail.get_connection(
            backend=getattr(settings, "NUNTIUS_EMAIL_BACKEND", None)
        ) as connection:
            for subscriber in queryset.iterator():
                if (
                    subscriber.get_subscriber_status()
                    != AbstractSubscriber.STATUS_SUBSCRIBED
                ):
                    continue

                email = subscriber.get_subscriber_email()

                (sent_event, created) = CampaignSentEvent.objects.get_or_create(
                    campaign=campaign, subscriber=subscriber, email=email
                )

                if sent_event.result != CampaignSentStatusType.PENDING:
                    continue

                with transaction.atomic():
                    sent_event = CampaignSentEvent.objects.select_for_update().get(
                        subscriber=subscriber, campaign=campaign
                    )

                    if sent_event.result != CampaignSentStatusType.PENDING:
                        continue

                    subscriber_data = subscriber.get_subscriber_data()

                    from_email = (
                        f"{campaign.message_from_name} <{campaign.message_from_email}>"
                        if campaign.message_from_name
                        else campaign.message_from_email
                    )
                    message = EmailMultiAlternatives(
                        subject=campaign.message_subject,
                        body=replace_vars(
                            campaign.message_content_text, subscriber_data
                        ),
                        from_email=from_email,
                        to=[email],
                        reply_to=campaign.message_reply_to_email,
                        connection=connection,
                    )
                    message.attach_alternative(
                        replace_vars(campaign.message_content_html, subscriber_data),
                        "text/html",
                    )
                    send_message(connection, sent_event, message)

            campaign.status = Campaign.STATUS_SENT
            campaign.save()
    except Exception as e:
        campaign.status = Campaign.STATUS_ERROR
        campaign.save()
        raise e
