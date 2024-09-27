import multiprocessing
from queue import Queue, Empty
from unittest.mock import patch, Mock

from django.test import TestCase

from nuntius.management.commands import nuntius_worker
from nuntius.models import PushCampaign, BaseSubscriber
from nuntius.utils.notifications import notification_for_event
from standalone.models import Subscriber, Segment


def run_campaign_manager_process_sync(campaign):
    queue = Queue()
    queue.close = lambda: None
    queue.join_thread = lambda: None

    nuntius_worker.push_campaign_manager_process(
        campaign=campaign, queue=queue, quit_event=multiprocessing.Event()
    )
    message_event_tuples = []
    while not queue.empty():
        message_event_tuples.append(queue.get_nowait())
    return message_event_tuples


def run_sender_process_sync(message_event_tuples, error_channel=None):
    queue = Queue()

    for t in message_event_tuples:
        queue.put(t)

    quit_event = multiprocessing.Event()

    original_get = queue.get

    def get(timeout):
        try:
            return original_get(block=False)
        except Empty:
            quit_event.set()
            raise

    queue.get = get

    nuntius_worker.pusher_process(
        queue=queue,
        error_channel=error_channel or "SHOULD NOT BE USED",
        quit_event=quit_event,
    )


class NotificationContentTestCase(TestCase):
    fixtures = ["subscribers.json"]

    def test_correctly_serialize_notification_content_from_campaign(self):
        campaign = PushCampaign.objects.create(
            notification_title="Notification",
            notification_url="https://nunti.us?push=push",
            notification_body="Hey, something happened!",
            notification_tag="Tag",
            notification_icon="https://nunti.us/icon.jpg",
            utm_name="push_campaign",
        )

        subscriber = Subscriber.objects.first()
        event = campaign.get_event_for_subscriber(subscriber)
        notification = notification_for_event(event)

        self.assertEqual(notification["title"], campaign.notification_title)
        self.assertEqual(notification["body"], campaign.notification_body)
        self.assertEqual(notification["tag"], campaign.notification_tag)
        self.assertEqual(notification["icon"], campaign.notification_icon)
        self.assertIn("url", notification)

    def test_send_campaign_to_segment(self):
        segment = Segment.objects.get(id="subscribed")
        campaign = PushCampaign.objects.create(
            notification_title="Notification",
            notification_url="https://nunti.us",
            notification_body="Hey, something happened!",
            utm_name="push_campaign",
            segment=segment,
        )
        subscriber_count = segment.get_subscribers_queryset().count()
        notifications = [n for n, _ in run_campaign_manager_process_sync(campaign)]
        self.assertEqual(subscriber_count, len(notifications))

    def test_send_campaign_without_segment(self):
        campaign = PushCampaign.objects.create(
            notification_title="Notification",
            notification_url="https://nunti.us",
            notification_body="Hey, something happened!",
            utm_name="push_campaign",
        )
        subscriber_count = Subscriber.objects.filter(
            subscriber_status=BaseSubscriber.STATUS_SUBSCRIBED
        ).count()
        notifications = [n for n, _ in run_campaign_manager_process_sync(campaign)]
        self.assertEqual(subscriber_count, len(notifications))

    def test_send_campaign_only_to_subscribed(self):
        segment = Segment.objects.get(id="all_status")
        campaign = PushCampaign.objects.create(
            notification_title="Notification",
            notification_url="https://nunti.us",
            notification_body="Hey, something happened!",
            utm_name="push_campaign",
            segment=segment,
        )

        subscriber_count = (
            segment.get_subscribers_queryset()
            .filter(subscriber_status=BaseSubscriber.STATUS_SUBSCRIBED)
            .count()
        )
        notifications = [n for n, _ in run_campaign_manager_process_sync(campaign)]
        self.assertEqual(subscriber_count, len(notifications))


try:
    from push_notifications.models import GCMDevice
except ImportError:
    pass
else:

    class PushingTestCase(TestCase):
        fixtures = ["subscribers.json"]

        def setUp(self) -> None:
            self.subscriber = Subscriber.objects.create(
                email="subscriber@nunti.us",
                subscriber_status=Subscriber.STATUS_SUBSCRIBED,
            )
            self.segment = Segment.objects.create(id="push_segment")
            self.subscriber.segments.add(self.segment)
            self.subscriber.save()
            self.gcm_device = GCMDevice.objects.create(
                name="",
                active=True,
                device_id=hex(self.subscriber.id),
                registration_id=self.subscriber.email,
            )

        def test_segments(self):
            self.assertEqual(self.segment.get_subscribers_queryset().count(), 1)

        def test_devices(self):
            devices = self.subscriber.get_subscriber_push_devices()
            self.assertEqual(len(devices), 2)
            self.assertIn(self.gcm_device, devices)

        @patch("nuntius.utils.notifications.push_gcm_notification", side_effect=Mock())
        def test_push_notifications(self, gcm_push):
            campaign = PushCampaign.objects.create(
                notification_title="Notification",
                notification_url="https://nunti.us",
                notification_body="Hey, something happened!",
                utm_name="push_campaign",
                segment=self.segment,
            )
            subscribers = self.segment.get_subscribers_queryset()
            events = [campaign.get_event_for_subscriber(s) for s in subscribers]
            notifications = [notification_for_event(e) for e in events]

            gcm_push.assert_not_called()

            run_sender_process_sync(zip(notifications, (e.id for e in events)))

            gcm_push.assert_called_once_with(
                self.gcm_device, notifications[0], campaign.id
            )

            self.assertEqual(len(events), campaign.get_sent_count())

        @patch("nuntius.utils.notifications.push_gcm_notification", side_effect=Mock())
        def test_send_only_once(self, gcm_push):
            campaign = PushCampaign.objects.create(
                notification_title="Notification",
                notification_url="https://nunti.us",
                notification_body="Hey, something happened!",
                utm_name="push_campaign",
                segment=self.segment,
            )
            notification_events_tuple = run_campaign_manager_process_sync(campaign)

            gcm_push.assert_not_called()

            run_sender_process_sync(notification_events_tuple)

            gcm_push.assert_called()

            self.assertEqual(
                len(notification_events_tuple),
                self.segment.get_subscribers_queryset().count(),
            )
            self.assertEqual(len(notification_events_tuple), campaign.get_sent_count())

            gcm_push.reset_mock()

            notification_events_tuple = run_campaign_manager_process_sync(campaign)

            gcm_push.assert_not_called()

            self.assertEqual(len(notification_events_tuple), 0)
