from django.db import transaction
from django.dispatch import receiver

from nuntius.actions import update_subscriber
from nuntius.models import CampaignSentEvent, CampaignSentStatusType, AbstractSubscriber

try:
    from anymail.signals import tracking, EventType

    @receiver(tracking, dispatch_uid="nuntius_anymail_tracking")
    def handle_anymail(sender, event, esp_name, **kwargs):
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

        try:
            with transaction.atomic():
                c = CampaignSentEvent.objects.select_for_update().get(
                    esp_message_id=event.message_id
                )
                if event.event_type in actions:
                    c.result = actions[event.event_type][0]
                if event.event_type == EventType.OPENED:
                    c.open_count = c.open_count + 1
                if event.event_type == EventType.CLICKED:
                    c.click_count = c.click_count + 1
                c.save()
        except CampaignSentEvent.DoesNotExist:
            pass

            if actions[event.event_type][1] is not None:
                update_subscriber(event.recipient, actions[event.event_type][1])


except ImportError:
    pass
