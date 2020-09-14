import logging
import multiprocessing
import multiprocessing.connection
import time
from ctypes import c_double
from smtplib import SMTPServerDisconnected, SMTPException, SMTPRecipientsRefused
from typing import Dict, List

from anymail.exceptions import AnymailError
from django.core import mail
from django.core.mail import EmailMessage
from django.core.management import BaseCommand
from django.db.models import Exists, OuterRef
from tenacity import (
    retry,
    stop_after_attempt,
    retry_if_exception_type,
    wait_random_exponential,
)

from nuntius import app_settings
from nuntius.messages import message_for_event
from nuntius.models import (
    Campaign,
    CampaignSentEvent,
    CampaignSentStatusType,
    AbstractSubscriber,
)

try:
    from anymail.exceptions import AnymailRecipientsRefused
except:

    class AnymailRecipientsRefused(BaseException):
        pass


logger = logging.getLogger(__name__)


class RateLimiter:
    def take(self):
        return


class TokenBucket(RateLimiter):
    """
    Simple multiprocessing token bucket implementation of the RateLimiter Interface

    Token buckets have the following principles :
    - They fill up at a fixed rate
    - They have a maximum capacity and will stop filling up when it is reached
    - Whenever a process calls `take`, if the bucket is full enough is is decreased ;
      if it is not the case, the process (and others) are blocked until is has filled
      in enough.
    """

    def __init__(self, max: int, rate: float):
        """Create a new TokenBucket.

        :param max: The maximum number of tokens that may be stored in the bucket
        :type max: class:`int`
        :param rate: The rate at which the bucket fills in, in number of tokens per second
        :type rate: class:`float`
        """
        self.max = max
        self.rate = rate
        self.lock = multiprocessing.RLock()
        self.timestamp = multiprocessing.Value(c_double, lock=False)
        self.timestamp.value = time.monotonic()
        self.value = multiprocessing.Value(c_double, lock=False)
        self.value.value = self.max

    def _current_time(self):
        """Returns monotonic current time in seconds.

        Splitted off in a method to increase testability.

        :return: current time in seconds, guaranteed monotonic
        """
        return time.monotonic()

    def _update(self):
        with self.lock:
            now = self._current_time()
            self.value.value = min(
                self.value.value + self.rate * (now - self.timestamp.value), self.max
            )
            self.timestamp.value = now

    def take(self, n=1):
        """
        Try to take a token, or wait for the bucket to fill in enough.

        If several processes take at the same time, the first one to call will takes
        a lock and will be guaranteed to be unblocked first. No such guarantee exists
        for the other processes.
        """
        with self.lock:
            self._update()
            self.value.value -= n

            if self.value.value < 0:
                time.sleep(-self.value.value / self.rate)


@retry(
    stop=stop_after_attempt(5),
    wait=wait_random_exponential(),
    retry=retry_if_exception_type((SMTPException, AnymailError)),
)
def send_message(message: EmailMessage, connection):
    """Send an email message and retry in cases of failures.

    This function will try sending up to 5 times, and uses an exponential
    backoff strategy, where a random waiting time is chosen between 0 and a max
    value that doubles every retry, to avoid all sender processes retrying at the
    same time.

    :param message: the email message to send
    :param connection: the connection to use to send the message

    """
    try:
        connection.send_messages([message])
    except SMTPServerDisconnected:
        connection.open()
        raise


def sender_process(
    *,
    queue: multiprocessing.Queue,
    error_channel: multiprocessing.connection.Connection,
    quit_event: multiprocessing.Event,
    rate_limiter: RateLimiter = None,
):
    """
    Main function of the processes responsible for sending email messages.

    This process pulls `(message: EmailMessage, event: CampaignSentEvent)`
    tuples from the work queue, tries to send the message and saves the result
    on the `event`.

    Whenever an unexpected error happens (i.e. which does not seem to be linked
    to a particular recipient), the process signals the error on the
    `error_channel` by sending the campaign id.

    It monitors its own connection to the mail service, and resets it every
    `nuntius.app_settings.MAX_MESSAGES_PER_CONNECTION` messages.

    :param queue: The work queue on which tuples (EmailMessage, CampaignSentEvent) are received.
    :type queue: class:`multiprocessing.Queue`

    :param error_channel: channel on which campaign ids of failing campaigns are sent.
    :type error_channel: class:`multiprocessing.connection.Connection`

    :param quit_event: event that may be used by the main process to signal to senders they need to quit
    :type quit_event: class:`multiprocessing.Event`

    :param rate_limiter: rate limiter to limit the rate of message sendings.
    :type rate_limiter: class:`RateLimiter`
    """
    message: EmailMessage
    sent_event_id: int

    while True:
        with mail.get_connection(backend=app_settings.EMAIL_BACKEND) as connection:
            for i in range(app_settings.MAX_MESSAGES_PER_CONNECTION):
                if queue.empty() and quit_event.is_set():
                    return

                # rate limit before the queue get so that the process does not
                # sit on a message while being rate limited
                if rate_limiter:
                    rate_limiter.take()
                message, sent_event_id = queue.get()
                sent_event_qs = CampaignSentEvent.objects.filter(id=sent_event_id)
                email = message.to[0]

                try:
                    send_message(message, connection)
                except (SMTPRecipientsRefused, AnymailRecipientsRefused):
                    CampaignSentEvent.objects.filter(id=sent_event_id).update(
                        result=CampaignSentStatusType.BLOCKED
                    )
                except Exception:
                    campaign = Campaign.objects.get(campaignsentevent__id=sent_event_id)
                    error_channel.send(campaign.id)
                else:
                    if hasattr(message, "anymail_status"):
                        if message.anymail_status.recipients[email].status in [
                            "invalid",
                            "rejected",
                            "failed",
                        ]:
                            sent_event_qs.update(result=CampaignSentStatusType.REJECTED)
                        else:
                            sent_event_qs.update(
                                result=CampaignSentStatusType.UNKNOWN,
                                esp_message_id=message.anymail_status.recipients[
                                    email
                                ].message_id,
                            )
                    else:
                        sent_event_qs.update(result=CampaignSentStatusType.UNKNOWN)


def campaign_manager_process(
    *,
    campaign: Campaign,
    queue: multiprocessing.Queue,
    quit_event: multiprocessing.Event,
):
    """
    Main function of the process responsible for scheduling the sending of campaigns

    :param campaign: the campaign for which messages must be sent
    :type campaign: :class:`nuntius.models.Campaign`

    :param queue: the work queue on which email messages are put
    :type queue: : class:`multiprocessing.Queue`

    :param quit_event: an event that may be used by the main process to tell the manager it needs to quit
    :type quit_event: class:`multiprocessing.Event`
    """
    queryset = campaign.get_subscribers_queryset()
    # eliminate people who already received the message
    queryset = queryset.annotate(
        already_sent=Exists(
            CampaignSentEvent.objects.filter(
                subscriber_id=OuterRef("pk"), campaign_id=campaign.id
            ).exclude(result=CampaignSentStatusType.PENDING)
        )
    ).filter(already_sent=False)

    for subscriber in queryset.iterator():
        if quit_event.is_set():
            # quit if sending is paused
            break

        if subscriber.get_subscriber_status() != AbstractSubscriber.STATUS_SUBSCRIBED:
            continue

        sent_event = campaign.get_event_for_subscriber(subscriber)

        if sent_event.result != CampaignSentStatusType.PENDING:
            # just in case there is another nuntius_worker started, but this should not happen
            continue

        message = message_for_event(sent_event)

        queue.put((message, sent_event.id))

    queue.close()
    queue.join_thread()
    # everything has been scheduled for sending:
    campaign.status = Campaign.STATUS_SENT
    campaign.save()


class Command(BaseCommand):
    def handle(self, *args, **options):
        # used by campaign managers processes to queue emails to send
        self.queue = multiprocessing.Queue(
            maxsize=app_settings.MAX_CONCURRENT_SENDERS * 2
        )

        # used to signals to sender they should exist once the queue has been emptied
        self.senders_quit_event = multiprocessing.Event()

        # used by email senders to make sure they're not going over the max rate
        self.rate_limiter = TokenBucket(
            max=app_settings.MAX_CONCURRENT_SENDERS * 2,
            rate=app_settings.MAX_SENDING_RATE,
        )

        # used by the main process to ensure that processes are still alive
        self.sender_processes: List[multiprocessing.Process] = []
        self.campaign_manager_processes: List[multiprocessing.Process] = []

        # used by sender processes to signal when a campaign failed, so that it can be stopped by the main process
        self.sender_pipes: List[multiprocessing.connection.Connection] = []

        # used by the main process to signal to a campaign manager that it should quit
        self.campaign_manager_quit_events: Dict[int, multiprocessing.Event] = {}

        self.run_loop()

    def start_sender_processes(self):
        for i in range(
            app_settings.MAX_CONCURRENT_SENDERS - len(self.sender_processes)
        ):
            logger.info("Starting up sender process...")
            recv_conn, send_conn = multiprocessing.Pipe(duplex=False)
            process = multiprocessing.Process(
                target=sender_process,
                kwargs={
                    "queue": self.queue,
                    "error_channel": send_conn,
                    "rate_limiter": self.rate_limiter,
                    "quit_event": self.senders_quit_event,
                },
            )
            process.daemon = True

            self.sender_processes.append(process)
            self.sender_pipes.append(recv_conn)
            process.start()
            logger.info("Sender process started")

    def check_campaigns(self):
        campaigns = Campaign.objects.filter(
            status__in=[Campaign.STATUS_WAITING, Campaign.STATUS_SENDING]
        )

        for campaign in campaigns:
            if (
                campaign.status == Campaign.STATUS_WAITING
                and campaign.id in self.campaign_manager_quit_events
            ):
                # we need to cancel that task
                logger.info(
                    f"Stopping campaign manager n°{campaign.id} ({campaign.name[:20]})..."
                )
                quit_event = self.campaign_manager_quit_events.pop(campaign.id)
                quit_event.set()

            if (
                campaign.status == Campaign.STATUS_SENDING
                and campaign.id not in self.campaign_manager_quit_events
            ):
                logger.info(
                    f"Starting campaign manager n°{campaign.id} ({campaign.name[:20]})..."
                )
                quit_event = multiprocessing.Event()
                self.campaign_manager_quit_events[campaign.id] = quit_event
                process = multiprocessing.Process(
                    target=campaign_manager_process,
                    kwargs={
                        "campaign": campaign,
                        "queue": self.queue,
                        "quit_event": quit_event,
                    },
                )
                process.daemon = True
                self.campaign_manager_processes.append(process)
                process.start()
                logger.info("Campaign started...")

    def monitor_processes(self):
        sender_sentinels = [p.sentinel for p in self.sender_processes]
        campaign_manager_sentinels = [
            p.sentinel for p in self.campaign_manager_processes
        ]

        events = multiprocessing.connection.wait(
            sender_sentinels + campaign_manager_sentinels + self.sender_pipes,
            timeout=app_settings.POLLING_INTERVAL,
        )

        stopped_senders = []
        stopped_campaign_managers = []
        campaign_errors = set()

        for event in events:
            if event in sender_sentinels:
                stopped_senders.append(sender_sentinels.index(event))
            if event in stopped_campaign_managers:
                stopped_campaign_managers = campaign_manager_sentinels.index(event)
            elif event in self.sender_pipes:
                while event.poll():
                    campaign_errors.add(event.recv())

        for i in sorted(stopped_senders, reverse=True):
            logger.error("Sender process unexpectedly quit...")
            del self.sender_processes[i]
            del self.sender_pipes[i]

        for i in sorted(stopped_campaign_managers):
            # TODO
            pass

        for campaign_id in campaign_errors:
            if campaign_id in self.campaign_manager_quit_events:
                logger.error(
                    f"Unexpected error while trying to send message from campaign {campaign_id}...\nStopping manager."
                )
                self.campaign_manager_quit_events[campaign_id].signal()
                del self.campaign_manager_quit_events[campaign_id]

    def run_loop(self):
        while True:
            self.start_sender_processes()
            self.check_campaigns()
            self.monitor_processes()
