import contextlib
import logging
import multiprocessing as mp
import multiprocessing.connection as mpc
import signal
import time
import traceback
from ctypes import c_double
from queue import Empty
from smtplib import SMTPServerDisconnected, SMTPException, SMTPRecipientsRefused
from typing import Dict, List, Tuple

from anymail.exceptions import AnymailError
from django.core import mail
from django.core.mail import EmailMessage
from django.core.management import BaseCommand
from django.db import ProgrammingError
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


class GracefulExit(Exception):
    pass


def gracefully_exit(sig, stack):
    raise GracefulExit()


def print_stack_trace(sig, stack):
    traceback.print_stack(stack)


def reset_sigmask(proc):
    """
    Decorator that resets sigmask to use for children.
    """

    @contextlib.wraps(proc)
    def wrapper(*args, **kwargs):
        signal.pthread_sigmask(signal.SIG_SETMASK, [])
        return proc(*args, **kwargs)

    return wrapper


@contextlib.contextmanager
def setup_signal_handlers_for_children():
    old_sigint_handler = None
    old_sigterm_handler = None
    signal.pthread_sigmask(signal.SIG_BLOCK, [signal.SIGTERM, signal.SIGINT])
    try:
        old_sigint_handler = signal.signal(signal.SIGINT, signal.SIG_IGN)
        old_sigterm_handler = signal.signal(signal.SIGTERM, signal.SIG_DFL)
        yield
    finally:
        if old_sigterm_handler:
            signal.signal(signal.SIGTERM, old_sigterm_handler)
        if old_sigint_handler:
            signal.signal(signal.SIGINT, old_sigint_handler)
        signal.pthread_sigmask(signal.SIG_UNBLOCK, [signal.SIGTERM, signal.SIGINT])


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
        self.lock = mp.RLock()
        self.timestamp = mp.Value(c_double, lock=False)
        self.timestamp.value = time.monotonic()
        self.value = mp.Value(c_double, lock=False)
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
        connection.messages_sent += 1
    except SMTPServerDisconnected:
        connection.close()
        connection.open()
        connection.messages_sent = 0
        raise


@reset_sigmask
def sender_process(
    *,
    queue: mp.Queue,
    error_channel: mpc.Connection,
    quit_event: mp.Event,
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
        try:
            with mail.get_connection(backend=app_settings.EMAIL_BACKEND) as connection:
                connection.messages_sent = 0
                while (
                    connection.messages_sent < app_settings.MAX_MESSAGES_PER_CONNECTION
                ):
                    if queue.empty() and quit_event.is_set():
                        return

                    # rate limit before the queue get so that the process does not
                    # sit on a message while being rate limited
                    if rate_limiter:
                        rate_limiter.take()

                    try:
                        message, sent_event_id = queue.get(
                            timeout=app_settings.POLLING_INTERVAL
                        )
                    except Empty:
                        continue

                    sent_event_qs = CampaignSentEvent.objects.filter(id=sent_event_id)
                    email = message.to[0]

                    try:
                        send_message(message, connection)
                    except (SMTPRecipientsRefused, AnymailRecipientsRefused):
                        CampaignSentEvent.objects.filter(id=sent_event_id).update(
                            result=CampaignSentStatusType.BLOCKED
                        )
                    except Exception:
                        traceback.print_exc()
                        campaign = Campaign.objects.get(
                            campaignsentevent__id=sent_event_id
                        )
                        error_channel.send(campaign.id)
                    else:
                        if hasattr(message, "anymail_status"):
                            if message.anymail_status.recipients[email].status in [
                                "invalid",
                                "rejected",
                                "failed",
                            ]:
                                sent_event_qs.update(
                                    result=CampaignSentStatusType.REJECTED
                                )
                            else:
                                sent_event_qs.update(
                                    result=CampaignSentStatusType.UNKNOWN,
                                    esp_message_id=message.anymail_status.recipients[
                                        email
                                    ].message_id,
                                )
                        else:
                            sent_event_qs.update(result=CampaignSentStatusType.UNKNOWN)
        except SMTPServerDisconnected:
            continue


@reset_sigmask
def campaign_manager_process(
    *, campaign: Campaign, queue: mp.Queue, quit_event: mp.Event
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

    finished = False

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
    else:
        finished = True

    queue.close()
    queue.join_thread()
    # everything has been scheduled for sending:
    if finished:
        campaign.status = Campaign.STATUS_SENT
        campaign.save()


class Command(BaseCommand):
    def handle(self, *args, **options):
        signal.signal(signal.SIGUSR1, print_stack_trace)
        signal.signal(signal.SIGTERM, gracefully_exit)

        # used by campaign managers processes to queue emails to send
        self.queue = mp.Queue(maxsize=app_settings.MAX_CONCURRENT_SENDERS * 2)

        # used to signals to sender they should exist once the queue has been emptied
        self.senders_quit_event = mp.Event()

        # used by email senders to make sure they're not going over the max rate
        self.rate_limiter = TokenBucket(
            max=app_settings.MAX_CONCURRENT_SENDERS * 2,
            rate=app_settings.MAX_SENDING_RATE,
        )

        # used by the main process to monitor the sender processes
        self.sender_processes: List[mp.Process] = []

        # used by sender processes to signal when a campaign failed, so that it can be stopped by the main process
        self.sender_pipes: List[mp.connection.Connection] = []

        # used by the main process to monitor campaign managers and tell them to quit
        self.campaign_manager_processes: Dict[int, Tuple[mp.Process, mp.Event]] = {}

        self.run_loop()

    def start_sender_processes(self):
        for i in range(
            app_settings.MAX_CONCURRENT_SENDERS - len(self.sender_processes)
        ):
            recv_conn, send_conn = mp.Pipe(duplex=False)
            process = mp.Process(
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
            with setup_signal_handlers_for_children():
                process.start()
            logger.info(f"Started sender process {process.pid}")

    def check_campaigns(self):
        campaigns = Campaign.objects.filter(
            status__in=[Campaign.STATUS_WAITING, Campaign.STATUS_SENDING]
        )

        # weird errors when iterating on these
        while True:
            try:
                campaigns = list(campaigns)
            except (ProgrammingError, StopIteration):
                pass
            else:
                break

        for campaign in campaigns:
            if (
                campaign.status == Campaign.STATUS_WAITING
                and campaign.id in self.campaign_manager_processes
            ):
                # we need to cancel that task
                logger.info(
                    f"Stopping campaign manager n°{campaign.id} ({campaign.name[:20]})..."
                )
                _, quit_event = self.campaign_manager_processes[campaign.id]
                quit_event.set()

            if (
                campaign.status == Campaign.STATUS_SENDING
                and campaign.id not in self.campaign_manager_processes
            ):
                quit_event = mp.Event()
                process = mp.Process(
                    target=campaign_manager_process,
                    kwargs={
                        "campaign": campaign,
                        "queue": self.queue,
                        "quit_event": quit_event,
                    },
                )
                process.daemon = True
                self.campaign_manager_processes[campaign.id] = (process, quit_event)
                with setup_signal_handlers_for_children():
                    process.start()
                logger.info(f"Started campaign manager {process.pid} for {campaign!r}")

    def monitor_processes(self):
        sender_sentinels = [p.sentinel for p in self.sender_processes]
        campaign_manager_sentinels = {
            p.sentinel: c_id for c_id, (p, _) in self.campaign_manager_processes.items()
        }

        events = mpc.wait(
            sender_sentinels + list(campaign_manager_sentinels) + self.sender_pipes,
            timeout=app_settings.POLLING_INTERVAL,
        )

        stopped_senders = []
        stopped_campaign_managers = []
        campaign_errors = set()

        for event in events:
            if event in sender_sentinels:
                stopped_senders.append(sender_sentinels.index(event))
            if event in campaign_manager_sentinels:
                stopped_campaign_managers.append(campaign_manager_sentinels[event])
            elif event in self.sender_pipes:
                while event.poll():
                    try:
                        campaign_errors.add(event.recv())
                    except EOFError:
                        break

        # reverse=True is important as we're removing elements from the sender_processes list by index
        for i in sorted(stopped_senders, reverse=True):
            process = self.sender_processes[i]
            # let's reap process to avoid zombies
            process.join()

            logger.error(f"Sender process {process.pid} unexpectedly quit...")
            del self.sender_processes[i]
            del self.sender_pipes[i]

        for campaign_id in sorted(stopped_campaign_managers):
            process, event = self.campaign_manager_processes[campaign_id]
            pid = process.pid
            # let's reap process to avoid zombies
            process.join()
            try:
                campaign = repr(Campaign.objects.get(id=campaign_id))
            except Campaign.DoesNotExist:
                # the campaign has most likely be deleted
                campaign = "[DELETED CAMPAIGN]"

            if event.is_set():
                # process was asked to stop and did so correctly
                logger.info(
                    f"Campaign manager {pid} correctly stopped... Was taking care of {campaign}."
                )
            else:
                logger.error(
                    f"Campaign manager {pid} abruptly stops. Was taking care of {campaign}."
                )

            del self.campaign_manager_processes[campaign_id]

        for campaign_id in campaign_errors:
            if campaign_id in self.campaign_manager_processes:
                logger.error(
                    f"Unexpected error while trying to send message from campaign {campaign_id}...\nStopping manager."
                )
                self.campaign_manager_processes[campaign_id][1].set()

    def run_loop(self):
        try:
            while True:
                self.start_sender_processes()
                self.check_campaigns()
                self.monitor_processes()
        except (GracefulExit, KeyboardInterrupt):
            logger.info("Asked to quit, asking all subprocesses to exit...")
            self.senders_quit_event.set()
            for _, event in self.campaign_manager_processes.values():
                event.set()

            logger.info("Waiting for all subprocesses to gracefully exit...")
            # active_children joins children so removes zombies
            while mp.active_children():
                mpc.wait(
                    [p.sentinel for p in self.sender_processes]
                    + [p.sentinel for p, _ in self.campaign_manager_processes.values()]
                )

            logger.info("All subprocesses have exited!")
