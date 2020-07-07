import logging

from django.db import transaction
from django.dispatch import receiver

from nuntius.actions import update_subscriber
from nuntius.admin import subscriber_class
from nuntius.models import CampaignSentEvent, CampaignSentStatusType

logger = logging.getLogger(__name__)

try:
    from anymail.signals import tracking, EventType
except ImportError:
    pass
else:
    actions = {
        EventType.SENT: CampaignSentStatusType.OK,
        EventType.REJECTED: CampaignSentStatusType.REJECTED,
        EventType.FAILED: CampaignSentStatusType.ERROR,
        EventType.BOUNCED: CampaignSentStatusType.BOUNCED,
        EventType.UNSUBSCRIBED: CampaignSentStatusType.UNSUBSCRIBED,
        EventType.COMPLAINED: CampaignSentStatusType.COMPLAINED,
    }

    @receiver(tracking, dispatch_uid="nuntius_anymail_tracking")
    def handle_anymail(sender, event, esp_name, **kwargs):
        campaign_status = actions.get(event.event_type, (None, None))

        if event.event_type == EventType.BOUNCED:
            # in cases of soft bounces (grouped by Anymail with hard bounces in the BOUNCED event type)
            # we do not want to update the subscriber status
            if (
                esp_name == "Amazon SES"
                and event.esp_event.get("bounce", {}).get("bounceType") != "Permanent"
            ):
                campaign_status = CampaignSentStatusType.BLOCKED

            elif esp_name == "Postmark" and event.esp_event.get("Type") != "HardBounce":
                campaign_status = CampaignSentStatusType.BLOCKED

        if event.event_type == EventType.SENT:
            logger.debug(event.event_type + " : " + str(event.esp_event))
        else:
            logger.info(event.event_type + " : " + str(event.esp_event))

        with transaction.atomic():
            defaults = dict()
            if hasattr(subscriber_class().objects, "get_subscriber"):
                defaults["subscriber"] = subscriber_class().objects.get_subscriber(
                    event.recipient
                )
            c, is_create = CampaignSentEvent.objects.select_for_update().get_or_create(
                esp_message_id=event.message_id,
                defaults={"email": event.recipient, **defaults},
            )
            if campaign_status is not None:
                c.result = campaign_status
            if event.event_type == EventType.OPENED:
                c.open_count = c.open_count + 1
            if event.event_type == EventType.CLICKED:
                c.click_count = c.click_count + 1
            c.save()

        update_subscriber(event.recipient, campaign_status)
