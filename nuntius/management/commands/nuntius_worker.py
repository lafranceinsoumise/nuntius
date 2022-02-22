import contextlib
import logging
import multiprocessing as mp
import multiprocessing.connection as mpc
import signal
import smtplib
from argparse import ArgumentTypeError
from typing import Dict, List, Tuple

from django.core import mail
from django.core.mail import EmailMessage
from django.core.management import BaseCommand
from django.db import connection
from django.db.models import Exists, OuterRef
from django.utils import timezone
from django.utils.translation import gettext as _, gettext_lazy
from tenacity import (
    retry,
    stop_after_attempt,
    retry_if_exception_type,
    wait_random_exponential,
    TryAgain,
)

from nuntius import app_settings
from nuntius.app_settings import CAMPAIGN_TYPE_EMAIL, CAMPAIGN_TYPE_PUSH
from nuntius.messages import message_for_event
from nuntius.models import (
    Campaign,
    CampaignSentEvent,
    CampaignSentStatusType,
    PushCampaign,
    PushCampaignSentEvent,
    PushCampaignSentStatusType,
    AbstractSubscriber,
)
from nuntius.utils.notifications import (
    notification_for_event,
    push_notification,
    get_pushing_error_classes,
)
from nuntius.utils.processes import (
    gracefully_exit,
    print_stack_trace,
    reset_sigmask,
    RateLimiter,
    TokenBucket,
    RateMeter,
    GracefulExit,
    get_from_queue_or_quit,
    put_in_queue_or_quit,
    unexpected_exc_logger,
)

try:
    from anymail import exceptions as anymail_exceptions

    AnymailError = anymail_exceptions.AnymailError
    AnymailAPIError = anymail_exceptions.AnymailAPIError
    AnymailRecipientsRefused = anymail_exceptions.AnymailRecipientsRefused
except:

    class FakeException(Exception):
        pass

    AnymailError = AnymailRecipientsRefused = AnymailAPIError = FakeException


logger = logging.getLogger(__name__)


class ConnectionManager:
    """
    Manager around the SMTP or Mail API connection that handles reconnection and quitting
    """

    CONNECTION_ERRORS = (ConnectionError, smtplib.SMTPException, AnymailError)
    MAIL_SENDING_ERRORS = (
        smtplib.SMTPSenderRefused,
        smtplib.SMTPDataError,
        AnymailAPIError,
    )

    def __init__(self, quit_event):
        self._connection = mail.get_connection(backend=app_settings.EMAIL_BACKEND)
        self._message_counter = 0
        self._quit_event = quit_event

    @retry(
        wait=wait_random_exponential(max=30),
        retry=retry_if_exception_type(CONNECTION_ERRORS),
    )
    def open_connection(self):
        """
        Connect to the SMTP or API server and retry with exponential backoff.

        This function will try up to 5 times to connect to the server, allowing for shaky
        connections.
        """
        if self._quit_event.is_set():
            raise GracefulExit()

        try:
            self._connection.open()
        except Exception:
            self._connection.close()
            raise
        else:
            self._message_counter = 0

    @retry(
        stop=stop_after_attempt(5),
        wait=wait_random_exponential(),
        retry=retry_if_exception_type(MAIL_SENDING_ERRORS),
    )
    def send_message(self, message: EmailMessage):
        """
        Send an email message and retry in cases of failures.

        This function will try sending up to 5 times, and uses an exponential
        backoff strategy, where a random waiting time is chosen between 0 and a max
        value that doubles every retry, to avoid all sender processes retrying at the
        same time.

        :param message: the email message to send
        :param connection: the connection to use to send the message
        """
        if self._quit_event.is_set():
            raise GracefulExit()

        if (
            app_settings.MAX_MESSAGES_PER_CONNECTION
            and self._message_counter >= app_settings.MAX_MESSAGES_PER_CONNECTION
        ):
            self._connection.close()
            self.open_connection()
        try:
            self._connection.send_messages([message])
            self._message_counter += 1
        except smtplib.SMTPServerDisconnected:
            self._connection.close()
            self.open_connection()
            raise TryAgain

    def __enter__(self):
        self.open_connection()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self._connection.close()


class PushManager:
    """
    Manager around the push notification sending that handles retrying
    """

    def __init__(self, quit_event):
        self._quit_event = quit_event

    @retry(
        stop=stop_after_attempt(5),
        wait=wait_random_exponential(),
        retry=retry_if_exception_type(get_pushing_error_classes()),
    )
    def push(self, notification, push_sent_event):
        """
        Send a push notification and retry in cases of failures.

        This function will try sending up to 5 times, and uses an exponential
        backoff strategy, where a random waiting time is chosen between 0 and a max
        value that doubles every retry, to avoid all sender processes retrying at the
        same time.
        """
        if self._quit_event.is_set():
            raise GracefulExit()

        push_notification(notification, push_sent_event)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass


@reset_sigmask
@unexpected_exc_logger
def mailer_process(
    *,
    queue: mp.Queue,
    error_channel: mpc.Connection,
    quit_event: mp.Event,
    rate_limiter: RateLimiter = None,
    rate_meter: RateMeter = None,
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
    :type rate_limiter: class:`nuntius.utils.processes.RateLimiter`

    :param rate_meter: rate meter to allow measuring the sending speed
    :type rate_meter: class:`nuntius.utils.processes.RateMeter`
    """
    message: EmailMessage
    sent_event_id: int

    try:
        with ConnectionManager(quit_event) as connection_manager:
            while True:
                # the timeout allows the loop to start again every few seconds so that the
                # quit_event is checked and the process can quit if it has to.
                message, sent_event_id = get_from_queue_or_quit(
                    queue,
                    event=quit_event,
                    polling_period=app_settings.POLLING_INTERVAL,
                )

                sent_event_qs = CampaignSentEvent.objects.filter(id=sent_event_id)
                # messages generated by the campaign manager should only have one recipient
                email = message.to[0]

                # rate limit just before sending
                if rate_limiter:
                    rate_limiter.take()

                try:
                    connection_manager.send_message(message)
                except (smtplib.SMTPRecipientsRefused, AnymailRecipientsRefused):
                    # exceptions linked to a specific recipient need not stop the sending
                    CampaignSentEvent.objects.filter(id=sent_event_id).update(
                        result=CampaignSentStatusType.BLOCKED
                    )
                except GracefulExit:
                    raise
                except Exception:
                    campaign = Campaign.objects.get(campaignsentevent__id=sent_event_id)
                    error_channel.send(campaign.id)
                    logger.error(
                        _("Error while sending email for campaign %(campaign)s")
                        % repr(campaign),
                        exc_info=True,
                    )

                else:
                    if rate_meter:
                        rate_meter.count_up()
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
    except GracefulExit:
        return


@reset_sigmask
@unexpected_exc_logger
def pusher_process(
    *,
    queue: mp.Queue,
    error_channel: mpc.Connection,
    quit_event: mp.Event,
    rate_limiter: RateLimiter = None,
    rate_meter: RateMeter = None,
):
    """
    Main function of the processes responsible for sending push notifications.

    This process pulls `(push_notification, event: PushCampaignSentEvent)`
    tuples from the work queue, tries to send the push and saves the result
    on the `event`.

    Whenever an unexpected error happens (i.e. which does not seem to be linked
    to a particular recipient), the process signals the error on the
    `error_channel` by sending the campaign id.

    It monitors its own connection to the mail service, and resets it every
    `nuntius.app_settings.MAX_MESSAGES_PER_CONNECTION` messages.

    :param queue: The work queue on which tuples (push_notification, CampaignSentEvent) are received.
    :type queue: class:`multiprocessing.Queue`

    :param error_channel: channel on which campaign ids of failing campaigns are sent.
    :type error_channel: class:`multiprocessing.connection.Connection`

    :param quit_event: event that may be used by the main process to signal to senders they need to quit
    :type quit_event: class:`multiprocessing.Event`

    :param rate_limiter: rate limiter to limit the rate of message sendings.
    :type rate_limiter: class:`nuntius.utils.processes.RateLimiter`

    :param rate_meter: rate meter to allow measuring the sending speed
    :type rate_meter: class:`nuntius.utils.processes.RateMeter`
    """
    notification: dict
    push_sent_event_id: int

    try:
        with PushManager(quit_event) as push_manager:
            while True:
                # the timeout allows the loop to start again every few seconds so that the
                # quit_event is checked and the process can quit if it has to.
                notification, push_sent_event_id = get_from_queue_or_quit(
                    queue,
                    event=quit_event,
                    polling_period=app_settings.POLLING_INTERVAL,
                )

                # rate limit just before sending
                if rate_limiter:
                    rate_limiter.take()

                try:
                    push_sent_event = PushCampaignSentEvent.objects.get(
                        id=push_sent_event_id
                    )
                    push_manager.push(notification, push_sent_event)
                except GracefulExit:
                    raise
                except PushCampaignSentEvent.DoesNotExist:
                    logger.error(
                        _(
                            f"Push campaign sent event with id '{push_sent_event_id}' not found"
                        ),
                        exc_info=True,
                    )
                except Exception:
                    push_campaign = PushCampaign.objects.get(
                        pushcampaignsentevent__id=push_sent_event_id
                    )
                    error_channel.send(push_campaign.id)
                    logger.error(
                        _(
                            f"Error while pushing notification for campaign {repr(push_campaign)}"
                        ),
                        exc_info=True,
                    )
                else:
                    if rate_meter:
                        rate_meter.count_up()

    except GracefulExit:
        return


@reset_sigmask
@unexpected_exc_logger
def email_campaign_manager_process(
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

    campaign_finished = False

    for subscriber in queryset.iterator():
        if quit_event.is_set():
            break

        if subscriber.get_subscriber_status() != AbstractSubscriber.STATUS_SUBSCRIBED:
            continue

        sent_event = campaign.get_event_for_subscriber(subscriber)

        # just in case there is another nuntius_worker started, but this should not happen
        if sent_event.result != CampaignSentStatusType.PENDING:
            continue

        message = message_for_event(sent_event)

        try:
            put_in_queue_or_quit(
                queue,
                (message, sent_event.id),
                event=quit_event,
                polling_period=app_settings.POLLING_INTERVAL,
            )
        except GracefulExit:
            break
    else:
        campaign_finished = True

    queue.close()
    queue.join_thread()
    # everything has been scheduled for sending:
    if campaign_finished:
        campaign.status = Campaign.STATUS_SENT
        campaign.save()


@reset_sigmask
@unexpected_exc_logger
def push_campaign_manager_process(
    *, campaign: PushCampaign, queue: mp.Queue, quit_event: mp.Event
):
    """
    Main function of the process responsible for scheduling the pushing of campaigns

    :param campaign: the campaign for which messages must be pushed
    :type campaign: :class:`nuntius.models.PushCampaign`

    :param queue: the work queue on which email messages are put
    :type queue: : class:`multiprocessing.Queue`

    :param quit_event: an event that may be used by the main process to tell the manager it needs to quit
    :type quit_event: class:`multiprocessing.Event`
    """
    queryset = campaign.get_subscribers_queryset()
    # eliminate people who already received the message
    queryset = queryset.annotate(
        already_sent=Exists(
            PushCampaignSentEvent.objects.filter(
                subscriber_id=OuterRef("pk"), campaign_id=campaign.id
            ).exclude(result=PushCampaignSentStatusType.PENDING)
        )
    ).filter(already_sent=False)

    campaign_finished = False

    for subscriber in queryset.iterator():
        if quit_event.is_set():
            break

        if subscriber.get_subscriber_status() != AbstractSubscriber.STATUS_SUBSCRIBED:
            continue

        push_sent_event = campaign.get_event_for_subscriber(subscriber)

        if (
            push_sent_event is None
            or push_sent_event.result != PushCampaignSentStatusType.PENDING
        ):
            # just in case there is another nuntius_worker started, but this should not happen
            continue

        notification = notification_for_event(push_sent_event)

        try:
            put_in_queue_or_quit(
                queue,
                (notification, push_sent_event.id),
                event=quit_event,
                polling_period=app_settings.POLLING_INTERVAL,
            )
        except GracefulExit:
            break
    else:
        campaign_finished = True

    queue.close()
    queue.join_thread()
    # everything has been scheduled for sending:
    if campaign_finished:
        campaign.status = Campaign.STATUS_SENT
        if campaign.first_sent is None:
            campaign.first_sent = timezone.now()
        campaign.save()


CAMPAIGN_TYPE = {
    CAMPAIGN_TYPE_EMAIL: {
        "CampaignModel": Campaign,
        "sender_process": mailer_process,
        "manager_process": email_campaign_manager_process,
    },
    CAMPAIGN_TYPE_PUSH: {
        "CampaignModel": PushCampaign,
        "sender_process": pusher_process,
        "manager_process": push_campaign_manager_process,
    },
}


def campaign_types_argument(campaign_types):
    if not isinstance(campaign_types, str):
        raise ArgumentTypeError("The campaign type must be a string")

    campaign_types = campaign_types.lower().split(",")

    for campaign_type in campaign_types:
        if campaign_type not in CAMPAIGN_TYPE.keys():
            raise ArgumentTypeError(
                f"'{campaign_type}': this campaign type does not exist, possible choices are: {', '.join(CAMPAIGN_TYPE.keys())}"
            )

    return campaign_types


class Command(BaseCommand):
    STATS_MESSAGE = gettext_lazy(
        """
%(campaign_type)s STATISTICS
Message queue size: %(queue_size)s
Sender processes: %(sender_processes)s
Campaign managers: %(campaign_managers)s
Token bucket current capacity: %(bucket_capacity)s
Current sending rate: %(sending_rate)s"""
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "-t",
            "--types",
            dest="campaign_types",
            default=app_settings.ENABLED_CAMPAIGN_TYPES,
            type=campaign_types_argument,
            help="The comma-separated list of campaign types for which to start the workers. "
            f"Valid choices are: {', '.join(CAMPAIGN_TYPE.keys())}. "
            "Defaults to: 'email'",
        )

    def handle(self, *args, campaign_types=None, **options):
        # used by campaign managers processes to queue messages to send
        self.queue = {
            key: mp.Queue(maxsize=app_settings.MAX_CONCURRENT_SENDERS)
            for key in CAMPAIGN_TYPE.keys()
        }

        # used to signals to sender they should exist once the queue has been emptied
        self.senders_quit_event = mp.Event()

        # used by email senders to make sure they're not going over the max rate
        self.rate_limiter = TokenBucket(
            max=app_settings.MAX_CONCURRENT_SENDERS * 2,
            rate=app_settings.MAX_SENDING_RATE,
        )

        # allow us to measure the sending speed
        self.rate_meter = RateMeter(0.3, 0.5)

        # used by the main process to monitor the sender processes
        self.sender_processes: Dict[str, List[mp.Process]] = {
            key: [] for key in CAMPAIGN_TYPE.keys()
        }

        # used by sender processes to signal when a campaign failed, so that it can be stopped by the main process
        self.sender_pipes: Dict[str, List[mp.connection.Connection]] = {
            key: [] for key in CAMPAIGN_TYPE.keys()
        }

        # used by the main process to monitor campaign managers and tell them to quit
        self.campaign_manager_processes: Dict[
            str, Dict[int, Tuple[mp.Process, mp.Event]]
        ] = {key: {} for key in CAMPAIGN_TYPE.keys()}

        self._setup_signals()
        self.run_loop(campaign_types)

    def _setup_signals(self):
        signal.signal(signal.SIGINT, signal.default_int_handler)
        signal.signal(signal.SIGTERM, gracefully_exit)
        signal.signal(signal.SIGUSR1, self.print_stats)
        signal.signal(signal.SIGUSR2, print_stack_trace)

    @contextlib.contextmanager
    def _setup_signal_handlers_for_children(self):
        try:
            signal.pthread_sigmask(signal.SIG_BLOCK, [signal.SIGTERM, signal.SIGINT])
            signal.signal(signal.SIGINT, signal.SIG_IGN)
            signal.signal(signal.SIGTERM, signal.SIG_DFL)
            signal.signal(signal.SIGUSR1, signal.SIG_DFL)
            signal.signal(signal.SIGUSR2, signal.SIG_DFL)
            yield
        finally:
            self._setup_signals()
            signal.pthread_sigmask(signal.SIG_UNBLOCK, [signal.SIGTERM, signal.SIGINT])

    def print_stats(self, sig, stack):
        for campaign_type in CAMPAIGN_TYPE.keys():
            values = {
                "campaign_type": campaign_type.upper(),
                "queue_size": self.queue[campaign_type].qsize(),
                "sender_processes": [
                    process.pid for process in self.sender_processes[campaign_type]
                ],
                "campaign_managers": [
                    process.pid
                    for process, _ in self.campaign_manager_processes[
                        campaign_type
                    ].values()
                ],
                "bucket_capacity": self.rate_limiter.peek(),
                "sending_rate": self.rate_meter.current_rate(),
            }
            self.stderr.write(self.STATS_MESSAGE % values, ending="\n\n")

    def start_sender_processes(self, campaign_type):
        sender_processes = self.sender_processes[campaign_type]
        queue = self.queue[campaign_type]

        for i in range(app_settings.MAX_CONCURRENT_SENDERS - len(sender_processes)):
            if i == 0:
                logger.info(f"\n{campaign_type.upper()}:")
            recv_conn, send_conn = mp.Pipe(duplex=False)
            process = mp.Process(
                target=CAMPAIGN_TYPE[campaign_type]["sender_process"],
                kwargs={
                    "queue": queue,
                    "error_channel": send_conn,
                    "rate_limiter": self.rate_limiter,
                    "rate_meter": self.rate_meter,
                    "quit_event": self.senders_quit_event,
                },
            )
            process.daemon = True

            sender_processes.append(process)
            self.sender_pipes[campaign_type].append(recv_conn)
            # let's close SQL connection to make sure it is not shared with children
            connection.close()
            with self._setup_signal_handlers_for_children():
                process.start()
            logger.info(
                _(
                    "Started sender process %(process_pid)s for %(campaign_type)s campaigns"
                )
                % {"process_pid": process.pid, "campaign_type": campaign_type}
            )

    def check_campaigns(self, campaign_type):
        CampaignModel = CAMPAIGN_TYPE[campaign_type]["CampaignModel"]
        campaigns = CampaignModel.objects.outbox()
        campaign_manager_process = self.campaign_manager_processes[campaign_type]
        queue = self.queue[campaign_type]

        for campaign in campaigns:
            if (
                campaign.status == CampaignModel.STATUS_WAITING
                and campaign.id in campaign_manager_process
            ):
                # we need to cancel that task
                logger.info(
                    _(
                        "Stopping campaign manager n°%(campaign_id)s (%(campaign_name)s)..."
                    )
                    % {"campaign_id": campaign.id, "campaign_name": campaign.name[20:]}
                )
                _process, quit_event = campaign_manager_process[campaign.id]
                quit_event.set()

            if (
                campaign.status == CampaignModel.STATUS_SENDING
                and campaign.id not in campaign_manager_process
            ):
                quit_event = mp.Event()
                process = mp.Process(
                    target=CAMPAIGN_TYPE[campaign_type]["manager_process"],
                    kwargs={
                        "campaign": campaign,
                        "queue": queue,
                        "quit_event": quit_event,
                    },
                )
                process.daemon = True
                campaign_manager_process[campaign.id] = (process, quit_event)
                # let's close SQL connection to make sure it is not shared with children
                connection.close()
                with self._setup_signal_handlers_for_children():
                    process.start()
                logger.info(
                    _(
                        "Started %(campaign_type)s campaign manager %(process_pid)s for %(campaign)s"
                    )
                    % {
                        "campaign_type": campaign_type,
                        "process_pid": process.pid,
                        "campaign": repr(campaign),
                    }
                )

    def monitor_processes(self, campaign_type):
        CampaignModel = CAMPAIGN_TYPE[campaign_type]["CampaignModel"]
        sender_processes = self.sender_processes[campaign_type]
        campaign_manager_process = self.campaign_manager_processes[campaign_type]
        sender_pipes = self.sender_pipes[campaign_type]

        sender_sentinels = [p.sentinel for p in sender_processes]
        campaign_manager_sentinels = {
            p.sentinel: c_id for c_id, (p, _e) in campaign_manager_process.items()
        }

        events = mpc.wait(
            sender_sentinels + list(campaign_manager_sentinels) + sender_pipes,
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
            elif event in sender_pipes:
                while event.poll():
                    try:
                        campaign_errors.add(event.recv())
                    except EOFError:
                        break

        # reverse=True is important as we're removing elements from the sender_processes list by index
        for i in sorted(stopped_senders, reverse=True):
            process = sender_processes[i]
            # let's reap process to avoid zombies
            process.join()

            logger.error(
                _("Sender process %(process_pid)s unexpectedly quit...")
                % {"process_pid": process.pid}
            )
            del sender_processes[i]
            del sender_pipes[i]

        for campaign_id in sorted(stopped_campaign_managers):
            process, _quit_event = campaign_manager_process[campaign_id]
            pid = process.pid
            # let's reap process to avoid zombies
            process.join()

            try:
                campaign = CampaignModel.objects.get(id=campaign_id)
            except CampaignModel.DoesNotExist:
                # the campaign has most likely be deleted
                campaign = None

            if campaign and campaign.status != CampaignModel.STATUS_SENDING:
                # process was asked to stop and did so correctly
                logger.info(
                    _(
                        "Campaign manager %(pid)s correctly stopped... Was taking care of %(campaign)s."
                    )
                    % {"pid": pid, "campaign": repr(campaign)},
                    exc_info=True,
                )
            else:
                logger.error(
                    _(
                        "Campaign manager %(pid)s abruptly stops. Was taking care of %(campaign)s."
                    )
                    % {"pid": pid, "campaign": repr(campaign)},
                    exc_info=True,
                )

            del campaign_manager_process[campaign_id]

        for campaign_id in campaign_errors:
            CampaignModel.objects.filter(id=campaign_id).update(
                status=CampaignModel.STATUS_ERROR
            )
            if campaign_id in campaign_manager_process:
                logger.error(
                    _(
                        "Unexpected error while trying to send message from campaign %(campaign_id)s...\n"
                    )
                    % {"campaign_id": campaign_id}
                )
                campaign_manager_process[campaign_id][1].set()

    def run_loop(self, campaign_types):
        try:
            while True:
                for campaign_type in campaign_types:
                    self.start_sender_processes(campaign_type)
                    self.check_campaigns(campaign_type)
                    self.monitor_processes(campaign_type)

        except (GracefulExit, KeyboardInterrupt):
            logger.info(_("Asked to quit, asking all subprocesses to exit..."))
            self.senders_quit_event.set()

            for campaign_type in campaign_types:
                for _proces, event in self.campaign_manager_processes[
                    campaign_type
                ].values():
                    event.set()

            logger.info(_("Waiting for all subprocesses to gracefully exit..."))
            # active_children joins children so removes zombies
            for campaign_type in campaign_types:
                while mp.active_children():
                    sender_processes = sum(self.sender_processes.values(), [])
                    mpc.wait(
                        [p.sentinel for p in sender_processes]
                        + [
                            p.sentinel
                            for p, _e in self.campaign_manager_processes[
                                campaign_type
                            ].values()
                        ]
                    )

            logger.info(_("All subprocesses have exited!"))
