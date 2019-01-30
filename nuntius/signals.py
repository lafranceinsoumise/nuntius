from django.dispatch import receiver

from nuntius.actions import handle_bounce


def _handle_anymail(sender, event, esp_name, **kwargs):
    if event.event_type == "bounced":
        handle_bounce(event.recipient)


try:
    from anymail.signals import tracking

    @receiver(tracking, dispatch_uid="nuntius_anymail_tracking")
    def handle_anymail(sender, event, esp_name, **kwargs):
        _handle_anymail(sender, event, esp_name, **kwargs)


except ImportError:
    pass
