"""Per-source request pacing so free data services are never hammered."""

import threading
import time
from collections.abc import Callable

from app.core.profiles import SourceKey, get_profiles


class RateLimiter:
    """Spaces calls at least 60/per_minute seconds apart. Thread-safe."""

    def __init__(
        self,
        per_minute: float,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.interval = 60.0 / per_minute
        self._clock = clock
        self._sleep = sleep
        self._next = 0.0
        self._lock = threading.Lock()

    def acquire(self) -> float:
        """Block until a request may be made. Returns the seconds waited."""
        with self._lock:
            now = self._clock()
            slot = max(now, self._next)
            self._next = slot + self.interval
        wait = slot - now
        if wait > 0:
            self._sleep(wait)
        return wait

    def penalise(self, seconds: float) -> None:
        """Push the next slot back, e.g. after the source answers HTTP 429."""
        with self._lock:
            self._next = max(self._next, self._clock() + seconds)


_limiters: dict[str, RateLimiter] = {}
_registry_lock = threading.Lock()


def limiter(source: SourceKey) -> RateLimiter:
    with _registry_lock:
        if source not in _limiters:
            _limiters[source] = RateLimiter(get_profiles().data.rate_limits_per_minute[source])
        return _limiters[source]


def reset_limiters() -> None:
    with _registry_lock:
        _limiters.clear()
