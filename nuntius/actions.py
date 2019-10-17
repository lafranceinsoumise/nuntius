from django.conf import settings
from django.contrib.contenttypes.models import ContentType

from nuntius.models import CampaignSentStatusType, AbstractSubscriber


def update_subscriber(email, campaign_status):
    statuses = {
        CampaignSentStatusType.BOUNCED: AbstractSubscriber.STATUS_BOUNCED,
        CampaignSentStatusType.UNSUBSCRIBED: AbstractSubscriber.STATUS_UNSUBSCRIBED,
        CampaignSentStatusType.COMPLAINED: AbstractSubscriber.STATUS_COMPLAINED,
    }

    if campaign_status not in statuses:
        return

    model = settings.NUNTIUS_SUBSCRIBER_MODEL
    model_class = ContentType.objects.get(
        app_label=model.split(".")[0], model=model.split(".")[1].lower()
    ).model_class()
    model_class.objects.set_subscriber_status(email, statuses.get(campaign_status))
