import base64
import json

from django.test import TestCase
from django.urls import reverse

from nuntius.models import (
    BaseSubscriber,
    Campaign,
    CampaignSentEvent,
    CampaignSentStatusType,
)
from nuntius.tasks import send_campaign
from tests.models import TestSubscriber


ESP_MESSAGE_ID = "testmessageid"


class BounceTestCase(TestCase):
    fixtures = ["subscribers.json"]
    sendgrid_payload = [
        {"email": "a@example.com", "event": "bounce", "anymail_id": ESP_MESSAGE_ID}
    ]

    def post_webhook(self):
        return self.client.post(
            reverse("anymail:sendgrid_tracking_webhook"),
            json.dumps(self.sendgrid_payload),
            content_type="application/json",
            HTTP_AUTHORIZATION="Basic "
            + (base64.b64encode(b"test:test").decode("utf-8")),
        )

    def test_bounce_basic_model(self):
        TestSubscriber.objects.set_subscriber_status(
            "a@example.com", BaseSubscriber.STATUS_BOUNCED
        )
        subscriber = TestSubscriber.objects.get(email="a@example.com")

        self.assertEqual(subscriber.subscriber_status, BaseSubscriber.STATUS_BOUNCED)

    def test_anymail_bounce(self):
        response = self.post_webhook()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            TestSubscriber.objects.get(email="a@example.com").subscriber_status,
            BaseSubscriber.STATUS_BOUNCED,
        )

    def test_tracking(self):
        campaign = Campaign.objects.create()
        send_campaign(campaign.pk)

        c = CampaignSentEvent.objects.get(email="a@example.com")
        c.esp_message_id = ESP_MESSAGE_ID
        c.save()

        self.assertEqual(c.result, CampaignSentStatusType.UNKNOWN)

        self.post_webhook()
        c.refresh_from_db()
        self.assertEqual(c.result, CampaignSentStatusType.BOUNCED)
