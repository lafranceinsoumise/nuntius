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
from nuntius.views import subscriber_count_view, count_view


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
                    "start_date",
                    "end_date",
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

    def async_count(self, instance, name):
        if not instance or instance.id is None:
            return "-"

        return mark_safe(
            f"""
            <span id="{name}-count-{instance.id}" 
                  hx-get="{reverse(f"admin:nuntius_campaign_count", args=[instance.id, name])}" 
                  hx-trigger="load"
                  hx-swap="innerHTML">
                  Chargement..
            </span>
        """
        )

    def segment_subscribers(self, instance):
        if not instance or instance.id is None:
            return "-"

        return mark_safe(
            f"""
                <span id="subscribers-count-{instance.id}" 
                      hx-get="{reverse(f"admin:nuntius_campaign_subscribers_count",     args=[instance.id])}" 
                      hx-trigger="load"
                      hx-swap="innerHTML">
                      Chargement..
                </span>
            """
        )

    segment_subscribers.short_description = _("Subscribers")

    def sent_to(self, instance):
        return self.async_count(instance, "sent")

    sent_to.short_description = _("Sent to")

    def sent_ok(self, instance):
        return self.async_count(instance, "ok")

    sent_ok.short_description = _("Ok")

    def sent_bounced(self, instance):
        return self.async_count(instance, "bounced")

    sent_bounced.short_description = _("Bounced")

    def sent_complained(self, instance):
        return self.async_count(instance, "complained")

    sent_complained.short_description = _("Complained")

    def sent_blocked(self, instance):
        return self.async_count(instance, "blocked")

    sent_blocked.short_description = _("Blocked")

    def open_count(self, instance):
        return self.async_count(instance, "open")

    open_count.short_description = _("Open count")

    def unique_open_count(self, instance):
        return self.async_count(instance, "unique_open")

    unique_open_count.short_description = _("Unique open count")

    def click_count(self, instance):
        return self.async_count(instance, "click")

    click_count.short_description = _("Click count")

    def unique_click_count(self, instance):
        return self.async_count(instance, "unique_click")

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
            path(
                "<pk>/nuntius/subscribers/count/",
                subscriber_count_view,
                name="nuntius_campaign_subscribers_count"
            ),
            path(
                f"<pk>/nuntius/<name>/count/",
                count_view,
                name=f"nuntius_campaign_count"
            )
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


from django.utils.functional import cached_property
from django.core.paginator import Paginator, InvalidPage
from django.contrib.admin.views.main import ChangeList
from django.conf import settings

class PaginatorCampaignSentEventAdmin(Paginator):
    @cached_property
    def count(self):
        """
        CampaignSentEventAdmin has a huge amount of data, we limit the count to avoid
        parsing the full database for each request on the list.
        :return:
        """
        distinct = self.object_list.values("datetime").distinct()
        limited_distinct_datetimes = distinct[:2500]
        return limited_distinct_datetimes.count()

DISABLE_FULL_PAGINATION = settings.NUNTIUS_PERFORMANCE["CAMPAIGN_SENT_EVENT_DISABLE_FULL_PAGINATION"]
class CampaignSentEventAdmin(admin.ModelAdmin):
    def has_change_permission(self, *args, **kwargs):
        return False

    def has_add_permission(self, *args, **kwargs):
        return False

    paginator = PaginatorCampaignSentEventAdmin if DISABLE_FULL_PAGINATION else Paginator
    list_per_page = 50
    actions = None
    readonly_fields = ("subscriber_filter", "campaign_filter")
    list_filter = ("result", TrackingFilter)
    list_display_links = None

    def get_changelist(self, request, **kwargs):
        if not DISABLE_FULL_PAGINATION:
            return super().get_changelist(request, **kwargs)

        from django.contrib.admin.options import IncorrectLookupParameters
        class NoDeterministicOrderChangeList(ChangeList):
            def get_results(self, request_results):
                """
                Mainly took from super class, to avoid making two times full count of the table
                More information about this case: https://code.djangoproject.com/ticket/34593
                :param request_results:
                :return:
                """
                paginator = self.model_admin.get_paginator(
                    request_results, self.queryset, self.list_per_page
                )
                # Get the number of objects, with admin filters applied.
                # We directly use the paginator count to avoid counting a second time all the database.
                # even with side effects on filter
                result_count = paginator.count

                if self.model_admin.show_full_result_count:
                    full_result_count = paginator.count
                else:
                    full_result_count = None
                can_show_all = result_count <= self.list_max_show_all
                multi_page = result_count > self.list_per_page

                # Get the list of objects to display on this page.
                if (self.show_all and can_show_all) or not multi_page:
                    result_list = self.queryset._clone()
                else:
                    try:
                        result_list = paginator.page(self.page_num).object_list
                    except InvalidPage:
                        raise IncorrectLookupParameters

                self.result_count = result_count
                self.show_full_result_count = self.model_admin.show_full_result_count
                # Admin actions are shown if there is at least one entry
                # or if entries are not counted because show_full_result_count is disabled
                self.show_admin_actions = not self.show_full_result_count or bool(
                    full_result_count
                )
                self.full_result_count = full_result_count
                self.result_list = result_list
                self.can_show_all = can_show_all
                self.multi_page = multi_page
                self.paginator = paginator

            def _get_deterministic_ordering(self, ordering):
                return ("-datetime",)
        return NoDeterministicOrderChangeList

    def get_list_display(self, request):
        list_display = ("email", "datetime", "result", "open_count", "click_count")

        if request.GET.get("campaign_id__exact") is None:
            list_display = ("campaign_filter", *list_display)
        else:
            list_display = ("campaign", *list_display)

        if request.GET.get("subscriber_id__exact") is None:
            list_display = ("subscriber_filter", *list_display)
        else:
            list_display = ("subscriber", *list_display)

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
