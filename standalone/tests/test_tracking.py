import base64
import json
from unittest.mock import patch
from urllib.parse import quote as url_quote

from django.test import TestCase
from django.urls import reverse

from nuntius.messages import message_for_event
from nuntius.models import (
    Campaign,
    CampaignSentEvent,
    CampaignSentStatusType,
    BaseSubscriber,
    PushCampaign,
    PushCampaignSentEvent,
)
from nuntius.utils.messages import sign_url
from nuntius.utils.notifications import notification_for_event
from standalone.models import Subscriber

EXTERNAL_LINK = "http://otherexample.com"
ESP_MESSAGE_ID = "testmessageid"
HTML_MESSAGE = '<body><a href="' + EXTERNAL_LINK + '">Link</a></body>'
PUBLIC_URL = "http://public.com"
IMAGES_URL = "http://images.com"
LINKS_URL = "http://links.com"


def settings_patcher(klass):
    patchers = [
        patch("nuntius.app_settings.PUBLIC_URL", new=PUBLIC_URL),
        patch("nuntius.app_settings.IMAGES_URL", new=IMAGES_URL),
        patch("nuntius.app_settings.LINKS_URL", new=LINKS_URL),
    ]

    for p in patchers:
        klass = p(klass)

    return klass


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
        Subscriber.objects.set_subscriber_status(
            "a@example.com", BaseSubscriber.STATUS_BOUNCED
        )
        subscriber = Subscriber.objects.get(email="a@example.com")

        self.assertEqual(subscriber.subscriber_status, BaseSubscriber.STATUS_BOUNCED)

    def test_sendgrid_bounce(self):
        self.assertEqual(CampaignSentEvent.objects.count(), 0)
        with self.assertLogs(logger="nuntius.signals", level="INFO"):
            response = self.post_webhook(
                reverse("anymail:sendgrid_tracking_webhook"), self.sendgrid_payload()
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            Subscriber.objects.get(email="a@example.com").subscriber_status,
            BaseSubscriber.STATUS_BOUNCED,
        )
        event = CampaignSentEvent.objects.last()
        self.assertIsNone(event.campaign)
        self.assertEqual(event.email, "a@example.com")
        self.assertEqual(
            event.subscriber, Subscriber.objects.get(email="a@example.com")
        )

    def test_amazon_soft_bounce(self):
        campaign = Campaign.objects.create()
        subscriber = Subscriber.objects.get(email="a@example.com")
        c = campaign.get_event_for_subscriber(subscriber)
        c.result = CampaignSentStatusType.UNKNOWN
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
            Subscriber.objects.get(email="a@example.com").subscriber_status,
            BaseSubscriber.STATUS_SUBSCRIBED,
        )
        c.refresh_from_db()
        self.assertEqual(c.result, CampaignSentStatusType.BLOCKED)

    def test_amazon_hard_bounce(self):
        campaign = Campaign.objects.create()
        subscriber = Subscriber.objects.get(email="a@example.com")
        c = campaign.get_event_for_subscriber(subscriber)
        c.result = CampaignSentStatusType.UNKNOWN
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
            Subscriber.objects.get(email="a@example.com").subscriber_status,
            BaseSubscriber.STATUS_BOUNCED,
        )
        c.refresh_from_db()
        self.assertEqual(c.result, CampaignSentStatusType.BOUNCED)

    def test_bounce_tracking_on_campaign(self):
        campaign = Campaign.objects.create()
        subscriber = Subscriber.objects.get(email="a@example.com")

        c = campaign.get_event_for_subscriber(subscriber)
        c.result = CampaignSentStatusType.UNKNOWN
        c.esp_message_id = ESP_MESSAGE_ID
        c.save()

        self.post_webhook(
            reverse("anymail:sendgrid_tracking_webhook"), self.sendgrid_payload()
        )
        c.refresh_from_db()
        self.assertEqual(c.result, CampaignSentStatusType.BOUNCED)


@settings_patcher
class TrackingTestCase(TestCase):
    fixtures = ["subscribers.json"]
    maxDiff = None

    def test_open_tracking(self):
        campaign = Campaign.objects.create(
            message_content_html=HTML_MESSAGE, message_content_text="Test"
        )
        subscriber = Subscriber.objects.get(email="a@example.com")
        event = campaign.get_event_for_subscriber(subscriber)
        message = message_for_event(event)

        tracking_id = event.tracking_id
        tracking_url = reverse(
            "nuntius_track_open", kwargs={"tracking_id": tracking_id}
        )

        self.assertIn(
            '<img src="{}" width="1" height="1" alt="nt">'.format(
                PUBLIC_URL + tracking_url
            ),
            str(message.message()),
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
        subscriber = Subscriber.objects.get(email="a@example.com")
        event = campaign.get_event_for_subscriber(subscriber)
        message = message_for_event(event)

        tracking_id = event.tracking_id
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
            '<a href="{}">Link</a>'.format(LINKS_URL + tracking_url),
            str(message.message()),
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

    def test_push_click_tracking(self):
        campaign = PushCampaign.objects.create(
            notification_title="Notification",
            notification_url=EXTERNAL_LINK,
            notification_body="Hey, something happened!",
            utm_name="tracked_campaign",
        )
        subscriber = Subscriber.objects.get(email="a@example.com")
        event = campaign.get_event_for_subscriber(subscriber)
        notification = notification_for_event(event)
        tracking_id = event.tracking_id
        encoded_tracking_query = "?utm_term="

        tracking_url = LINKS_URL + reverse(
            "nuntius_track_push_click",
            kwargs={
                "tracking_id": tracking_id,
                "signature": sign_url(campaign, EXTERNAL_LINK + encoded_tracking_query),
                "link": url_quote(EXTERNAL_LINK + encoded_tracking_query, safe=""),
            },
        )

        self.assertEqual(tracking_url, notification["url"])

        for i in range(2):
            res = self.client.get(tracking_url)

        self.assertRedirects(
            res,
            EXTERNAL_LINK
            + "?utm_campaign=tracked_campaign&utm_source=nuntius&utm_medium=push",
            fetch_redirect_response=False,
        )
        self.assertEqual(
            2,
            PushCampaignSentEvent.objects.get(
                subscriber__email="a@example.com"
            ).click_count,
            campaign.get_click_count(),
        )

    def test_complicated_link_tracking(self):
        URL = (
            "https://twitter.com/intent/tweet?original_referer=https%3A%2F%2Fpublish.twitter.com%2F&ref_src=twsrc%5Etf"
            "w%7Ctwcamp%5Ebuttonembed%7Ctwterm%5Eshare%7Ctwgr%5E&text=Mercredi%2015%20mars%20%C3%A0%2019h%2C%20%40JLMelenchon%20sera%20en%20meeting%20contre%20la%20%23ReformeDesRetraites%20%C3%A0%20Chevilly-Larue%20avec%20%40KekeRachel%20et%20%40MathildePanot%20%23PourNosRetraites&url=https%3A%2F%2Factionpopulaire.fr%2Fevenements%2F3a167ba7-99fb-4709-876e-60d9994322a4%2F"
        )
