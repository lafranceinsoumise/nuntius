from django.contrib import admin
from django.shortcuts import redirect
from django.urls import reverse, path
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from django.utils.translation import gettext as _

from nuntius import app_settings
from nuntius.admin.panels import subscriber_class
from nuntius.models import Campaign
from nuntius.models.push_campaigns import PushCampaign, PushCampaignSentEvent


class PushCampaignAdmin(admin.ModelAdmin):
    search_fields = ("name", "notification_title")
    autocomplete_fields = ("segment",)
    prepopulated_fields = {"utm_name": ("name",)}
    fieldsets = (
        (None, {"fields": ("created", "updated", "name", "utm_name")}),
        (
            _("Notification"),
            {
                "fields": (
                    "notification_title",
                    "notification_url",
                    "notification_body",
                    "notification_tag",
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
            {"fields": ("sent_to", "sent_ok", "sent_ko", "click_count")},
        ),
    )
    list_display = (
        "name",
        "notification_title",
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
        "sent_to",
        "sent_ok",
        "sent_ko",
        "click_count",
    )
    save_as = True

    def segment_subscribers(self, instance):
        if instance.segment is None:
            return subscriber_class().objects.count()
        return instance.segment.get_subscribers_count()

    segment_subscribers.short_description = _("Subscribers")

    def sent_to(self, instance):
        return format_html(
            '<a href="{}">{}</a>',
            reverse("admin:nuntius_pushcampaignsentevent_changelist")
            + "?campaign_id__exact="
            + str(instance.pk),
            str(instance.get_sent_count()),
        )

    sent_to.short_description = _("Sent to")

    def sent_ok(self, instance):
        return instance.get_ok_count()

    sent_ok.short_description = _("OK")

    def sent_ko(self, instance):
        return instance.get_ko_count()

    sent_ko.short_description = _("KO")

    def click_count(self, instance):
        return instance.get_click_count()

    click_count.short_description = _("Click count")

    def send_button(self, instance):
        if instance.pk is None:
            return mark_safe("-")
        if instance.status == Campaign.STATUS_SENDING:
            return format_html(
                '<a href="{}" class="button">' + _("Pause") + "</a>",
                reverse("admin:nuntius_pushcampaign_pause", args=[instance.pk]),
            )
        return format_html(
            '<a href="{}" class="button">' + _("Send") + "</a>",
            reverse("admin:nuntius_pushcampaign_send", args=[instance.pk]),
        )

    send_button.short_description = _("Send")

    def get_urls(self):
        return [
            path(
                "<pk>/send/",
                self.admin_site.admin_view(self.send_view),
                name="nuntius_pushcampaign_send",
            ),
            path(
                "<pk>/pause/",
                self.admin_site.admin_view(self.pause_view),
                name="nuntius_pushcampaign_pause",
            ),
        ] + super().get_urls()

    def send_view(self, request, pk):
        campaign = PushCampaign.objects.get(pk=pk)
        campaign.status = PushCampaign.STATUS_SENDING
        campaign.save(update_fields=["status"])

        return redirect(reverse("admin:nuntius_pushcampaign_change", args=[pk]))

    def pause_view(self, request, pk):
        campaign = PushCampaign.objects.get(pk=pk)

        campaign.status = PushCampaign.STATUS_WAITING
        campaign.save(update_fields=["status"])

        return redirect(reverse("admin:nuntius_pushcampaign_change", args=[pk]))


class TrackingFilter(admin.SimpleListFilter):
    title = _("Clicked")
    parameter_name = "clicked"

    def lookups(self, request, model_admin):
        return (("1", _("Yes")), ("0", _("No")))

    def queryset(self, request, queryset):
        if self.value() == "1":
            return queryset.exclude(click_count=0)
        if self.value() == "0":
            return queryset.filter(click_count=0)
        return queryset


class PushCampaignSentEventAdmin(admin.ModelAdmin):
    def has_change_permission(self, *args, **kwargs):
        return False

    def has_add_permission(self, *args, **kwargs):
        return False

    actions = None
    readonly_fields = ("subscriber_filter", "campaign_filter")
    list_filter = ("result", TrackingFilter)
    list_display_links = None

    def get_list_display(self, request):
        list_display = ("datetime", "result", "click_count")

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
            reverse("admin:nuntius_pushcampaignsentevent_changelist")
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
            reverse("admin:nuntius_pushcampaignsentevent_changelist")
            + "?campaign_id__exact="
            + str(instance.campaign_id),
            str(instance.campaign),
        )

    campaign_filter.short_description = _("Campaign")

    def changelist_view(self, request, extra_context=None):
        title = _("Sent events")
        campaign, subscriber = (None, None)

        if request.GET.get("campaign_id__exact") is not None:
            campaign = PushCampaign.objects.filter(
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
                        reverse(
                            "admin:nuntius_pushcampaign_change", args=[campaign.pk]
                        ),
                        str(campaign),
                    ),
                )
            )
        elif subscriber:
            title = _("Sent events for subscriber %s") % (str(subscriber),)

        return super().changelist_view(request, extra_context={"title": title})


if not app_settings.DISABLE_DEFAULT_ADMIN:
    admin.site.register(PushCampaign, PushCampaignAdmin)
    admin.site.register(PushCampaignSentEvent, PushCampaignSentEventAdmin)
