import re
from secrets import token_urlsafe

from django.db import models
from django.db.models import fields, Sum, Value
from django.db.models.functions import Coalesce
from django.template import Template
from django.utils.functional import cached_property
from django.utils.translation import gettext_lazy as _
from stdimage import StdImageField

from nuntius import app_settings
from nuntius.models.mixins import AbstractCampaign
from nuntius.utils.messages import generate_plain_text

MOSAICO_TO_DJANGO_TEMPLATE_VARS = re.compile(r"\[([A-Z_-]+)]")


class Campaign(AbstractCampaign):
    message_from_name = fields.CharField(_('"From" name'), max_length=255, blank=True)
    message_from_email = fields.EmailField(_('"From" email address'), max_length=255)
    message_reply_to_name = fields.CharField(
        _('"Reply to" name'), max_length=255, blank=True
    )
    message_reply_to_email = fields.CharField(
        _('"Reply to" email address'), max_length=255, blank=True
    )
    message_subject = fields.CharField(
        _("Message subject line"), max_length=255, blank=True
    )
    message_mosaico_data = fields.TextField(_("Mosaico data"), blank=True)
    message_content_html = fields.TextField(_("Message content (HTML)"), blank=True)
    message_content_text = fields.TextField(_("Message content (text)"), blank=True)

    def save(self, *args, **kwargs):
        if self.message_mosaico_data:
            self.message_content_text = generate_plain_text(self.message_content_html)
        super().save(*args, **kwargs)

    def get_sent_count(self):
        return (
            CampaignSentEvent.objects.filter(campaign=self)
            .exclude(result=CampaignSentStatusType.PENDING)
            .count()
        )

    def get_ok_count(self):
        return (
            CampaignSentEvent.objects.filter(campaign=self)
            .filter(result=CampaignSentStatusType.OK)
            .count()
        )

    def get_bounced_count(self):
        return (
            CampaignSentEvent.objects.filter(campaign=self)
            .filter(result=CampaignSentStatusType.BOUNCED)
            .count()
        )

    def get_complained_count(self):
        return (
            CampaignSentEvent.objects.filter(campaign=self)
            .filter(result=CampaignSentStatusType.COMPLAINED)
            .count()
        )

    def get_blocked_count(self):
        return (
            CampaignSentEvent.objects.filter(campaign=self)
            .filter(result=CampaignSentStatusType.BLOCKED)
            .count()
        )

    def get_open_count(self):
        return CampaignSentEvent.objects.filter(campaign=self).aggregate(
            count=Coalesce(Sum("open_count"), Value(0))
        )["count"]

    def get_unique_open_count(self):
        return (
            CampaignSentEvent.objects.filter(campaign=self)
            .filter(open_count__gt=0)
            .count()
        )

    def get_click_count(self):
        return CampaignSentEvent.objects.filter(campaign=self).aggregate(
            count=Coalesce(Sum("click_count"), Value(0))
        )["count"]

    def get_unique_click_count(self):
        return (
            CampaignSentEvent.objects.filter(campaign=self)
            .filter(click_count__gt=0)
            .count()
        )

    def get_event_for_subscriber(self, subscriber):
        event, _ = CampaignSentEvent.objects.get_or_create(
            campaign=self,
            subscriber=subscriber,
            defaults={"email": subscriber.get_subscriber_email()},
        )
        return event

    def __repr__(self):
        return f"Campaign(id={self.id!r}, name={self.name!r})"

    @cached_property
    def html_template(self):
        return Template(self.message_content_html)

    @cached_property
    def text_template(self):
        return Template(self.message_content_text)

    @property
    def from_header(self):
        if self.message_from_name:
            return f"{self.message_from_name} <{self.message_from_email}>"
        return self.message_from_email

    @property
    def reply_to_header(self):
        if self.message_reply_to_email:
            if self.message_reply_to_name:
                return f"{self.message_reply_to_name} <{self.message_reply_to_email}>"
            return self.message_reply_to_email
        return None

    class Meta:
        verbose_name = _("email campaign")
        verbose_name_plural = _("email campaigns")


class CampaignSentStatusType:
    PENDING = "P"
    UNKNOWN = "?"
    REJECTED = "RE"
    OK = "OK"
    BOUNCED = "BC"
    COMPLAINED = "C"
    UNSUBSCRIBED = "U"
    BLOCKED = "BL"
    ERROR = "E"

    CHOICES = (
        (PENDING, _("Sending")),
        (UNKNOWN, _("Unknown")),
        (REJECTED, _("Rejected by server")),
        (OK, _("Sent")),
        (BOUNCED, _("Bounced")),
        (COMPLAINED, _("Complained")),
        (UNSUBSCRIBED, _("Unsubscribed")),
        (BLOCKED, _("Blocked temporarily")),
        (ERROR, _("Error")),
    )


class CampaignSentEvent(models.Model):
    subscriber = models.ForeignKey(
        app_settings.NUNTIUS_SUBSCRIBER_MODEL,
        models.SET_NULL,
        verbose_name=_("Subscriber"),
        null=True,
        blank=True,
    )
    email = models.EmailField(_("Email address at sending time"))
    campaign = models.ForeignKey(
        "Campaign", models.CASCADE, verbose_name=_("Campaign"), null=True, blank=True
    )
    datetime = models.DateTimeField(_("Sending time"), auto_now_add=True)
    result = models.CharField(
        _("Operation result"),
        max_length=2,
        default=CampaignSentStatusType.PENDING,
        choices=CampaignSentStatusType.CHOICES,
    )
    esp_message_id = models.CharField(
        _("ID given by the sending server"),
        unique=True,
        max_length=255,
        null=True,
        editable=False,
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
    open_count = models.IntegerField(_("Open count"), default=0, editable=False)
    click_count = models.IntegerField(_("Click count"), default=0, editable=False)

    class Meta:
        unique_together = ("campaign", "subscriber")
        verbose_name = _("email sent event")
        verbose_name_plural = _("email sent events")
        # this (email, datetime) index is required to handle bouncing rules
        # see func:`nuntius.actions.update_subscriber`
        indexes = [
            models.Index(fields=["email", "datetime"]),
            models.Index(fields=["subscriber", "datetime"]),
        ]
        ordering = ["-datetime"]


class MosaicoImage(models.Model):
    file = StdImageField(upload_to="mosaico", variations={"thumbnail": (90, 90)})
    created = fields.DateTimeField(auto_now_add=True)
