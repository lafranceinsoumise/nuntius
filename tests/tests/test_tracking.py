import base64
import json
from urllib.parse import quote as url_quote

from django.core import mail
from django.test import TestCase
from django.urls import reverse

from nuntius._tasks import send_campaign
from nuntius.models import (
    Campaign,
    CampaignSentEvent,
    CampaignSentStatusType,
    BaseSubscriber,
)
from nuntius.utils import sign_url
from tests.models import TestSubscriber

EXTERNAL_LINK = "http://otherexample.com"
ESP_MESSAGE_ID = "testmessageid"
HTML_MESSAGE = '<body><a href="' + EXTERNAL_LINK + '">Link</a></body>'


class TrackingMixin:
    def sendgrid_payload(self, esp_message_id=ESP_MESSAGE_ID):
        return json.dumps(
            [
                {
                    "email": "a@example.com",
                    "event": "bounce",
                    "anymail_id": esp_message_id,
                }
            ]
        )

    amazon_soft_bounce_payload = {
        "Type": "Notification",
        "MessageId": ESP_MESSAGE_ID,
        "Message": json.dumps(
            {
                "notificationType": "Bounce",
                "bounce": {
                    "bounceType": "Transient",
                    "bounceSubType": "ContentRejected",
                    "bouncedRecipients": [
                        {
                            "emailAddress": "a@example.com",
                            "action": "failed",
                            "status": "5.3.0",
                            "diagnosticCode": "smtp; 550 spam detected",
                        }
                    ],
                    "timestamp": "2019-06-05T14:56:13.363Z",
                    "feedbackId": "...",
                    "remoteMtaIp": "x.x.x.x",
                    "reportingMTA": "dsn; a6-136.smtp-out.eu-west-1.amazonses.com",
                },
                "mail": {
                    "timestamp": "2019-06-05T14:56:13.000Z",
                    "source": "source@example.com",
                    "sourceArn": "arn:aws:ses:eu-west-1:...",
                    "sourceIp": "x.x.x.x",
                    "sendingAccountId": "...",
                    "messageId": ESP_MESSAGE_ID,
                    "destination": ["a@example.com"],
                },
            }
        ),
    }

    amazon_hard_bounce_payload = {
        "Type": "Notification",
        "MessageId": ESP_MESSAGE_ID,
        "Message": json.dumps(
            {
                "notificationType": "Bounce",
                "bounce": {
                    "bounceType": "Permanent",
                    "bounceSubType": "General",
                    "bouncedRecipients": [
                        {
                            "emailAddress": "a@example.com",
                            "action": "failed",
                            "status": "5.1.1",
                            "diagnosticCode": "smtp; 550 5.1.1 user unknown (UserSearch)",
                        }
                    ],
                    "timestamp": "2019-06-04T14:50:05.578Z",
                    "feedbackId": "...",
                    "remoteMtaIp": "x.x.x.x",
                    "reportingMTA": "dsn; a6-77.smtp-out.eu-west-1.amazonses.com",
                },
                "mail": {
                    "timestamp": "2019-06-04T14:50:04.000Z",
                    "source": "source@example.com",
                    "sourceArn": "arn:aws:ses:eu-west-1:...",
                    "sourceIp": "x.x.x.x",
                    "sendingAccountId": "...",
                    "messageId": ESP_MESSAGE_ID,
                    "destination": ["a@example.com"],
                },
            }
        ),
    }

    def post_webhook(self, url, data, **headers):
        return self.client.post(
            url,
            data,
            content_type="application/json",
            HTTP_AUTHORIZATION="Basic "
            + (base64.b64encode(b"test:test").decode("utf-8")),
            **headers
        )


class BounceTestCase(TrackingMixin, TestCase):
    fixtures = ["subscribers.json"]

    def test_bounce_basic_model(self):
        TestSubscriber.objects.set_subscriber_status(
            "a@example.com", BaseSubscriber.STATUS_BOUNCED
        )
        subscriber = TestSubscriber.objects.get(email="a@example.com")

        self.assertEqual(subscriber.subscriber_status, BaseSubscriber.STATUS_BOUNCED)

    def test_sendgrid_bounce(self):
        self.assertEqual(CampaignSentEvent.objects.count(), 0)
        with self.assertLogs(logger="nuntius.signals", level="INFO"):
            response = self.post_webhook(
                reverse("anymail:sendgrid_tracking_webhook"), self.sendgrid_payload()
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            TestSubscriber.objects.get(email="a@example.com").subscriber_status,
            BaseSubscriber.STATUS_BOUNCED,
        )
        event = CampaignSentEvent.objects.last()
        self.assertIsNone(event.campaign)
        self.assertEqual(event.email, "a@example.com")
        self.assertEqual(
            event.subscriber, TestSubscriber.objects.get(email="a@example.com")
        )

    def test_amazon_soft_bounce(self):
        campaign = Campaign.objects.create()
        send_campaign(campaign.pk, "http://example.com")
        c = CampaignSentEvent.objects.get(email="a@example.com")
        c.esp_message_id = ESP_MESSAGE_ID
        c.save()

        with self.assertLogs(logger="nuntius.signals", level="INFO"):
            response = self.post_webhook(
                reverse("anymail:amazon_ses_tracking_webhook"),
                self.amazon_soft_bounce_payload,
                HTTP_X_AMZ_SNS_MESSAGE_ID=ESP_MESSAGE_ID,
                HTTP_X_AMZ_SNS_MESSAGE_TYPE="Notification",
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            TestSubscriber.objects.get(email="a@example.com").subscriber_status,
            BaseSubscriber.STATUS_SUBSCRIBED,
        )
        c.refresh_from_db()
        self.assertEqual(c.result, CampaignSentStatusType.BLOCKED)

    def test_amazon_hard_bounce(self):
        campaign = Campaign.objects.create()
        send_campaign(campaign.pk, "http://example.com")
        c = CampaignSentEvent.objects.get(email="a@example.com")
        c.esp_message_id = ESP_MESSAGE_ID
        c.save()

        response = self.post_webhook(
            reverse("anymail:amazon_ses_tracking_webhook"),
            self.amazon_hard_bounce_payload,
            HTTP_X_AMZ_SNS_MESSAGE_ID=ESP_MESSAGE_ID,
            HTTP_X_AMZ_SNS_MESSAGE_TYPE="Notification",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            TestSubscriber.objects.get(email="a@example.com").subscriber_status,
            BaseSubscriber.STATUS_BOUNCED,
        )
        c.refresh_from_db()
        self.assertEqual(c.result, CampaignSentStatusType.BOUNCED)

    def test_bounce_tracking_on_campaign(self):
        campaign = Campaign.objects.create()
        send_campaign(campaign.pk, "http://example.com")

        c = CampaignSentEvent.objects.get(email="a@example.com")
        c.esp_message_id = ESP_MESSAGE_ID
        c.save()

        self.assertEqual(c.result, CampaignSentStatusType.UNKNOWN)

        self.post_webhook(
            reverse("anymail:sendgrid_tracking_webhook"), self.sendgrid_payload()
        )
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
            message_content_html=HTML_MESSAGE,
            message_content_text="Test",
            utm_name="tracked_campaign",
        )
        send_campaign(campaign.pk, "http://example.com")

        tracking_id = CampaignSentEvent.objects.get(email="a@example.com").tracking_id
        encoded_tracking_query = "?utm_content=link-0&utm_term="
        tracking_url = reverse(
            "nuntius_track_click",
            kwargs={
                "tracking_id": tracking_id,
                "signature": sign_url(campaign, EXTERNAL_LINK + encoded_tracking_query),
                "link": url_quote(EXTERNAL_LINK + encoded_tracking_query, safe=""),
            },
        )

        self.assertIn(
            '<a href="http://example.com{}">Link</a>'.format(tracking_url),
            str(mail.outbox[0].message()),
        )

        for i in range(2):
            res = self.client.get(tracking_url)

        self.assertRedirects(
            res,
            EXTERNAL_LINK
            + "?utm_campaign=tracked_campaign&utm_content=link-0&utm_source=nuntius&utm_medium=email",
            fetch_redirect_response=False,
        )
        self.assertEqual(
            2,
            CampaignSentEvent.objects.get(email="a@example.com").click_count,
            campaign.get_click_count(),
        )
