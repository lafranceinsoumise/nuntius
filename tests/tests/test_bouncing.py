from datetime import timedelta
from unittest import mock

from django.test import TestCase
from django.urls import reverse
from django.utils.timezone import now

from nuntius.models import AbstractSubscriber, CampaignSentEvent, CampaignSentStatusType
from tests.models import TestSubscriber
from tests.tests.test_tracking import TrackingMixin

ESP_MESSAGE_ID = "testmessageid"


def eight_days_generator():
    date = now()
    while True:
        yield date
        date = date + timedelta(days=8)


eight_days_iterator = eight_days_generator()


def mock_now_plus_8_days():
    return next(eight_days_iterator)


class BouncingTestCase(TrackingMixin, TestCase):
    fixtures = ["subscribers.json"]

    def test_first_send_is_bounce_then_bounce(self):
        self.post_webhook(
            reverse("anymail:sendgrid_tracking_webhook"), self.sendgrid_payload()
        )
        self.assertEqual(
            TestSubscriber.objects.get(email="a@example.com").get_subscriber_status(),
            AbstractSubscriber.STATUS_BOUNCED,
        )

    def test_second_send_is_bounce_after_success_then_not_bounce(self):
        CampaignSentEvent.objects.create(
            email="a@example.com", result=CampaignSentStatusType.OK
        )
        self.post_webhook(
            reverse("anymail:sendgrid_tracking_webhook"), self.sendgrid_payload()
        )
        self.assertEqual(
            TestSubscriber.objects.get(email="a@example.com").get_subscriber_status(),
            AbstractSubscriber.STATUS_SUBSCRIBED,
        )

    def test_four_bounces_in_short_period_is_bounce(self):
        CampaignSentEvent.objects.create(
            email="a@example.com", result=CampaignSentStatusType.OK
        )

        for i in range(0, 3):
            self.post_webhook(
                reverse("anymail:sendgrid_tracking_webhook"),
                self.sendgrid_payload(esp_message_id=ESP_MESSAGE_ID + str(i)),
            )
        self.assertEqual(
            TestSubscriber.objects.get(email="a@example.com").get_subscriber_status(),
            AbstractSubscriber.STATUS_SUBSCRIBED,
        )

        self.post_webhook(
            reverse("anymail:sendgrid_tracking_webhook"),
            self.sendgrid_payload(esp_message_id=ESP_MESSAGE_ID + "onemore"),
        )
        self.assertEqual(
            TestSubscriber.objects.get(email="a@example.com").get_subscriber_status(),
            AbstractSubscriber.STATUS_BOUNCED,
        )

    @mock.patch("django.utils.timezone.now", mock_now_plus_8_days)
    @mock.patch("nuntius.actions.now", mock_now_plus_8_days)
    def test_consecutive_bounces_on_long_period(self):
        CampaignSentEvent.objects.create(
            email="a@example.com", result=CampaignSentStatusType.OK
        )
        self.post_webhook(
            reverse("anymail:sendgrid_tracking_webhook"),
            self.sendgrid_payload(esp_message_id=ESP_MESSAGE_ID + "first week"),
        )
        self.assertEqual(
            TestSubscriber.objects.get(email="a@example.com").get_subscriber_status(),
            AbstractSubscriber.STATUS_SUBSCRIBED,
        )
        self.post_webhook(
            reverse("anymail:sendgrid_tracking_webhook"),
            self.sendgrid_payload(esp_message_id=ESP_MESSAGE_ID + "one week later"),
        )
        self.assertEqual(
            TestSubscriber.objects.get(email="a@example.com").get_subscriber_status(),
            AbstractSubscriber.STATUS_BOUNCED,
        )
