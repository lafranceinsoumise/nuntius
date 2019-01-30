import base64
import json

from django.test import TestCase
from django.urls import reverse

from nuntius.models import BaseSubscriber
from tests.models import TestSubscriber


class BounceTestCase(TestCase):
    fixtures = ["subscribers.json"]
    sendgrid_payload = [{"email": "a@example.com", "event": "bounce"}]

    def test_bounce_basic_model(self):
        TestSubscriber.objects.set_subscriber_status(
            "a@example.com", BaseSubscriber.STATUS_BOUNCED
        )
        subscriber = TestSubscriber.objects.get(email="a@example.com")

        self.assertEqual(subscriber.subscriber_status, BaseSubscriber.STATUS_BOUNCED)

    def test_anymail_bounce(self):
        response = self.client.post(
            reverse("anymail:sendgrid_tracking_webhook"),
            json.dumps(self.sendgrid_payload),
            content_type="application/json",
            HTTP_AUTHORIZATION="Basic "
            + (base64.b64encode(b"test:test").decode("utf-8")),
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            TestSubscriber.objects.get(email="a@example.com").subscriber_status,
            BaseSubscriber.STATUS_BOUNCED,
        )
