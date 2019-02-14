import json
import os

from django.conf import settings
from django.contrib import admin
from django import forms
from django.contrib.contenttypes.models import ContentType
from django.http import HttpResponseBadRequest, HttpResponse, JsonResponse
from django.shortcuts import redirect
from django.template.response import TemplateResponse
from django.urls import reverse, path
from django.utils.html import format_html, format_html_join
from django.utils.safestring import mark_safe
from django.utils.translation import gettext as _
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.generic import CreateView

from nuntius.admin.fields import GenericModelChoiceField
from nuntius.celery import nuntius_celery_app
from nuntius.models import segment_cts, Campaign, MosaicoImage
from nuntius._tasks import send_campaign


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
            "url": self.request.build_absolute_uri(image.file.url),
            "deleteUrl": self.request.build_absolute_uri(image.file.url),
            "deleteType": "DELETE",
            "thumbnailUrl": self.request.build_absolute_uri(image.file.thumbnail.url),
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
                    "name",
                    "message_from_name",
                    "message_from_email",
                    "message_reply_to_name",
                    "message_reply_to_email",
                    "message_subject",
                )
            },
        ),
        (_("Content"), {"fields": ("mosaico_buttons", "message_content_text")}),
        (
            _("Sending"),
            {
                "fields": (
                    "segment",
                    "segment_subscribers",
                    "status",
                    "send_button",
                    "sent_to",
                    "sent_ok",
                    "sent_bounced",
                    "sent_complained",
                    "sent_blocked",
                    "task_uuid",
                    "task_state",
                )
            },
        ),
    )
    list_display = (
        "name",
        "message_subject",
        "segment",
        "segment_subscribers",
        "status",
        "send_button",
        "sent_to",
    )
    list_filter = ("status",)
    form = CampaignAdminForm
    readonly_fields = (
        "segment_subscribers",
        "status",
        "send_button",
        "mosaico_buttons",
        "message_content_text",
        "sent_to",
        "sent_ok",
        "sent_bounced",
        "sent_complained",
        "sent_blocked",
        "task_uuid",
        "task_state",
    )

    def get_object(self, request, object_id, from_field=None):
        object = super().get_object(request, object_id, from_field=from_field)
        object.get_task_and_update_status()

        return object

    def segment_subscribers(self, instance):
        if instance.segment is None:
            model = settings.NUNTIUS_SUBSCRIBER_MODEL
            model_class = ContentType.objects.get(
                app_label=model.split(".")[0], model=model.split(".")[1].lower()
            ).model_class()
            return model_class.objects.count()
        return instance.segment.get_subscribers_count()

    segment_subscribers.short_description = _("Subscribers")

    def sent_to(self, instance):
        return instance.get_sent_count()

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

    def task_state(self, instance):
        task = instance.get_task_and_update_status()
        if task is not None:
            return task[0]
        if instance.task_uuid is None:
            return "-"

        return _("Connection to celery failed")

    task_state.short_description = _("Send task state")

    def send_button(self, instance):
        if instance.pk is None:
            return mark_safe("-")
        if instance.status == Campaign.STATUS_SENDING:
            return format_html(
                '<a href="{}" class="button">' + _("Pause") + "</a>",
                reverse("admin:nuntius_campaign_pause", args=[instance.pk]),
            )

        return format_html(
            '<a href="{}" class="button">' + _("Send") + "</a>",
            reverse("admin:nuntius_campaign_send", args=[instance.pk]),
        )

    send_button.short_description = _("Send")

    def mosaico_buttons(self, instance):
        if instance.pk is None:
            return mark_safe("-")

        if not instance.message_mosaico_data:
            default_template = (
                settings.STATIC_URL
                + "/nuntius/mosaico/templates/versafix-1/template-versafix-1.html",
                _("Default template"),
            )
            templates = getattr(
                settings, "NUNTIUS_MOSAICO_TEMPLATES", [default_template]
            )

            return format_html(
                "<p>" + _("Create content from template:") + "</p><br>"
            ) + format_html_join(
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
            '<a href="{}" class="button">' + _("Preview result") + "</a>",
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
        if campaign.get_task_and_update_status() is not None:
            return redirect(reverse("admin:nuntius_campaign_change", args=[pk]))

        r = send_campaign.delay(pk)
        campaign.task_uuid = r.id
        campaign.save()

        return redirect(reverse("admin:nuntius_campaign_change", args=[pk]))

    def pause_view(self, request, pk):
        campaign = Campaign.objects.get(pk=pk)
        if campaign.get_task_and_update_status() is None:
            return redirect(reverse("admin:nuntius_campaign_change", args=[pk]))

        nuntius_celery_app.control.revoke(str(campaign.task_uuid), terminate=True)

        return redirect(reverse("admin:nuntius_campaign_change", args=[pk]))

    def mosaico_view(self, request, pk):
        return TemplateResponse(
            request=request,
            template="nuntius/editor.html",
            context={
                "image_processor_backend_url": request.build_absolute_uri(
                    reverse("nuntius_mosaico_image_processor")
                )
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
