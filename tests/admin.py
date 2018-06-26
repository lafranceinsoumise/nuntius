from django.contrib import admin

from tests.models import TestSubscriber, TestSegment


@admin.register(TestSubscriber)
class TestSubscriberAdmin(admin.ModelAdmin):
    list_display = ('email', 'subscriber_status')
    pass


@admin.register(TestSegment)
class TestSegmentAdmin(admin.ModelAdmin):
    pass
