from django.contrib import admin
from django import forms
from django.shortcuts import redirect
from django.urls import reverse, path
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from django.utils.translation import gettext as _

from mailer.admin.fields import GenericModelChoiceField
from mailer.celery import mailer_celery_app
from mailer.models import segment_cts, Campaign
from mailer.tasks import send_campaign


class CampaignAdminForm(forms.ModelForm):
    segment = GenericModelChoiceField(querysets=lambda: [ct.model_class().objects.all() for ct in set(segment_cts())])

    def clean(self):
        cleaned_data = super().clean()
        segment = cleaned_data.get('segment')

        if segment:
            self.instance.segment = segment

        return cleaned_data

    class Meta:
        exclude = ('segment_content_type', 'segment_id')


@admin.register(Campaign)
class CampaignAdmin(admin.ModelAdmin):
    list_display = ('name', 'message_subject', 'segment', 'segment_subscribers', 'status', 'send_button', 'sent_to')
    list_filter = ('status',)
    form = CampaignAdminForm
    readonly_fields = ('segment_subscribers', 'status', 'send_button', 'sent_to', 'sent_ok', 'sent_bounced',
                       'sent_complained', 'sent_blocked', 'task_uuid', 'task_state')

    def get_object(self, request, object_id, from_field=None):
        object = super().get_object(request, object_id, from_field=from_field)
        object.get_task_and_update_status()

        return object

    def segment_subscribers(self, instance):
        return instance.segment.get_subscriber_count()
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
        return '-'
    task_state.short_description = _("Send task state")

    def send_button(self, instance):
        if instance.pk is None:
            return mark_safe('-')
        if instance.status == Campaign.STATUS_SENDING:
            return format_html(
                '<a href="{}" class="button">' + _("Pause") + '</a>',
                reverse('admin:mailer_campaign_pause', args=[instance.pk])
            )

        return format_html(
            '<a href="{}" class="button">' + _("Send") + '</a>',
            reverse('admin:mailer_campaign_send', args=[instance.pk])
        )
    send_button.short_description = _("Send")

    def get_urls(self):
        return [
            path('<pk>/send/', self.admin_site.admin_view(self.send_view), name='mailer_campaign_send'),
            path('<pk>/pause/', self.admin_site.admin_view(self.pause_view), name='mailer_campaign_pause')
        ] + super().get_urls()

    def send_view(self, request, pk):
        campaign = Campaign.objects.get(pk=pk)
        if campaign.get_task_and_update_status() is not None:
            return redirect(reverse('admin:mailer_campaign_change', args=[pk]))

        r = send_campaign.delay(pk)
        campaign.task_uuid = r.id
        campaign.save()

        return redirect(reverse('admin:mailer_campaign_change', args=[pk]))

    def pause_view(self, request, pk):
        campaign = Campaign.objects.get(pk=pk)
        if campaign.get_task_and_update_status() is None:
            return redirect(reverse('admin:mailer_campaign_change', args=[pk]))

        mailer_celery_app.control.revoke(str(campaign.task_uuid), terminate=True)

        return redirect(reverse('admin:mailer_campaign_change', args=[pk]))
