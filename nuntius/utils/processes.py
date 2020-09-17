import contextlib
import multiprocessing as mp
import signal
import time
import traceback
from ctypes import c_double

from nuntius.management.commands.nuntius_worker import GracefulExit


def _current_time():
    """Returns monotonic current time in seconds.

    Splitted off in function to increase testability.

    :return: current time in seconds, guaranteed monotonic
    """
    return time.monotonic()


def gracefully_exit(sig, stack):
    """
    Signal handler that raises a GracefulExit exception

    :raise: :class:`nuntius.synchronize.GracefulExit`
    """
    raise GracefulExit()


def print_stack_trace(sig, stack):
    """
    Signal handler that prints the current track before resuming process
    """
    traceback.print_stack(stack)


def reset_sigmask(proc):
    """
    Decorator that sets an empty sigmask when the function is called
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

    def _update(self):
        with self.lock:
            now = _current_time()
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
