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

        if event.event_type in actions:
            try:
                c = CampaignSentEvent.objects.get(esp_message_id=event.message_id)
                c.result = actions[event.event_type][0]
                c.save()
            except CampaignSentEvent.DoesNotExist:
                pass

            if actions[event.event_type][1] is not None:
                update_subscriber(event.recipient, actions[event.event_type][1])


except ImportError:
    pass
