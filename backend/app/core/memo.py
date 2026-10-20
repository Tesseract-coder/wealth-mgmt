"""Results shared between requests until an analysis input changes.

A cached result is reused while nothing has been written to an analysis input (see
`db.write_version`) and it is younger than `max_age` (freshness labels depend on the time of
day). Requests that arrive while a result is being built wait for it instead of building it
again. With `stale_for`, a result that has only aged out (the data hasn't changed) is still
returned for that long while a fresh one is built in the background, so a page that sat idle
doesn't wait for the whole analysis again.
"""

import logging
import threading
from collections.abc import Callable, Hashable
from datetime import datetime, timedelta
from typing import Generic, TypeVar

from sqlmodel import Session

from app.core.db import write_version
from app.core.formatting import now_ist
from app.core.profiles import get_profiles

logger = logging.getLogger(__name__)

T = TypeVar("T")

_memos: list["Memo[object]"] = []


class Memo(Generic[T]):
    def __init__(
        self,
        name: str,
        max_age: timedelta,
        *,
        stale_for: timedelta | None = None,
        size: int = 16,
    ) -> None:
        self.name, self.max_age, self.stale_for, self.size = name, max_age, stale_for, size
        self._lock = threading.Lock()
        self._key_locks: dict[Hashable, threading.Lock] = {}
        self._cache: dict[Hashable, tuple[int, datetime, T]] = {}
        _memos.append(self)  # type: ignore[arg-type]

    def get(self, session: Session, key: Hashable, compute: Callable[[Session], T]) -> T:
        """The cached result for `key`, else `compute(session)` (stored for later requests).

        `compute` may run in a background thread with a session of its own, so it must use
        the session it is given, never one captured from the request."""
        bind = session.get_bind()
        # Results from another database (tests) or another profiles.yaml load never mix.
        full = (id(bind), id(get_profiles()), key)
        with self._lock:
            key_lock = self._key_locks.setdefault(full, threading.Lock())
            hit = self._cache.get(full)
        if hit and hit[0] == write_version():
            age = now_ist() - hit[1]
            if age < self.max_age:
                return hit[2]
            if self.stale_for is not None and age < self.max_age + self.stale_for:
                self._revalidate(full, key_lock, bind, compute)
                return hit[2]
        with key_lock:
            hit = self._cache.get(full)
            if hit and hit[0] == write_version() and now_ist() - hit[1] < self.max_age:
                return hit[2]
            return self._build(full, session, compute)

    def _build(self, full: Hashable, session: Session, compute: Callable[[Session], T]) -> T:
        version, started = write_version(), now_ist()
        value = compute(session)
        with self._lock:
            # Stamped with the version from before the run: a write during it makes this stale.
            self._cache[full] = (version, started, value)
            while len(self._cache) > self.size:
                old = next(iter(self._cache))
                del self._cache[old]
                self._key_locks.pop(old, None)
        return value

    def _revalidate(
        self,
        full: Hashable,
        key_lock: threading.Lock,
        bind: object,
        compute: Callable[[Session], T],
    ) -> None:
        if not key_lock.acquire(blocking=False):
            return  # already being rebuilt

        def run() -> None:
            try:
                with Session(bind) as s:  # type: ignore[arg-type]
                    self._build(full, s, compute)
            except Exception:
                logger.exception("Couldn't rebuild the cached %s", self.name)
            finally:
                key_lock.release()

        try:
            threading.Thread(target=run, name=f"memo-{self.name}", daemon=True).start()
        except Exception:
            key_lock.release()
            raise

    def clear(self) -> None:
        with self._lock:
            self._cache.clear()


def clear_memos() -> None:
    """Drop every cached result (tests, or after changing data outside this process)."""
    for m in _memos:
        m.clear()
