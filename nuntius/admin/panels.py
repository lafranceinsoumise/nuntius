import json

from django.conf import settings
from django.contrib import admin
from django import forms
from django.contrib.contenttypes.models import ContentType
from django.http import HttpResponseBadRequest, HttpResponse, JsonResponse
from django.shortcuts import redirect
from django.template.response import TemplateResponse
from django.urls import reverse, path, resolve
from django.utils.html import format_html, format_html_join
from django.utils.safestring import mark_safe
from django.utils.translation import gettext as _
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.generic import CreateView

from nuntius.admin.fields import GenericModelChoiceField
from nuntius.celery import nuntius_celery_app
from nuntius.models import segment_cts, Campaign, MosaicoImage, CampaignSentEvent
from nuntius._tasks import send_campaign
from nuntius.utils import NoCeleryError, build_absolute_uri


def subscriber_class():
    model = settings.NUNTIUS_SUBSCRIBER_MODEL
    return ContentType.objects.get(
        app_label=model.split(".")[0], model=model.split(".")[1].lower()
    ).model_class()


class CampaignAdminForm(forms.ModelForm):
    segment = GenericModelChoiceField(
        querysets=lambda: [ct.model_class().objects.all() for ct in set(segment_cts())],
        required=False,
    )

    def clean(self):
        cleaned_data = super().clean()
        segment = cleaned_data.get("segment")

        if segment:
            self.instance.segment = segment

        return cleaned_data

    class Meta:
        exclude = ("segment_content_type", "segment_id")


class MosaicoImageUploadView(CreateView):
    model = MosaicoImage
    fields = ("file",)

    def image_dict(self, image):
        return {
            "name": image.file.name,
            "size": image.file.size,
            "url": build_absolute_uri(self.request, image.file.url),
            "deleteUrl": build_absolute_uri(self.request, image.file.url),
            "deleteType": "DELETE",
            "thumbnailUrl": build_absolute_uri(self.request, image.file.thumbnail.url),
        }

    def form_invalid(self, form):
        return HttpResponseBadRequest()

    def form_valid(self, form):
        self.object = form.save()

        return JsonResponse({"files": [self.image_dict(self.object)]})

    def get(self, *args, **kwargs):
        return JsonResponse(
            {"files": [self.image_dict(image) for image in MosaicoImage.objects.all()]}
        )


@admin.register(Campaign)
class CampaignAdmin(admin.ModelAdmin):
    fieldsets = (
        (
            None,
            {
                "fields": (
                    "created",
                    "updated",
                    "name",
                    "message_from_name",
                    "message_from_email",
                    "message_reply_to_name",
                    "message_reply_to_email",
                    "message_subject",
                )
            },
        ),
        (
            _("Content"),
            {
                "fields": (
                    "available_variables",
                    "mosaico_buttons",
                    "message_content_text",
                )
            },
        ),
        (
            _("Sending details"),
            {
                "fields": (
                    "first_sent",
                    "segment",
                    "segment_subscribers",
                    "status",
                    "send_button",
                    "task_uuid",
                    "task_state",
                )
            },
        ),
        (
            _("Sending reports"),
            {
                "fields": (
                    "sent_to",
                    "sent_ok",
                    "sent_bounced",
                    "sent_complained",
                    "sent_blocked",
                    "unique_open_count",
                    "unique_click_count",
                    "open_count",
                    "click_count",
                )
            },
        ),
    )
    list_display = (
        "name",
        "message_subject",
        "segment",
        "status",
        "send_button",
        "sent_to",
    )
    list_filter = ("status",)
    form = CampaignAdminForm
    readonly_fields = (
        "created",
        "updated",
        "first_sent",
        "segment_subscribers",
        "status",
        "send_button",
        "available_variables",
        "mosaico_buttons",
        "message_content_text",
        "sent_to",
        "sent_ok",
        "sent_bounced",
        "sent_complained",
        "sent_blocked",
        "unique_open_count",
        "unique_click_count",
        "open_count",
        "click_count",
        "task_uuid",
        "task_state",
    )
    save_as = True

    def get_object(self, request, object_id, from_field=None):
        object = super().get_object(request, object_id, from_field=from_field)
        try:
            self.task = object.get_task_and_update_status()
        except NoCeleryError:
            self.task = False

        return object

    def save_model(self, request, campaign, form, change):
        if "_saveasnew" in request.POST:
            original_pk = resolve(request.path).kwargs["object_id"]
            original_campaign = Campaign.objects.get(id=original_pk)
            campaign.message_content_html = original_campaign.message_content_html
            campaign.message_mosaico_data = original_campaign.message_mosaico_data

        return super().save_model(request, campaign, form, change)

    def segment_subscribers(self, instance):
        if instance.segment is None:
            return subscriber_class().objects.count()
        return instance.segment.get_subscribers_count()

    segment_subscribers.short_description = _("Subscribers")

    def sent_to(self, instance):
        return format_html(
            '<a href="{}">{}</a>',
            reverse("admin:nuntius_campaignsentevent_changelist")
            + "?campaign_id__exact="
            + str(instance.pk),
            str(instance.get_sent_count()),
        )

    sent_to.short_description = _("Sent to")

    def sent_ok(self, instance):
        return instance.get_ok_count()

    sent_ok.short_description = _("Ok")

    def sent_bounced(self, instance):
        return instance.get_bounced_count()

    sent_bounced.short_description = _("Bounced")

    def sent_complained(self, instance):
        return instance.get_complained_count()

    sent_complained.short_description = _("Complained")

    def sent_blocked(self, instance):
        return instance.get_blocked_count()

    sent_blocked.short_description = _("Blocked")

    def open_count(self, instance):
        return instance.get_open_count()

    open_count.short_description = _("Open count")

    def unique_open_count(self, instance):
        return instance.get_unique_open_count()

    unique_open_count.short_description = _("Unique open count")

    def click_count(self, instance):
        return instance.get_click_count()

    click_count.short_description = _("Click count")

    def unique_click_count(self, instance):
        return instance.get_unique_click_count()

    unique_click_count.short_description = _("Unique click count")

    def task_state(self, instance):
        task = self.task
        if task:
            return task[0]
        if instance.task_uuid is None:
            return "-"

        if task is False:
            return _("Connection to celery failed")

        return _(
            "A sending task has been scheduled, is not launched yet, or has been stopped for unkown reasons."
        )

    task_state.short_description = _("Send task state")

    def send_button(self, instance):
        if instance.pk is None:
            return mark_safe("-")
        if instance.status == Campaign.STATUS_SENDING:
            return format_html(
                '<a href="{}" class="button">' + _("Pause") + "</a>",
                reverse("admin:nuntius_campaign_pause", args=[instance.pk]),
            )
        if instance.task_uuid is None:
            return format_html(
                '<a href="{}" class="button">' + _("Send") + "</a>",
                reverse("admin:nuntius_campaign_send", args=[instance.pk]),
            )

        return mark_safe("-")

    send_button.short_description = _("Send")

    def available_variables(self, instance):
        if instance.segment is not None:
            qs = instance.segment.get_subscribers_queryset()
        else:
            qs = subscriber_class().objects.all()

        data = qs.first().get_subscriber_data()

        return format_html_join(
            mark_safe("<br/>"), "<b>{{{{ {} }}}}</b> ({})", data.items()
        )

    available_variables.short_description = _(
        "Available variables (for first subscriber)"
    )

    def mosaico_buttons(self, instance):
        if instance.pk is None:
            return mark_safe("-")

        if not instance.message_mosaico_data:
            default_template = (
                settings.STATIC_URL
                + "/nuntius/templates/versafix-1/template-versafix-1.html",
                _("Default template"),
            )
            templates = getattr(
                settings, "NUNTIUS_MOSAICO_TEMPLATES", [default_template]
            )

            return format_html_join(
                " ",
                '<a href="{}" class="button">{}</a>',
                (
                    (
                        reverse("admin:nuntius_campaign_mosaico", args=[instance.pk])
                        + "#"
                        + template,
                        name,
                    )
                    for template, name in templates
                ),
            )

        return format_html(
            '<a href="{}" class="button">' + _("Access the editor") + "</a> "
            '<a href="{}" class="button" target="_blank">'
            + _("Preview result")
            + "</a>",
            reverse("admin:nuntius_campaign_mosaico", args=[instance.pk]),
            reverse("admin:nuntius_campaign_mosaico_preview", args=[instance.pk]),
        )

    mosaico_buttons.short_description = _("HTML content")

    def get_urls(self):
        return [
            path(
                "<pk>/send/",
                self.admin_site.admin_view(self.send_view),
                name="nuntius_campaign_send",
            ),
            path(
                "<pk>/pause/",
                self.admin_site.admin_view(self.pause_view),
                name="nuntius_campaign_pause",
            ),
            path(
                "<pk>/mosaico/",
                ensure_csrf_cookie(self.admin_site.admin_view(self.mosaico_view)),
                name="nuntius_campaign_mosaico",
            ),
            path(
                "<pk>/mosaico/preview/",
                self.admin_site.admin_view(self.mosaico_preview),
                name="nuntius_campaign_mosaico_preview",
            ),
            path(
                "<pk>/mosaico/save/",
                self.admin_site.admin_view(self.mosaico_save_view),
                name="nuntius_campaign_mosaico_save",
            ),
            path(
                "<pk>/mosaico/data/",
                self.admin_site.admin_view(self.mosaico_load_view),
                name="nuntius_campaign_mosaico_load",
            ),
            path(
                "<pk>/mosaico/upload/",
                self.admin_site.admin_view(MosaicoImageUploadView.as_view()),
                name="nuntius_campaign_mosaico_image_upload",
            ),
        ] + super().get_urls()

    def send_view(self, request, pk):
        campaign = Campaign.objects.get(pk=pk)
        if campaign.task_uuid is not None:
            return redirect(reverse("admin:nuntius_campaign_change", args=[pk]))

        r = send_campaign.delay(pk, build_absolute_uri(request, location="/")[:-1])
        campaign.task_uuid = r.id
        campaign.save(update_fields=["task_uuid"])

        return redirect(reverse("admin:nuntius_campaign_change", args=[pk]))

    def pause_view(self, request, pk):
        campaign = Campaign.objects.get(pk=pk)
        if campaign.task_uuid is None:
            return redirect(reverse("admin:nuntius_campaign_change", args=[pk]))

        nuntius_celery_app.control.revoke(str(campaign.task_uuid), terminate=True)

        campaign.task_uuid = None
        campaign.save(update_fields=["task_uuid"])

        return redirect(reverse("admin:nuntius_campaign_change", args=[pk]))

    def mosaico_view(self, request, pk):
        return TemplateResponse(
            request=request,
            template="nuntius/editor.html",
            context={
                "image_processor_backend_url": build_absolute_uri(
                    request, reverse("nuntius_mosaico_image_processor")
                ),
                "save_url": reverse("admin:nuntius_campaign_mosaico_save", args=[pk]),
                "image_upload_url": reverse(
                    "admin:nuntius_campaign_mosaico_image_upload", args=[pk]
                ),
                "load_data_url": reverse(
                    "admin:nuntius_campaign_mosaico_load", args=[pk]
                ),
                "change_url": reverse("admin:nuntius_campaign_change", args=[pk]),
            },
        )

    def mosaico_preview(self, request, pk):
        campaign = Campaign.objects.get(pk=pk)

        return HttpResponse(campaign.message_content_html)

    def mosaico_load_view(self, request, pk):
        campaign = Campaign.objects.get(pk=pk)

        return JsonResponse(json.loads(campaign.message_mosaico_data or "{}"))

    def mosaico_save_view(self, request, pk):
        if request.method != "POST":
            return HttpResponseBadRequest()

        html = request.POST.get("html")
        metadata = request.POST.get("metadata")
        content = request.POST.get("content")

        campaign = Campaign.objects.get(pk=pk)
        campaign.message_content_html = html
        campaign.message_mosaico_data = json.dumps(
            {"metadata": json.loads(metadata), "content": json.loads(content)}
        )
        campaign.save()

        return HttpResponse()


@admin.register(CampaignSentEvent)
class CampaignSentEventAdmin(admin.ModelAdmin):
    def has_change_permission(self, *args, **kwargs):
        return False

    def has_add_permission(self, *args, **kwargs):
        return False

    actions = None
    readonly_fields = ("subscriber_filter", "campaign_filter")
    list_filter = ("result",)
    list_display_links = None

    def get_list_display(self, request):
        list_display = ("email", "datetime", "result")
        if request.GET.get("campaign_id__exact") is None:
            list_display = ("campaign_filter", *list_display)
        if request.GET.get("subscriber_id__exact") is None:
            list_display = ("subscriber_filter", *list_display)

        return list_display

    def subscriber_filter(self, instance):
        return format_html(
            '<a href="{}">{}</a>',
            reverse("admin:nuntius_campaignsentevent_changelist")
            + "?subscriber_id__exact="
            + str(instance.subscriber_id),
            str(instance.subscriber),
        )

    subscriber_filter.short_description = _("Subscriber")

    def campaign_filter(self, instance):
        return format_html(
            "<a href={}>{}</a>",
            reverse("admin:nuntius_campaignsentevent_changelist")
            + "?campaign_id__exact="
            + str(instance.campaign_id),
            str(instance.campaign),
        )

    campaign_filter.short_description = _("Campaign")

    def changelist_view(self, request, extra_context=None):
        title = _("Sent events")
        campaign, subscriber = (None, None)

        if request.GET.get("campaign_id__exact") is not None:
            campaign = Campaign.objects.filter(
                id=request.GET.get("campaign_id__exact")
            ).first()
        if request.GET.get("subscriber_id__exact") is not None:
            subscriber = (
                subscriber_class()
                .objects.filter(id=request.GET.get("subscriber_id__exact"))
                .first()
            )

        if campaign and subscriber:
            title = _(
                f"Sent event for campaign %(campaign)s and subscriber %(subscriber)s"
            ) % {"campaign": str(campaign), "subscriber": str(subscriber)}
        elif campaign:
            title = mark_safe(
                _("Sent events for campaign %s")
                % (
                    format_html(
                        '<a href="{}">{}</a>',
                        reverse("admin:nuntius_campaign_change", args=[campaign.pk]),
                        str(campaign),
                    ),
                )
            )
        elif subscriber:
            title = _("Sent events for subscriber %s") % (str(subscriber),)

        return super().changelist_view(request, extra_context={"title": title})
