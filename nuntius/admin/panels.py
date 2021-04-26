import json

from django.contrib import admin
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

from nuntius import app_settings
from nuntius.models import Campaign, MosaicoImage, CampaignSentEvent
from nuntius.utils.messages import build_image_absolute_uri


def subscriber_class():
    model = app_settings.NUNTIUS_SUBSCRIBER_MODEL
    return ContentType.objects.get(
        app_label=model.split(".")[0], model=model.split(".")[1].lower()
    ).model_class()


class MosaicoImageUploadView(CreateView):
    model = MosaicoImage
    fields = ("file",)

    def image_dict(self, image):
        return {
            "name": image.file.name,
            "size": image.file.size,
            "url": build_image_absolute_uri(self.request, image.file.url),
            "deleteUrl": build_image_absolute_uri(self.request, image.file.url),
            "deleteType": "DELETE",
            "thumbnailUrl": build_image_absolute_uri(
                self.request, image.file.thumbnail.url
            ),
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


class CampaignAdmin(admin.ModelAdmin):
    search_fields = ("name", "message_subject")
    autocomplete_fields = ("segment",)
    prepopulated_fields = {"utm_name": ("name",)}
    fieldsets = (
        (
            None,
            {
                "fields": (
                    "created",
                    "updated",
                    "name",
                    "utm_name",
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
    )
    save_as = True

    def get_changeform_initial_data(self, request):
        return {
            "message_from_name": app_settings.DEFAULT_FROM_NAME,
            "message_from_email": app_settings.DEFAULT_FROM_EMAIL,
            "message_reply_to_name": app_settings.DEFAULT_REPLY_TO_NAME,
            "message_reply_to_email": app_settings.DEFAULT_REPLY_TO_EMAIL,
        }

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
        "Available variables (example values from first subscriber)"
    )

    def mosaico_buttons(self, instance):
        if instance.pk is None:
            return mark_safe("-")

        if not instance.message_mosaico_data:
            templates = app_settings.MOSAICO_TEMPLATES

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
            '<a href="{}" class="button">' + _("Open the editor") + "</a> "
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

        campaign.status = Campaign.STATUS_SENDING
        campaign.save(update_fields=["status"])

        return redirect(reverse("admin:nuntius_campaign_change", args=[pk]))

    def pause_view(self, request, pk):
        campaign = Campaign.objects.get(pk=pk)

        campaign.status = Campaign.STATUS_WAITING
        campaign.save(update_fields=["status"])

        return redirect(reverse("admin:nuntius_campaign_change", args=[pk]))

    def mosaico_view(self, request, pk):
        return TemplateResponse(
            request=request,
            template="nuntius/editor.html",
            context={
                "image_processor_backend_url": build_image_absolute_uri(
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


class TrackingFilter(admin.SimpleListFilter):
    title = _("Tracking")
    parameter_name = "tracking"

    def lookups(self, request, model_admin):
        return ("O", _("Opened")), ("C", _("Clicked"))

    def queryset(self, request, queryset):
        if self.value() == "O":
            return queryset.exclude(open_count=0)
        if self.value() == "C":
            return queryset.exclude(click_count=0)


class CampaignSentEventAdmin(admin.ModelAdmin):
    def has_change_permission(self, *args, **kwargs):
        return False

    def has_add_permission(self, *args, **kwargs):
        return False

    actions = None
    readonly_fields = ("subscriber_filter", "campaign_filter")
    list_filter = ("result", TrackingFilter)
    list_display_links = None

    def get_list_display(self, request):
        list_display = ("email", "datetime", "result", "open_count", "click_count")
        if request.GET.get("campaign_id__exact") is None:
            list_display = ("campaign_filter", *list_display)
        if request.GET.get("subscriber_id__exact") is None:
            list_display = ("subscriber_filter", *list_display)

        return list_display

    def subscriber_filter(self, instance):
        if instance.subscriber is None:
            return "-"

        return format_html(
            '<a href="{}">{}</a>',
            reverse("admin:nuntius_campaignsentevent_changelist")
            + "?subscriber_id__exact="
            + str(instance.subscriber_id),
            str(instance.subscriber),
        )

    subscriber_filter.short_description = _("Subscriber")

    def campaign_filter(self, instance):
        if instance.campaign is None:
            return "-"

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


if not app_settings.DISABLE_DEFAULT_ADMIN:
    admin.site.register(Campaign, CampaignAdmin)
    admin.site.register(CampaignSentEvent, CampaignSentEventAdmin)
