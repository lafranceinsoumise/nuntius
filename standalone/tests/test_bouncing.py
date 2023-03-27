import logging
from datetime import timedelta
from unittest import mock

from django.test import TestCase
from django.urls import reverse
from django.utils.timezone import now

from nuntius.models import AbstractSubscriber, CampaignSentEvent, CampaignSentStatusType
from standalone.models import Subscriber
from standalone.tests.test_tracking import TrackingMixin

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
        with self.assertLogs("nuntius", logging.INFO) as log_results:
            self.post_webhook(
                reverse("anymail:sendgrid_tracking_webhook"), self.sendgrid_payload()
            )
        self.assertEqual(
            log_results.output,
            ["INFO:nuntius.signals:event_type=bounced recipient=a@example.com"],
        )
        self.assertEqual(
            Subscriber.objects.get(email="a@example.com").get_subscriber_status(),
            AbstractSubscriber.STATUS_BOUNCED,
        )

    def test_second_send_is_bounce_after_success_then_not_bounce(self):
        CampaignSentEvent.objects.create(
            email="a@example.com", result=CampaignSentStatusType.OK
        )
        with self.assertLogs("nuntius", logging.INFO) as log_results:
            self.post_webhook(
                reverse("anymail:sendgrid_tracking_webhook"), self.sendgrid_payload()
            )
        self.assertEqual(
            log_results.output,
            ["INFO:nuntius.signals:event_type=bounced recipient=a@example.com"],
        )

        self.assertEqual(
            Subscriber.objects.get(email="a@example.com").get_subscriber_status(),
            AbstractSubscriber.STATUS_SUBSCRIBED,
        )

    def test_four_bounces_in_short_period_is_bounce(self):
        CampaignSentEvent.objects.create(
            email="a@example.com", result=CampaignSentStatusType.OK
        )

        with self.assertLogs("nuntius", logging.INFO) as log_results:
            for i in range(0, 3):
                self.post_webhook(
                    reverse("anymail:sendgrid_tracking_webhook"),
                    self.sendgrid_payload(esp_message_id=ESP_MESSAGE_ID + str(i)),
                )
        self.assertEqual(
            log_results.output,
            [
                "INFO:nuntius.signals:event_type=bounced recipient=a@example.com",
                "INFO:nuntius.signals:event_type=bounced recipient=a@example.com",
                "INFO:nuntius.signals:event_type=bounced recipient=a@example.com",
            ],
        )

        self.assertEqual(
            Subscriber.objects.get(email="a@example.com").get_subscriber_status(),
            AbstractSubscriber.STATUS_SUBSCRIBED,
        )

        with self.assertLogs("nuntius", logging.INFO) as log_results:
            self.post_webhook(
                reverse("anymail:sendgrid_tracking_webhook"),
                self.sendgrid_payload(esp_message_id=ESP_MESSAGE_ID + "onemore"),
            )
        self.assertEqual(
            log_results.output,
            ["INFO:nuntius.signals:event_type=bounced recipient=a@example.com"],
        )

        self.assertEqual(
            Subscriber.objects.get(email="a@example.com").get_subscriber_status(),
            AbstractSubscriber.STATUS_BOUNCED,
        )

    @mock.patch("django.utils.timezone.now", mock_now_plus_8_days)
    @mock.patch("nuntius.actions.now", mock_now_plus_8_days)
    def test_consecutive_bounces_on_long_period(self):
        CampaignSentEvent.objects.create(
            email="a@example.com", result=CampaignSentStatusType.OK
        )
        with self.assertLogs("nuntius", logging.INFO) as log_results:
            self.post_webhook(
                reverse("anymail:sendgrid_tracking_webhook"),
                self.sendgrid_payload(esp_message_id=ESP_MESSAGE_ID + "first week"),
            )
            self.assertEqual(
                Subscriber.objects.get(email="a@example.com").get_subscriber_status(),
                AbstractSubscriber.STATUS_SUBSCRIBED,
            )
            self.post_webhook(
                reverse("anymail:sendgrid_tracking_webhook"),
                self.sendgrid_payload(esp_message_id=ESP_MESSAGE_ID + "one week later"),
            )
            self.assertEqual(
                Subscriber.objects.get(email="a@example.com").get_subscriber_status(),
                AbstractSubscriber.STATUS_BOUNCED,
            )

        self.assertEqual(
            log_results.output,
            [
                "INFO:nuntius.signals:event_type=bounced recipient=a@example.com",
                "INFO:nuntius.signals:event_type=bounced recipient=a@example.com",
            ],
        )
