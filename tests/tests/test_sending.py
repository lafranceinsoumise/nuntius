from django.core import mail
from django.test import TestCase

from nuntius.models import Campaign, BaseSubscriber
from nuntius.tasks import send_campaign
from tests.models import TestSegment, TestSubscriber


class SendingTestCase(TestCase):
    fixtures = ['subscribers.json']

    def test_segments(self):
        self.assertEqual(TestSegment.objects.get(id="subscribed").get_subscribers_queryset().count(), 2)

    def test_send_campaign(self):
        segment = TestSegment.objects.get(id="subscribed")
        campaign = Campaign.objects.create(segment=segment)
        send_campaign(campaign.pk)

        self.assertEqual(segment.get_subscribers_queryset().count(), len(mail.outbox), campaign.get_sent_count())

    def test_send_campaign_without_segment(self):
        campaign = Campaign.objects.create()
        send_campaign(campaign.pk)

        self.assertEqual(TestSubscriber.objects.filter(subscriber_status=BaseSubscriber.STATUS_SUBSCRIBED).count(),
                         len(mail.outbox), campaign.get_sent_count())

    def test_send_only_to_subscribed(self):
        segment = TestSegment.objects.get(id="all_status")
        campaign = Campaign.objects.create(segment=segment)
        send_campaign(campaign.pk)

        self.assertEqual(
            segment.get_subscribers_queryset().filter(subscriber_status=BaseSubscriber.STATUS_SUBSCRIBED).count(),
            len(mail.outbox),
            campaign.get_sent_count()
        )

    def test_send_only_once(self):
        segment = TestSegment.objects.get(id="subscribed")
        campaign = Campaign.objects.create(segment=segment, message_content_text='test [email] test')
        send_campaign(campaign.pk)
        send_campaign(campaign.pk)

        self.assertEqual(segment.get_subscribers_queryset().count(), len(mail.outbox), campaign.get_sent_count())
        self.assertIn(f'test {segment.get_subscribers_queryset().first().email} test', str(mail.outbox[0].message()))



