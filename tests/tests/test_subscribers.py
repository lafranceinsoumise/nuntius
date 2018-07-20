from django.test import TestCase

from nuntius.models import BaseSubscriber
from tests.models import TestSubscriber


class SimpleSubscriberTestCase(TestCase):
    def test_use_email_property(self):
        subscriber = TestSubscriber(email='email@example.com')
        self.assertEqual(subscriber.get_subscriber_email(), 'email@example.com')

    def test_use_status_property(self):
        subscriber = TestSubscriber(email='email@example.com', subscriber_status=BaseSubscriber.STATUS_SUBSCRIBED)
        self.assertEqual(subscriber.get_subscriber_status(), BaseSubscriber.STATUS_SUBSCRIBED)
        subscriber.set_subscriber_status(BaseSubscriber.STATUS_UNSUBSCRIBED)
        self.assertEqual(subscriber.get_subscriber_status(), BaseSubscriber.STATUS_UNSUBSCRIBED)
