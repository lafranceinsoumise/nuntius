from django.test import TestCase

from nuntius.models import Campaign
from tests.models import TestSegment


class CampaignTestCase(TestCase):
    def test_can_attach_segment(self):
        segment = TestSegment.objects.create()
        campaign = Campaign.objects.create(name="Test campaign", segment=segment)

        campaign.refresh_from_db()
        self.assertEqual(campaign.segment, segment)
