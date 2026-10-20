"""Decide whether cached data is fresh, stale or unavailable — and say why.

No exchange-holiday calendar is bundled (NSE publishes it yearly and it changes). Instead:
  * the *expected* latest session is the most recent weekday whose data should be out by now
    (prices after `refresh_time_ist`, NAVs after `nav_refresh_time_ist`);
  * a series is fresh if we fetched it after that point and the source's last bar is within
    `max_missing_sessions` weekdays of it. On a holiday the source simply has nothing newer,
    which this tolerates; a suspended stock lags further and gets flagged.
"""

from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from typing import TYPE_CHECKING, Literal

from app.core.formatting import IST, format_freshness

if TYPE_CHECKING:
    from app.models.tables import SeriesStatus

Status = Literal["fresh", "stale", "unavailable"]


@dataclass(frozen=True)
class Freshness:
    status: Status
    reason: str


def as_utc(ts: datetime) -> datetime:
    """SQLite hands back naive datetimes; they are UTC."""
    return ts.replace(tzinfo=UTC) if ts.tzinfo is None else ts.astimezone(UTC)


def failed_lately(st: "SeriesStatus", now: datetime, within: timedelta | None) -> bool:
    """The last download attempt failed less than `within` ago (never, when `within` is None)."""
    at = st.last_attempt_at
    return bool(within and st.last_error and at and now - as_utc(at) < within)


def fmt_date(d: date) -> str:
    return f"{d:%d %b %Y}"


def expected_session(now: datetime, ready: time) -> date:
    """Latest weekday whose data should be published by `now` (IST)."""
    local = now.astimezone(IST)
    d = local.date()
    if d.weekday() < 5 and local.time() >= ready:
        return d
    d -= timedelta(days=1)
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d


def ready_at(session: date, ready: time) -> datetime:
    return datetime.combine(session, ready, tzinfo=IST)


def missing_sessions(last: date, expected: date) -> int:
    """Weekdays in (last, expected]."""
    if last >= expected:
        return 0
    n, d = 0, last + timedelta(days=1)
    while d <= expected:
        n += d.weekday() < 5
        d += timedelta(days=1)
    return n


def assess_series(
    *,
    last_date: date | None,
    last_success_at: datetime | None,
    last_error: str | None,
    now: datetime,
    ready: time,
    stale_after_hours: float,
    max_missing: int,
) -> Freshness:
    """Freshness of a daily series (stock prices or NAVs)."""
    if last_date is None:
        if last_error:
            return Freshness("unavailable", f"No data. Last attempt failed: {last_error}")
        return Freshness("unavailable", "Not downloaded yet")
    expected = expected_session(now, ready)
    suffix = f" Last attempt failed: {last_error}" if last_error else ""
    if last_success_at is None:
        return Freshness("stale", f"Data from {fmt_date(last_date)}, never refreshed.{suffix}")
    ok_at = as_utc(last_success_at)
    if now - ok_at > timedelta(hours=stale_after_hours):
        return Freshness(
            "stale",
            f"Not refreshed since {format_freshness(ok_at)} "
            f"(latest {fmt_date(last_date)}).{suffix}",
        )
    if ok_at < ready_at(expected, ready) and last_date < expected:
        return Freshness(
            "stale",
            f"Latest is {fmt_date(last_date)}; data for {fmt_date(expected)} "
            f"should be out now.{suffix}",
        )
    lag = missing_sessions(last_date, expected)
    if lag > max_missing:
        return Freshness(
            "stale",
            f"Source has nothing after {fmt_date(last_date)} ({lag} weekdays behind); "
            "it may be suspended, delisted or renamed.",
        )
    return Freshness("fresh", f"Up to date (latest {fmt_date(last_date)})." + suffix)


def assess_age(
    *,
    last_success_at: datetime | None,
    last_error: str | None,
    now: datetime,
    max_age: timedelta,
    what: str,
) -> Freshness:
    """Freshness by age alone (intraday bars, reference lists)."""
    if last_success_at is None:
        if last_error:
            return Freshness("unavailable", f"No {what}. Last attempt failed: {last_error}")
        return Freshness("unavailable", f"No {what} downloaded yet")
    ok_at = as_utc(last_success_at)
    suffix = f" Last attempt failed: {last_error}" if last_error else ""
    if now - ok_at > max_age:
        return Freshness("stale", f"{what.capitalize()} from {format_freshness(ok_at)}.{suffix}")
    return Freshness("fresh", f"{what.capitalize()} from {format_freshness(ok_at)}." + suffix)
