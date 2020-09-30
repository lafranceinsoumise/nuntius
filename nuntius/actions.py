from datetime import timedelta

from django.utils.timezone import now

from nuntius import app_settings
from nuntius.admin import subscriber_class
from nuntius.models import CampaignSentStatusType, AbstractSubscriber, CampaignSentEvent

successful_sent = (CampaignSentStatusType.UNKNOWN, CampaignSentStatusType.OK)


def update_subscriber(email, campaign_status):
    statuses = {
        CampaignSentStatusType.BOUNCED: None,
        CampaignSentStatusType.UNSUBSCRIBED: AbstractSubscriber.STATUS_UNSUBSCRIBED,
        CampaignSentStatusType.COMPLAINED: AbstractSubscriber.STATUS_COMPLAINED,
    }

    if campaign_status not in statuses:
        return

    model_class = subscriber_class()

    # if unsubscribe or spam, we change the status of the subscriber
    if campaign_status != CampaignSentStatusType.BOUNCED:
        model_class.objects.set_subscriber_status(email, statuses.get(campaign_status))
        return

    email_events = CampaignSentEvent.objects.filter(email=email)

    # if first email sent is a bounce, we bounce forever
    if not email_events.filter(result__in=successful_sent).exists():
        model_class.objects.set_subscriber_status(
            email, AbstractSubscriber.STATUS_BOUNCED
        )
        return

    max_bounce_duration_ago = now() - timedelta(
        days=app_settings.BOUNCE_PARAMS["duration"]
    )

    recent_successful_sent = email_events.filter(
        result__in=successful_sent, datetime__gt=max_bounce_duration_ago
    ).exists()

    # if there is at least a successful sending in `duration`, it is allowed up to `limit`
    if (
        recent_successful_sent
        and email_events.filter(
            result=CampaignSentStatusType.BOUNCED, datetime__gt=max_bounce_duration_ago
        ).count()
        <= app_settings.BOUNCE_PARAMS["limit"]
    ):
        return

    # it is also ok if we have at least a successful sending in last `consecutive` + 1
    for sent_event in email_events[: app_settings.BOUNCE_PARAMS["consecutive"] + 1]:
        if sent_event.result in successful_sent:
            return

    # in all other case, we bounce
    model_class.objects.set_subscriber_status(email, AbstractSubscriber.STATUS_BOUNCED)
