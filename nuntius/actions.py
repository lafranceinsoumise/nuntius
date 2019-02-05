from django.conf import settings
from django.contrib.contenttypes.models import ContentType


def update_subscriber(email, status):
    model = settings.NUNTIUS_SUBSCRIBER_MODEL
    model_class = ContentType.objects.get(
        app_label=model.split(".")[0], model=model.split(".")[1].lower()
    ).model_class()
    model_class.objects.set_subscriber_status(email, status)
