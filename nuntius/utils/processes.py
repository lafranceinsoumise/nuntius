import contextlib
import logging
import multiprocessing as mp
import signal
import time
import traceback
from ctypes import c_double, c_ulong
from queue import Empty, Full

logger = logging.getLogger(__name__)


class GracefulExit(Exception):
    pass


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


def unexpected_exc_logger(proc):
    """
    Decorator that intercepts exception and prints them
    :param proc:
    :return:
    """

    @contextlib.wraps(proc)
    def wrapper(*args, **kwargs):
        try:
            return proc(*args, **kwargs)
        except Exception:
            logger.exception("Unexpected error.")
            raise

    return wrapper


def reset_sigmask(proc):
    """
    Decorator that sets an empty sigmask when the function is called
    """

    @contextlib.wraps(proc)
    def wrapper(*args, **kwargs):
        signal.pthread_sigmask(signal.SIG_SETMASK, [])
        return proc(*args, **kwargs)

    return wrapper


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
        self._var_lock = mp.RLock()
        self._wait_lock = mp.RLock()
        self._timestamp = mp.Value(c_double, lock=False)
        self._timestamp.value = time.monotonic()
        self._capacity = mp.Value(c_double, lock=False)
        self._capacity.value = self.max

    def _update(self):
        with self._var_lock:
            now = _current_time()
            self._capacity.value = min(
                self._capacity.value + self.rate * (now - self._timestamp.value),
                self.max,
            )
            self._timestamp.value = now

    def take(self, n=1):
        """
        Try to take a token, or wait for the bucket to fill in enough.

        If several processes take at the same time, the first one to call will takes
        a lock and will be guaranteed to be unblocked first. No such guarantee exists
        for the other processes.
        """
        with self._wait_lock:
            with self._var_lock:
                self._update()
                self._capacity.value -= n
                capacity = self._capacity.value

            if capacity < 0:
                time.sleep(-self._capacity.value / self.rate)

    def peek(self):
        with self._var_lock:
            self._update()
            return self._capacity.value


class RateMeter:
    def __init__(self, alpha: float, window: float):
        self._alpha = alpha
        self._window = window
        self._lock = mp.RLock()
        self._current_rate = mp.Value(c_double, 0, lock=False)
        self._last_window = mp.Value(
            c_ulong, int(_current_time() / self._window), lock=False
        )
        self._current_counter = mp.Value(c_ulong, 0, lock=False)

    def _update(self):
        with self._lock:
            current_window = int(_current_time() / self._window)
            if current_window > self._last_window.value:
                time_diff = current_window - self._last_window.value
                alpha, beta = self._alpha, 1 - self._alpha
                self._current_rate.value = beta ** (time_diff - 1) * (
                    beta * self._current_rate.value
                    + alpha * (self._current_counter.value / self._window)
                )
                self._current_counter.value = 0
                self._last_window.value = current_window

    def count_up(self, n=1):
        with self._lock:
            self._update()
            self._current_counter.value += n

    def current_rate(self):
        with self._lock:
            return self._current_rate.value


def get_from_queue_or_quit(queue: mp.Queue, event: mp.Event, polling_period: float):
    while True:
        if event.is_set():
            raise GracefulExit()
        try:
            return queue.get(timeout=polling_period)
        except Empty:
            pass


def put_in_queue_or_quit(
    queue: mp.Queue, value, event: mp.Event, polling_period: float
):
    while True:
        if event.is_set():
            raise GracefulExit()
        try:
            return queue.put(value, timeout=polling_period)
        except Full:
            pass
