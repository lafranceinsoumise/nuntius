from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from nuntius.models import Campaign, PushCampaign
from standalone.models import Segment


class CampaignTestCase(TestCase):
    def test_can_attach_segment(self):
        segment = Segment.objects.create()
        campaign = Campaign.objects.create(name="Test campaign", segment=segment)

        campaign.refresh_from_db()
        self.assertEqual(campaign.segment, segment)

    def test_campaign_outbox_queryset(self):
        now = timezone.now()

        sent_campaign = Campaign.objects.create(
            name="Sent", status=Campaign.STATUS_SENT
        )
        past_campaign = Campaign.objects.create(
            name="Past",
            end_date=now - timedelta(days=1),
            status=Campaign.STATUS_WAITING,
        )
        future_campaign = Campaign.objects.create(
            name="Future",
            start_date=now + timedelta(days=1),
            status=Campaign.STATUS_WAITING,
        )
        present_campaign = Campaign.objects.create(
            name="Present",
            start_date=now - timedelta(days=1),
            end_date=now + timedelta(days=1),
            status=Campaign.STATUS_WAITING,
        )
        eternal_campaign = Campaign.objects.create(
            name="Eternal", status=Campaign.STATUS_WAITING
        )

        outbox = Campaign.objects.outbox()

        self.assertIn(present_campaign, outbox)
        self.assertIn(eternal_campaign, outbox)

        self.assertNotIn(sent_campaign, outbox)
        self.assertNotIn(past_campaign, outbox)
        self.assertNotIn(future_campaign, outbox)


class PushCampaignTestCase(TestCase):
    def test_can_attach_segment(self):
        segment = Segment.objects.create()
        campaign = PushCampaign.objects.create(
            name="Test push campaign", segment=segment
        )

        campaign.refresh_from_db()
        self.assertEqual(campaign.segment, segment)

    def test_campaign_outbox_queryset(self):
        now = timezone.now()

        sent_campaign = PushCampaign.objects.create(
            name="Sent", status=PushCampaign.STATUS_SENT
        )
        past_campaign = PushCampaign.objects.create(
            name="Past",
            end_date=now - timedelta(days=1),
            status=PushCampaign.STATUS_WAITING,
        )
        future_campaign = PushCampaign.objects.create(
            name="Future",
            start_date=now + timedelta(days=1),
            status=PushCampaign.STATUS_WAITING,
        )
        present_campaign = PushCampaign.objects.create(
            name="Present",
            start_date=now - timedelta(days=1),
            end_date=now + timedelta(days=1),
            status=PushCampaign.STATUS_WAITING,
        )
        eternal_campaign = PushCampaign.objects.create(
            name="Eternal", status=PushCampaign.STATUS_WAITING
        )

        outbox = PushCampaign.objects.outbox()

        self.assertIn(present_campaign, outbox)
        self.assertIn(eternal_campaign, outbox)

        self.assertNotIn(sent_campaign, outbox)
        self.assertNotIn(past_campaign, outbox)
        self.assertNotIn(future_campaign, outbox)
