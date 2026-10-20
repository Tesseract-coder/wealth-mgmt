import threading
from datetime import timedelta

from sqlmodel import Session

from app.core import memo
from app.core.memo import Memo
from app.models.tables import UserProfile


def test_result_is_shared_until_an_input_is_written(session: Session) -> None:
    m: Memo[int] = Memo("test", timedelta(minutes=5))
    runs: list[int] = []

    def build(_: Session) -> int:
        runs.append(1)
        return len(runs)

    assert m.get(session, "k", build) == 1
    assert m.get(session, "k", build) == 1
    assert m.get(session, "other", build) == 2
    session.add(UserProfile(id=1))
    session.commit()  # an analysis input changed
    assert m.get(session, "k", build) == 3


def test_aged_result_is_served_while_rebuilt_in_background(session: Session) -> None:
    m: Memo[int] = Memo("test", timedelta(minutes=5), stale_for=timedelta(hours=1))
    built = threading.Event()
    runs: list[int] = []

    def build(_: Session) -> int:
        runs.append(1)
        if len(runs) > 1:
            built.set()
        return len(runs)

    assert m.get(session, "k", build) == 1
    full = next(iter(m._cache))
    v, at, value = m._cache[full]
    m._cache[full] = (v, at - timedelta(minutes=10), value)  # aged out, same data
    assert m.get(session, "k", build) == 1  # the old result, straight away
    assert built.wait(5)
    with m._key_locks[full]:  # the rebuild has finished
        pass
    assert m.get(session, "k", build) == 2
    m._cache[full] = (v, at - timedelta(hours=2), m._cache[full][2])  # too old to serve
    assert m.get(session, "k", build) == 3
    memo.clear_memos()
    assert m._cache == {}
