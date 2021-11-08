from django.db import models
from push_notifications.models import APNSDevice, GCMDevice

from nuntius.models import BaseSubscriber, BaseSegment


class Segment(BaseSegment, models.Model):
    id = models.CharField(max_length=255, unique=True, primary_key=True)

    def get_display_name(self):
        return self.id

    def get_subscribers_queryset(self):
        return Subscriber.objects.filter(segments__id=self.id)

    def get_subscribers_count(self):
        return (
            self.get_subscribers_queryset()
            .filter(subscriber_status=BaseSubscriber.STATUS_SUBSCRIBED)
            .count()
        )

    def __str__(self):
        return self.get_display_name()


class Subscriber(BaseSubscriber):
    segments = models.ManyToManyField("standalone.Segment")

    def get_subscriber_push_devices(self):
        return [
            device
            for device in APNSDevice.objects.filter(
                registration_id=self.email, active=True
            )
        ] + [
            device
            for device in GCMDevice.objects.filter(
                registration_id=self.email, active=True
            )
        ]

    def get_subscriber_data(self):
        return {
            "segments": ", ".join(str(s) for s in self.segments.all()),
            **super().get_subscriber_data(),
        }

    def __str__(self):
        return self.get_subscriber_email()
