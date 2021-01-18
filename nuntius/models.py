import re
from secrets import token_urlsafe, token_bytes

from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ObjectDoesNotExist
from django.db import models
from django.db.models import fields, Sum, Value
from django.db.models.functions import Coalesce
from django.template import Template
from django.utils.functional import cached_property
from django.utils.translation import gettext_lazy as _
from stdimage import StdImageField

from nuntius import app_settings
from nuntius.utils.messages import generate_plain_text

MOSAICO_TO_DJANGO_TEMPLATE_VARS = re.compile(r"\[([A-Z_-]+)]")


class Campaign(models.Model):
    STATUS_WAITING = 0
    STATUS_SENDING = 1
    STATUS_SENT = 2
    STATUS_ERROR = 3
    STATUS_CHOICES = (
        (STATUS_WAITING, _("Waiting")),
        (STATUS_SENDING, _("Sending")),
        (STATUS_SENT, _("Sent")),
        (STATUS_ERROR, _("Error")),
    )

    name = fields.CharField(_("Name (invisible to subscribers)"), max_length=255)
    created = fields.DateTimeField(_("Created"), auto_now_add=True)
    updated = fields.DateTimeField(_("Updated"), auto_now=True)
    first_sent = fields.DateTimeField(_("First sent"), blank=True, null=True)

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

    segment = models.ForeignKey(
        to=app_settings.NUNTIUS_SEGMENT_MODEL,
        verbose_name=_("Subscriber segment"),
        on_delete=models.SET_NULL,
        null=True,
    )

    status = fields.IntegerField(choices=STATUS_CHOICES, default=STATUS_WAITING)

    utm_name = fields.CharField(
        _("UTM name (visible to subscribers)"),
        max_length=255,
        blank=True,
        help_text=_(
            "Value used as utm_campaign parameter, used by various analytics tools."
        ),
    )

    def generate_signature_key():
        return token_bytes(20)

    signature_key = fields.BinaryField(max_length=20, default=generate_signature_key)

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

    def get_subscribers_queryset(self):
        if self.segment is None:
            model = app_settings.NUNTIUS_SUBSCRIBER_MODEL
            model_class = ContentType.objects.get(
                app_label=model.split(".")[0], model=model.split(".")[1].lower()
            ).model_class()
            return model_class.objects.all()
        else:
            return self.segment.get_subscribers_queryset()

    def get_event_for_subscriber(self, subscriber):
        event, _ = CampaignSentEvent.objects.get_or_create(
            campaign=self,
            subscriber=subscriber,
            defaults={"email": subscriber.get_subscriber_email()},
        )
        return event

    def __str__(self):
        return self.name

    def __repr__(self):
        return f"Campaign(id={self.id!r}, name={self.name!r})"

    @cached_property
    def html_template(self):
        from nuntius.messages import insert_tracking_image_template

        return Template(insert_tracking_image_template(self.message_content_html))

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
        verbose_name = _("Campaign")
        verbose_name_plural = _("Campaigns")


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
        verbose_name = _("Sent event")
        verbose_name_plural = _("Sent events")
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
