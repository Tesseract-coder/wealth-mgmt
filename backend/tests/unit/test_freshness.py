from datetime import UTC, date, datetime, time, timedelta

from app.core.formatting import IST
from app.data.freshness import assess_age, assess_series, expected_session, missing_sessions

READY = time(16, 0)


def ist(y: int, m: int, d: int, hh: int = 12, mm: int = 0) -> datetime:
    return datetime(y, m, d, hh, mm, tzinfo=IST)


def test_expected_session_respects_ready_time_and_weekends() -> None:
    assert expected_session(ist(2026, 10, 9, 17), READY) == date(2026, 10, 9)  # Fri after 16:00
    assert expected_session(ist(2026, 10, 9, 10), READY) == date(2026, 10, 8)  # Fri morning
    assert expected_session(ist(2026, 10, 10), READY) == date(2026, 10, 9)  # Saturday
    assert expected_session(ist(2026, 10, 12, 9), READY) == date(2026, 10, 9)  # Monday morning
    # A UTC timestamp is converted: 11:00 UTC = 16:30 IST.
    assert expected_session(datetime(2026, 10, 9, 11, tzinfo=UTC), READY) == date(2026, 10, 9)


def test_missing_sessions_counts_weekdays_only() -> None:
    assert missing_sessions(date(2026, 10, 9), date(2026, 10, 9)) == 0
    assert missing_sessions(date(2026, 10, 9), date(2026, 10, 12)) == 1  # Fri → Mon
    assert missing_sessions(date(2026, 10, 5), date(2026, 10, 9)) == 4


def _assess(last_date: date | None, ok_at: datetime | None, now: datetime, err: str | None = None):
    return assess_series(
        last_date=last_date,
        last_success_at=ok_at,
        last_error=err,
        now=now,
        ready=READY,
        stale_after_hours=24,
        max_missing=2,
    )


def test_unavailable_when_no_data() -> None:
    now = ist(2026, 10, 9, 17)
    assert _assess(None, None, now).status == "unavailable"
    f = _assess(None, None, now, err="HTTP 503")
    assert f.status == "unavailable" and "HTTP 503" in f.reason


def test_fresh_after_fetching_the_expected_session() -> None:
    now = ist(2026, 10, 9, 17)
    f = _assess(date(2026, 10, 9), ist(2026, 10, 9, 16, 30), now)
    assert f.status == "fresh" and "09 Oct 2026" in f.reason


def test_stale_when_a_newer_session_should_exist() -> None:
    # Fetched Friday at 15:00 (before the cut-off); now it's 17:00 and Friday's bar should be out.
    f = _assess(date(2026, 10, 8), ist(2026, 10, 9, 15), ist(2026, 10, 9, 17))
    assert f.status == "stale" and "should be out" in f.reason


def test_holiday_tolerated_when_we_asked_after_the_cut_off() -> None:
    # 2 Oct 2026 (Fri) was a market holiday: asked after 16:00, the source's latest is Thursday.
    f = _assess(date(2026, 10, 1), ist(2026, 10, 2, 16, 30), ist(2026, 10, 2, 18))
    assert f.status == "fresh"


def test_stale_when_source_lags_too_far() -> None:
    f = _assess(date(2026, 10, 1), ist(2026, 10, 9, 16, 30), ist(2026, 10, 9, 17))
    assert f.status == "stale" and "suspended" in f.reason


def test_stale_by_age_and_error_is_surfaced() -> None:
    now = ist(2026, 10, 9, 17)
    f = _assess(date(2026, 10, 6), now - timedelta(hours=72), now, err="timeout")
    assert f.status == "stale" and "timeout" in f.reason


def test_naive_success_time_is_treated_as_utc() -> None:
    now = ist(2026, 10, 9, 17)
    naive_utc = datetime(2026, 10, 9, 11, 0)  # 16:30 IST, how SQLite returns it
    assert _assess(date(2026, 10, 9), naive_utc, now).status == "fresh"


def test_assess_age() -> None:
    now = ist(2026, 10, 9, 17)
    kw = {"now": now, "max_age": timedelta(minutes=15), "what": "bars"}
    assert assess_age(last_success_at=None, last_error=None, **kw).status == "unavailable"
    assert (
        assess_age(last_success_at=now - timedelta(minutes=5), last_error=None, **kw).status
        == "fresh"
    )
    assert (
        assess_age(last_success_at=now - timedelta(hours=1), last_error=None, **kw).status
        == "stale"
    )
