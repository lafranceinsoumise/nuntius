from django.core.exceptions import ObjectDoesNotExist
from django.db import models
from django.db.models import fields
from django.utils.translation import gettext_lazy as _


class BaseSegment:
    def get_display_name(self):
        raise NotImplementedError()

    def get_subscribers_queryset(self):
        raise NotImplementedError()

    def get_subscribers_count(self):
        raise NotImplementedError

    class Meta:
        swappable = "NUNTIUS_SEGMENT_MODEL"


class BaseSubscriberManager(models.Manager):
    def set_subscriber_status(self, email_address, status):
        try:
            subscriber = self.get(email=email_address)
        except ObjectDoesNotExist:
            return
        subscriber.subscriber_status = status
        subscriber.save(update_fields=["subscriber_status"])

    def get_subscriber(self, email_address):
        return self.filter(email=email_address).last()


class AbstractSubscriber:
    STATUS_SUBSCRIBED = 1
    STATUS_UNSUBSCRIBED = 2
    STATUS_BOUNCED = 3
    STATUS_COMPLAINED = 4
    STATUS_CHOICES = (
        (STATUS_SUBSCRIBED, _("Subscribed")),
        (STATUS_UNSUBSCRIBED, _("Unsubscribed")),
        (STATUS_BOUNCED, _("Bounced")),
        (STATUS_COMPLAINED, _("Complained")),
    )

    def get_subscriber_status(self):
        if hasattr(self, "subscriber_status"):
            return self.subscriber_status
        raise NotImplementedError()

    def get_subscriber_email(self):
        if hasattr(self, "email"):
            return self.email

        raise NotImplementedError()

    def get_subscriber_push_devices(self):
        if hasattr(self, "push_devices"):
            return self.push_devices

        return []

    def get_subscriber_data(self):
        return {"email": self.get_subscriber_email()}

    class Meta:
        abstract = True


class BaseSubscriber(AbstractSubscriber, models.Model):
    objects = BaseSubscriberManager()

    email = fields.EmailField(max_length=255)
    subscriber_status = fields.IntegerField(choices=AbstractSubscriber.STATUS_CHOICES)

    class Meta(AbstractSubscriber.Meta):
        swappable = "NUNTIUS_SUBSCRIBER_MODEL"
