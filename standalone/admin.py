from django.contrib import admin
from django.contrib.admin import AdminSite

from nuntius.admin import CampaignAdmin, CampaignSentEventAdmin
from nuntius.models import Campaign, CampaignSentEvent
from standalone.models import Subscriber, Segment


class NuntiusAdminSite(AdminSite):
    site_header = "Nuntius"


admin_site = NuntiusAdminSite(name="nuntius_admin")


class SubscriberAdmin(admin.ModelAdmin):
    list_display = ("email", "subscriber_status")


class SegmentAdmin(admin.ModelAdmin):
    search_fields = ("name",)


admin_site.register(Subscriber, SubscriberAdmin)
admin_site.register(Segment, SegmentAdmin)
admin_site.register(Campaign, CampaignAdmin)
admin_site.register(CampaignSentEvent, CampaignSentEventAdmin)
