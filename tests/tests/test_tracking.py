import base64
import json
from urllib.parse import quote as url_quote

from django.core import mail
from django.test import TestCase
from django.urls import reverse

from nuntius.models import (
    Campaign,
    CampaignSentEvent,
    CampaignSentStatusType,
    BaseSubscriber,
)
from nuntius._tasks import send_campaign
from nuntius.utils import sign_url
from tests.models import TestSubscriber


EXTERNAL_LINK = "http://otherexample.com"
ESP_MESSAGE_ID = "testmessageid"
HTML_MESSAGE = '<body><a href="' + EXTERNAL_LINK + '">Link</a></body>'


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

    def test_subscriber_bounce(self):
        response = self.post_webhook()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            TestSubscriber.objects.get(email="a@example.com").subscriber_status,
            BaseSubscriber.STATUS_BOUNCED,
        )

    def test_bounce_tracking_on_campaign(self):
        campaign = Campaign.objects.create()
        send_campaign(campaign.pk, "http://example.com")

        c = CampaignSentEvent.objects.get(email="a@example.com")
        c.esp_message_id = ESP_MESSAGE_ID
        c.save()

        self.assertEqual(c.result, CampaignSentStatusType.UNKNOWN)

        self.post_webhook()
        c.refresh_from_db()
        self.assertEqual(c.result, CampaignSentStatusType.BOUNCED)


class TrackingTestCase(TestCase):
    fixtures = ["subscribers.json"]

    def test_open_tracking(self):
        campaign = Campaign.objects.create(
            message_content_html=HTML_MESSAGE, message_content_text="Test"
        )
        send_campaign(campaign.pk, "http://example.com")

        tracking_id = CampaignSentEvent.objects.get(email="a@example.com").tracking_id
        tracking_url = reverse(
            "nuntius_track_open", kwargs={"tracking_id": tracking_id}
        )

        self.assertIn(
            '<img src="http://example.com{}" width="1" height="1" alt="nt">'.format(
                tracking_url
            ),
            str(mail.outbox[0].message()),
        )

        for i in range(2):
            self.client.get(tracking_url)

        self.assertEqual(
            2,
            CampaignSentEvent.objects.get(email="a@example.com").open_count,
            campaign.get_open_count(),
        )
        self.assertEqual(1, campaign.get_unique_open_count())

    def test_link_tracking(self):
        campaign = Campaign.objects.create(
            message_content_html=HTML_MESSAGE, message_content_text="Test"
        )
        send_campaign(campaign.pk, "http://example.com")

        tracking_id = CampaignSentEvent.objects.get(email="a@example.com").tracking_id
        tracking_url = reverse(
            "nuntius_track_click",
            kwargs={
                "tracking_id": tracking_id,
                "signature": sign_url(campaign, EXTERNAL_LINK),
                "link": url_quote(EXTERNAL_LINK, safe=""),
            },
        )

        self.assertIn(
            '<a href="http://example.com{}">Link</a>'.format(tracking_url),
            str(mail.outbox[0].message()),
        )

        for i in range(2):
            res = self.client.get(tracking_url)

        self.assertRedirects(res, EXTERNAL_LINK, fetch_redirect_response=False)
        self.assertEqual(
            2,
            CampaignSentEvent.objects.get(email="a@example.com").click_count,
            campaign.get_click_count(),
        )
