from functools import reduce
from secrets import token_urlsafe

from celery.app.control import Inspect
from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ObjectDoesNotExist
from django.db import models
from django.db.models import fields, Q, Sum, Value
from django.db.models.functions import Coalesce
from django.utils.translation import gettext_lazy as _
from stdimage import StdImageField

from nuntius.celery import nuntius_celery_app
from nuntius.utils import generate_plain_text, NoCeleryError


def segment_cts_q():
    segment_cts_qs = [
        Q(app_label=models.split(".")[0], model=models.split(".")[1])
        for models in settings.NUNTIUS_SEGMENT_MODELS
    ]
    return reduce(lambda q1, q2: q1 | q2, segment_cts_qs)


def segment_cts():
    if settings.NUNTIUS_SEGMENT_MODELS == []:
        return ContentType.objects.none()
    return ContentType.objects.filter(segment_cts_q())


class EditableGenericForeignKey(GenericForeignKey):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.editable = True

    def save_object_data(self, value):
        return value

    def value_from_object(self, obj):
        return getattr(obj, self.name)


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

    _task = None
    task_uuid = fields.UUIDField(
        _("Celery tasks identifier"), db_index=True, null=True, blank=True, default=None
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

    segment_content_type = models.ForeignKey(
        ContentType, on_delete=models.PROTECT, limit_choices_to=segment_cts_q, null=True
    )
    segment_id = models.CharField(max_length=255, null=True)
    segment = EditableGenericForeignKey("segment_content_type", "segment_id")

    status = fields.IntegerField(choices=STATUS_CHOICES, default=STATUS_WAITING)

    def save(self, *args, **kwargs):
        if self.message_mosaico_data:
            self.message_content_text = generate_plain_text(self.message_content_html)
        super().save(*args, **kwargs)

    def get_task_and_update_status(self):
        # caching
        if self._task is not None:
            return self._task

        # no task known for this campaign
        if self.task_uuid is None:
            if self.status == Campaign.STATUS_SENDING:
                self.status = Campaign.STATUS_WAITING
                self.save(update_fields=["status"])
            return

        res = Inspect(app=nuntius_celery_app).query_task(self.task_uuid)

        # celery is down
        if res is None:
            raise NoCeleryError()

        for host_tasks in res.values():
            if host_tasks.get(str(self.task_uuid)) is None:
                continue
            self.status = Campaign.STATUS_SENDING
            self.save(update_fields=["status"])
            self._task = host_tasks[str(self.task_uuid)]

            return host_tasks[str(self.task_uuid)]

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

    def __str__(self):
        return self.name

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


class BaseSubscriberManager(models.Manager):
    def set_subscriber_status(self, email_address, status):
        try:
            subscriber = self.get(email=email_address)
        except ObjectDoesNotExist:
            return
        subscriber.subscriber_status = status
        subscriber.save(update_fields=["subscriber_status"])


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
        settings.NUNTIUS_SUBSCRIBER_MODEL,
        models.SET_NULL,
        verbose_name=_("Subscriber"),
        null=True,
        blank=True,
    )
    email = models.EmailField(_("Email address at sending time"))
    campaign = models.ForeignKey("Campaign", models.CASCADE, verbose_name=_("Campaign"))
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
        max_length=12, default=generate_tracking_id, null=True, editable=False
    )
    open_count = models.IntegerField(_("Open count"), default=0, editable=False)
    click_count = models.IntegerField(_("Click count"), default=0, editable=False)

    class Meta:
        unique_together = ("campaign", "subscriber")
        verbose_name = _("Sent event")
        verbose_name_plural = _("Sent events")


class MosaicoImage(models.Model):
    file = StdImageField(upload_to="mosaico", variations={"thumbnail": (90, 90)})
    created = fields.DateTimeField(auto_now_add=True)
