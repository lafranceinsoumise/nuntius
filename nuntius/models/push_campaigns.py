from secrets import token_urlsafe

from django.db import models, IntegrityError
from django.db.models import fields
from django.utils.translation import gettext_lazy as _

from nuntius import app_settings
from nuntius.models import AbstractCampaign


class PushCampaign(AbstractCampaign):
    notification_title = fields.CharField(_("Notification title"), max_length=255)
    notification_url = fields.CharField(_("Notification URL"), max_length=255)
    notification_body = fields.TextField(_("Notification body"))
    notification_tag = fields.CharField(
        _("Notification tag"),
        null=True,
        blank=True,
        max_length=255,
        help_text=_(
            "Tagging a notification allows replacing it by pushing another with the same tag value"
        ),
    )
    notification_icon = fields.CharField(
        _("Notification icon"), null=True, blank=True, max_length=255
    )

    def get_sent_count(self):
        return (
            PushCampaignSentEvent.objects.filter(campaign=self)
            .exclude(result=PushCampaignSentStatusType.PENDING)
            .count()
        )

    def get_ok_count(self):
        return (
            PushCampaignSentEvent.objects.filter(campaign=self)
            .filter(result=PushCampaignSentStatusType.OK)
            .count()
        )

    def get_ko_count(self):
        return (
            PushCampaignSentEvent.objects.filter(campaign=self)
            .filter(result=PushCampaignSentStatusType.ERROR)
            .count()
        )

    def get_click_count(self):
        return (
            PushCampaignSentEvent.objects.filter(campaign=self)
            .filter(click_count__gt=0)
            .count()
        )

    def get_event_for_subscriber(self, subscriber):
        event, _ = PushCampaignSentEvent.objects.get_or_create(
            campaign=self, subscriber=subscriber
        )
        return event

    def __repr__(self):
        return f"PushCampaign(id={self.id!r}, name={self.name!r})"

    class Meta:
        verbose_name = _("push campaign")
        verbose_name_plural = _("push campaigns")


class PushCampaignSentStatusType:
    UNKNOWN = "?"
    PENDING = "P"
    OK = "OK"
    ERROR = "E"

    CHOICES = (
        (UNKNOWN, _("Unknown")),
        (PENDING, _("Sending")),
        (OK, _("Sent")),
        (ERROR, _("Error")),
    )


class PushCampaignSentEvent(models.Model):
    subscriber = models.ForeignKey(
        app_settings.NUNTIUS_SUBSCRIBER_MODEL,
        models.SET_NULL,
        verbose_name=_("Subscriber"),
        null=True,
        blank=True,
    )
    campaign = models.ForeignKey(
        "PushCampaign", models.CASCADE, verbose_name=_("Push campaign")
    )
    datetime = models.DateTimeField(_("Sending time"), auto_now_add=True)
    result = models.CharField(
        _("Operation result"),
        max_length=2,
        default=PushCampaignSentStatusType.PENDING,
        choices=PushCampaignSentStatusType.CHOICES,
    )

    def generate_tracking_id():
        return token_urlsafe(9)

    tracking_id = models.CharField(
        max_length=12,
        default=generate_tracking_id,
        null=True,
        editable=False,
        unique=True,
    )

    click_count = models.IntegerField(_("Click count"), default=0, editable=False)

    @property
    def devices(self):
        return self.subscriber.get_subscriber_push_devices()

    class Meta:
        verbose_name = _("push sent event")
        verbose_name_plural = _("push sent events")
        constraints = [
            models.UniqueConstraint(
                name="unique_push_campaign_subscriber",
                fields=["campaign", "subscriber"],
            )
        ]
        indexes = [models.Index(fields=["subscriber", "datetime"])]
        ordering = ["-datetime"]
