from functools import reduce

from celery.app.control import Inspect
from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.db.models import fields, Q
from django.utils.translation import gettext as _

from mailer.celery import mailer_celery_app


def segment_cts_q():
    segment_cts_qs = [Q(app_label=models.split('.')[0], model=models.split('.')[1]) for models in
                      settings.MAILER_SEGMENT_MODELS]
    return reduce(lambda q1, q2: q1 | q2, segment_cts_qs)


def segment_cts():
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
        (STATUS_ERROR, _("Error"))
    )

    _task = None
    task_uuid = fields.UUIDField(_("Celery tasks identifier"), db_index=True, null=True, blank=True, default=None)

    name = fields.CharField(_("Name (invisible to subscribers)"), max_length=255)
    created = fields.DateTimeField(auto_now_add=True)
    updated = fields.DateTimeField(auto_now=True)

    message_from_name = fields.CharField(_("\"From\" name"), max_length=255, blank=True)
    message_from_email = fields.EmailField(_("\"From\" email address"), max_length=255)
    message_reply_to_name = fields.CharField(_("\"Reply to\" name"), max_length=255, blank=True)
    message_reply_to_email = fields.CharField(_("\"Reply to\" email address"), max_length=255, blank=True)
    message_subject = fields.CharField(_("Message subject line"), max_length=255, blank=True)
    message_content_html = fields.TextField(_("Message content (HTML)"), blank=True)
    message_content_text = fields.TextField(_("Message content (text)"))

    segment_content_type = models.ForeignKey(ContentType, on_delete=models.PROTECT, limit_choices_to=segment_cts_q)
    segment_id = models.CharField(max_length=255)
    segment = EditableGenericForeignKey('segment_content_type', 'segment_id')

    status = fields.IntegerField(choices=STATUS_CHOICES, default=STATUS_WAITING)

    def get_task_and_update_status(self):
        if self._task is not None:
            return self._task
        if self.task_uuid is None:
            return None
        res = Inspect(app=mailer_celery_app).query_task(self.task_uuid)

        for host_tasks in res.values():
            if host_tasks.get(str(self.task_uuid)) is not None:
                self._task = host_tasks[str(self.task_uuid)]
                self.status = Campaign.STATUS_SENDING
                self.save(update_fields=['status'])

                return host_tasks[str(self.task_uuid)]

        self.task_uuid = None
        update_fields = ['task_uuid']

        if self.status == Campaign.STATUS_SENDING:
            self.status = Campaign.STATUS_WAITING
            update_fields.append('status')

        self.save(update_fields=update_fields)

        return None

    def get_sent_count(self):
        return CampaignSentEvent.objects.filter(campaign=self).exclude(result=CampaignSentEvent.RESULT_PENDING).count()

    def get_ok_count(self):
        return CampaignSentEvent.objects.filter(campaign=self).filter(result=CampaignSentEvent.RESULT_OK).count()

    def get_bounced_count(self):
        return CampaignSentEvent.objects.filter(campaign=self).filter(result=CampaignSentEvent.RESULT_BOUNCED).count()

    def get_complained_count(self):
        return CampaignSentEvent.objects.filter(campaign=self).filter(result=CampaignSentEvent.RESULT_COMPLAINED).count()

    def get_blocked_count(self):
        return CampaignSentEvent.objects.filter(campaign=self).filter(result=CampaignSentEvent.RESULT_BLOCKED).count()


class BaseSegment:
    def get_display_name(self):
        raise NotImplementedError()

    def get_queryset(self):
        raise NotImplementedError()

    def get_subscriber_count(self):
        raise NotImplementedError


class BaseSubscriber:
    STATUS_SUBSCRIBED = 1
    STATUS_UNSUBSCRIBED = 2
    STATUS_BOUNCED = 3
    STATUS_COMPLAINED = 4
    STATUS_CHOICES = (
        (STATUS_SUBSCRIBED, _("Subscribed")),
        (STATUS_UNSUBSCRIBED, _("Unsubscribed")),
        (STATUS_BOUNCED, _("Bounced")),
        (STATUS_COMPLAINED, _("Complained"))
    )

    def get_subscriber_status(self):
        if hasattr(self, 'subscriber_status'):
            return self.subscriber_status
        raise NotImplementedError()

    def set_subscriber_status(self, status):
        if hasattr(self, 'subscriber_status'):
            self.subscriber_status = status
            return
        raise NotImplementedError()

    def get_subscriber_id(self):
        if hasattr(self, 'id'):
            return self.id

        raise NotImplementedError

    def get_subscriber_email(self):
        if hasattr(self, 'email'):
            return self.email

        raise NotImplementedError()


class CampaignSentEvent(models.Model):
    RESULT_PENDING = 'P'
    RESULT_REFUSED = 'RE'
    RESULT_OK = 'OK'
    RESULT_BOUNCED = 'BC'
    RESULT_COMPLAINED = 'C'
    RESULT_BLOCKED = 'BL'
    RESULT_CHOICES = (
        RESULT_PENDING, _("Sending"),
        RESULT_PENDING, _("Refused by server"),
        RESULT_OK, _("Sent"),
        RESULT_BOUNCED, _("Bounced"),
        RESULT_COMPLAINED, _("Complained"),
        RESULT_BOUNCED, _("Bounced")
    )

    subscriber = models.ForeignKey(
        settings.MAILER_SUBSCRIBER_MODEL,
        models.SET_NULL,
        verbose_name=_("Subscriber"),
        null=True,
        blank=True,
    )
    email = models.EmailField(_("Email adress at event time"))
    campaign = models.ForeignKey('Campaign', models.CASCADE, _("Campaign"))
    datetime = models.DateTimeField(auto_now_add=True)
    result = models.CharField(_("Operation result"), max_length=2, default=RESULT_PENDING)

    class Meta:
        unique_together = ('campaign', 'subscriber')
