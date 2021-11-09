from secrets import token_bytes

from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.db.models import fields
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from nuntius import app_settings


class CampaignStatusType:
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


class AbstractCampaignQuerySet(models.QuerySet):
    def outbox(self):
        now = timezone.now()
        return (
            self.filter(status__lt=CampaignStatusType.STATUS_SENT)
            .exclude(start_date__isnull=False, start_date__gt=now)
            .exclude(end_date__isnull=False, end_date__lt=now)
        )


class AbstractCampaign(CampaignStatusType, models.Model):
    objects = AbstractCampaignQuerySet.as_manager()

    name = fields.CharField(_("Name (invisible to subscribers)"), max_length=255)
    created = fields.DateTimeField(_("Created"), auto_now_add=True)
    updated = fields.DateTimeField(_("Updated"), auto_now=True)
    first_sent = fields.DateTimeField(_("First sent"), blank=True, null=True)

    segment = models.ForeignKey(
        to=app_settings.NUNTIUS_SEGMENT_MODEL,
        verbose_name=_("Subscriber segment"),
        on_delete=models.SET_NULL,
        null=True,
    )
    start_date = models.DateTimeField(
        verbose_name=_("Campaign start date"), null=True, blank=True
    )
    end_date = models.DateTimeField(
        verbose_name=_("Campaign end date"), null=True, blank=True
    )

    status = fields.IntegerField(
        choices=CampaignStatusType.STATUS_CHOICES,
        default=CampaignStatusType.STATUS_WAITING,
    )

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

    def get_subscribers_queryset(self):
        if self.segment is None:
            model = app_settings.NUNTIUS_SUBSCRIBER_MODEL
            model_class = ContentType.objects.get(
                app_label=model.split(".")[0], model=model.split(".")[1].lower()
            ).model_class()
            return model_class.objects.all()
        else:
            return self.segment.get_subscribers_queryset()

    def __str__(self):
        return self.name

    def __repr__(self):
        return f"AbstractCampaign(id={self.id!r}, name={self.name!r})"

    class Meta:
        abstract = True
        verbose_name = _("Abstract campaign")
        verbose_name_plural = _("Abstract campaigns")
