import multiprocessing
from queue import Queue, Empty

from django.core import mail
from django.core.mail import EmailMessage
from django.test import TestCase

from nuntius.management.commands import nuntius_worker
from nuntius.management.commands.nuntius_worker import sender_process
from nuntius.messages import message_for_event
from nuntius.models import Campaign, BaseSubscriber
from tests.models import TestSegment, TestSubscriber


def run_campaign_manager_process_sync(campaign):
    queue = Queue()
    queue.close = lambda: None
    queue.join_thread = lambda: None

    nuntius_worker.campaign_manager_process(
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

    sender_process(
        queue=queue,
        error_channel=error_channel or "SHOULD NOT BE USED",
        quit_event=quit_event,
    )


class MessageTestCase(TestCase):
    fixtures = ["subscribers.json"]

    def test_correctly_generate_text_only_message_from_subscriber(self):
        campaign = Campaign.objects.create(
            message_from_email="test@example.com",
            message_subject="Nice campaign",
            message_content_text="Here's some text for you {{ email }} !",
        )

        subscriber = TestSubscriber.objects.get(email="a@example.com")
        event = campaign.get_event_for_subscriber(subscriber)
        message = message_for_event(event)

        self.assertIsInstance(message, EmailMessage)
        self.assertEqual(message.subject, "Nice campaign")
        self.assertEqual(message.from_email, "test@example.com")
        self.assertEqual(message.to, [subscriber.email])
        self.assertEqual(message.body, "Here's some text for you a@example.com !")
        self.assertEqual(message.content_subtype, "plain")

    def test_send_campaign(self):
        segment = TestSegment.objects.get(id="subscribed")
        campaign = Campaign.objects.create(
            segment=segment,
            message_from_email="test@example.com",
            message_from_name="Test sender",
            message_subject="Subject",
        )

        messages = [m for m, _ in run_campaign_manager_process_sync(campaign)]

        self.assertEqual(segment.get_subscribers_queryset().count(), len(messages))

        emails = [s.get_subscriber_email() for s in segment.get_subscribers_queryset()]

        self.assertCountEqual([m.to[0] for m in messages], emails)

        for message in messages:
            self.assertEqual(message.subject, "Subject")
            self.assertEqual(message.from_email, "Test sender <test@example.com>")

    def test_messages_for_campaign_without_segment(self):
        campaign = Campaign.objects.create()
        messages = [m for m, _ in run_campaign_manager_process_sync(campaign)]
        self.assertEqual(
            TestSubscriber.objects.filter(
                subscriber_status=BaseSubscriber.STATUS_SUBSCRIBED
            ).count(),
            len(messages),
        )

    def test_send_only_to_subscribed(self):
        segment = TestSegment.objects.get(id="all_status")
        campaign = Campaign.objects.create(segment=segment)
        messages = [m for m, _ in run_campaign_manager_process_sync(campaign)]

        self.assertEqual(
            segment.get_subscribers_queryset()
            .filter(subscriber_status=BaseSubscriber.STATUS_SUBSCRIBED)
            .count(),
            len(messages),
        )


class SendingTestCase(TestCase):
    fixtures = ["subscribers.json"]

    def test_segments(self):
        self.assertEqual(
            TestSegment.objects.get(id="subscribed").get_subscribers_queryset().count(),
            2,
        )

    def test_send_emails(self):
        segment = TestSegment.objects.get(id="subscribed")
        campaign = Campaign.objects.create(
            segment=segment,
            message_from_email="test@example.com",
            message_from_name="Test sender",
            message_subject="Subject",
            message_content_text="test {{email}} test",
        )
        subscribers = segment.get_subscribers_queryset()
        events = [campaign.get_event_for_subscriber(s) for s in subscribers]
        messages = [message_for_event(e) for e in events]

        run_sender_process_sync(zip(messages, (e.id for e in events)))

        self.assertEqual(len(events), len(mail.outbox))
        self.assertEqual(len(events), campaign.get_sent_count())

    def test_send_only_once(self):
        segment = TestSegment.objects.get(id="subscribed")
        campaign = Campaign.objects.create(segment=segment, message_content_text="test")
        message_events_tuple = run_campaign_manager_process_sync(campaign)
        run_sender_process_sync(message_events_tuple)

        self.assertEqual(
            len(message_events_tuple), segment.get_subscribers_queryset().count()
        )
        self.assertEqual(len(message_events_tuple), len(mail.outbox))
        self.assertEqual(len(message_events_tuple), campaign.get_sent_count())

        new_messages_tuple = run_campaign_manager_process_sync(campaign)
        self.assertEqual(len(new_messages_tuple), 0)
