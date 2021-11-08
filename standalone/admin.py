from django.contrib import admin
from django.contrib.admin import AdminSite
from push_notifications.admin import DeviceAdmin
from push_notifications.models import GCMDevice, WNSDevice, APNSDevice

from nuntius.admin import (
    CampaignAdmin,
    CampaignSentEventAdmin,
    PushCampaignAdmin,
    PushCampaignSentEventAdmin,
)
from nuntius.app_settings import CAMPAIGN_TYPE_EMAIL, CAMPAIGN_TYPE_PUSH
from nuntius.models import (
    Campaign,
    CampaignSentEvent,
    PushCampaign,
    PushCampaignSentEvent,
)
from standalone import settings
from standalone.models import Subscriber, Segment


class NuntiusAdminSite(AdminSite):
    site_header = "Standalone Nuntius"


admin_site = NuntiusAdminSite(name="nuntius_admin")


class SubscriberAdmin(admin.ModelAdmin):
    list_display = ("email", "subscriber_status")


class SegmentAdmin(admin.ModelAdmin):
    search_fields = ("name",)


admin_site.register(Subscriber, SubscriberAdmin)
admin_site.register(Segment, SegmentAdmin)

if CAMPAIGN_TYPE_EMAIL in settings.NUNTIUS_ENABLED_CAMPAIGN_TYPES:
    admin_site.register(Campaign, CampaignAdmin)
    admin_site.register(CampaignSentEvent, CampaignSentEventAdmin)

if CAMPAIGN_TYPE_PUSH in settings.NUNTIUS_ENABLED_CAMPAIGN_TYPES:
    admin_site.register(PushCampaign, PushCampaignAdmin)
    admin_site.register(PushCampaignSentEvent, PushCampaignSentEventAdmin)

    admin_site.register(APNSDevice, DeviceAdmin)
    admin_site.register(GCMDevice, DeviceAdmin)
