from django.conf import settings
from django.contrib.contenttypes.models import ContentType

from nuntius.models import BaseSubscriber


def handle_bounce(email):
    model = settings.NUNTIUS_SUBSCRIBER_MODEL
    model_class = ContentType.objects.get(
        app_label=model.split(".")[0], model=model.split(".")[1].lower()
    ).model_class()
    model_class.objects.set_subscriber_status(email, BaseSubscriber.STATUS_BOUNCED)
