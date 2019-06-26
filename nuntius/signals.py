from django.db import transaction
from django.dispatch import receiver

from nuntius.actions import update_subscriber
from nuntius.models import CampaignSentEvent, CampaignSentStatusType, AbstractSubscriber

try:
    from anymail.signals import tracking, EventType
except ImportError:
    pass
else:
    actions = {
        EventType.SENT: (CampaignSentStatusType.OK, None),
        EventType.REJECTED: (CampaignSentStatusType.REJECTED, None),
        EventType.FAILED: (CampaignSentStatusType.ERROR, None),
        EventType.BOUNCED: (
            CampaignSentStatusType.BOUNCED,
            AbstractSubscriber.STATUS_BOUNCED,
        ),
        EventType.UNSUBSCRIBED: (
            CampaignSentStatusType.UNSUBSCRIBED,
            AbstractSubscriber.STATUS_UNSUBSCRIBED,
        ),
        EventType.COMPLAINED: (
            CampaignSentStatusType.COMPLAINED,
            AbstractSubscriber.STATUS_COMPLAINED,
        ),
    }

    @receiver(tracking, dispatch_uid="nuntius_anymail_tracking")
    def handle_anymail(sender, event, esp_name, **kwargs):
        campaign_action, subscriber_action = actions.get(event.event_type, (None, None))

        try:
            with transaction.atomic():
                c = CampaignSentEvent.objects.select_for_update().get(
                    esp_message_id=event.message_id
                )
                if campaign_action is not None:
                    c.result = campaign_action
                if event.event_type == EventType.OPENED:
                    c.open_count = c.open_count + 1
                if event.event_type == EventType.CLICKED:
                    c.click_count = c.click_count + 1
                c.save()
        except CampaignSentEvent.DoesNotExist:
            pass

        if event.event_type == EventType.BOUNCED:
            # in cases of soft bounces (grouped by Anymail with hard bounces in the BOUNCED event type)
            # we do not want to update the subscriber status
            if (
                esp_name == "Amazon SES"
                and event.esp_event.get("bounce", {}).get("bounceType") != "Permanent"
            ):
                subscriber_action = None

            elif esp_name == "Postmark" and event.esp_event.get("Type") != "HardBounce":
                subscriber_action = None

        if subscriber_action is not None:
            update_subscriber(event.recipient, subscriber_action)
