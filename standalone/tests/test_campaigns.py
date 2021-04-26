from django.test import TestCase

from nuntius.models import Campaign
from standalone.models import Segment


class CampaignTestCase(TestCase):
    def test_can_attach_segment(self):
        segment = Segment.objects.create()
        campaign = Campaign.objects.create(name="Test campaign", segment=segment)

        campaign.refresh_from_db()
        self.assertEqual(campaign.segment, segment)
