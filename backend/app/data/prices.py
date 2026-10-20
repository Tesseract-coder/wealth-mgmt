"""Daily and intraday prices: incremental refresh into SQLite, split detection, resampling."""

import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Literal

import pandas as pd
from sqlmodel import Session

from app.core.formatting import IST, now_ist
from app.core.profiles import get_profiles
from app.data import store, yahoo
from app.data.freshness import (
    Freshness,
    assess_age,
    assess_series,
    expected_session,
    failed_lately,
)
from app.data.http import FetchError
from app.data.store import RefreshResult
from app.models.tables import SeriesStatus

logger = logging.getLogger(__name__)

DailyInterval = Literal["1d", "1wk", "1mo"]
IntradayInterval = Literal["15m", "1h"]


def price_key(ticker: str) -> str:
    return f"price:{ticker}"


def intraday_key(ticker: str, interval: str) -> str:
    return f"intraday:{ticker}:{interval}"


def daily_freshness(st: SeriesStatus | None, now: datetime) -> Freshness:
    cfg = get_profiles().data
    return assess_series(
        last_date=st.last_date if st else None,
        last_success_at=st.last_success_at if st else None,
        last_error=st.last_error if st else None,
        now=now,
        ready=cfg.price_ready,
        stale_after_hours=cfg.stale_after_hours,
        max_missing=cfg.max_missing_sessions,
    )


def history_start(now: datetime) -> date:
    return now.astimezone(IST).date() - timedelta(
        days=365 * get_profiles().data.price_history_years
    )


def _drop_unfinished(df: pd.DataFrame, now: datetime) -> pd.DataFrame:
    """Keep only sessions whose bar is final (today's counts only after refresh_time_ist)."""
    last_final = expected_session(now, get_profiles().data.price_ready)
    return df[[d <= last_final for d in df.index]]


def _split_suspected(session: Session, ticker: str, fresh: pd.DataFrame) -> bool:
    """Yahoo back-adjusts history after a split/bonus; overlapping closes then disagree."""
    stored = store.read_daily(session, ticker, start=min(fresh.index))
    both = stored[["close"]].join(fresh[["close"]], rsuffix="_new", how="inner")
    if both.empty:
        return False
    drift = ((both["close_new"] - both["close"]).abs() / both["close"]).max()
    return bool(drift > get_profiles().data.split_check_tolerance)


def refresh_daily(
    session: Session,
    ticker: str,
    label: str | None = None,
    *,
    force: bool = False,
    retry_failed_after: timedelta | None = None,
    now: datetime | None = None,
) -> RefreshResult:
    now = now or now_ist()
    key = price_key(ticker)
    st = store.status_row(session, key, "price", "yahoo", label)
    label = st.label or ticker
    if not force and daily_freshness(st, now).status == "fresh":
        return RefreshResult(key, label, "skipped", "Already up to date")
    if failed_lately(st, now, retry_failed_after):
        return RefreshResult(key, label, "failed", st.last_error or "Last download failed")

    want_from = history_start(now)
    full = st.last_date is None or st.history_from is None or st.history_from > want_from
    start = want_from
    if not full and st.last_date is not None:
        start = st.last_date - timedelta(days=get_profiles().data.incremental_overlap_days)
    st.last_attempt_at = store.to_utc(now)
    try:
        df = _drop_unfinished(yahoo.fetch_daily(ticker, start), now)
        if not full and not df.empty and _split_suspected(session, ticker, df):
            logger.info("%s: price history changed (split/bonus?); re-downloading", ticker)
            store.delete_daily(session, ticker)
            full, start = True, want_from
            df = _drop_unfinished(yahoo.fetch_daily(ticker, start), now)
    except FetchError as e:
        st.last_error = str(e)
        session.commit()
        return RefreshResult(key, label, "failed", str(e))

    store.upsert_daily(session, ticker, df)
    st.first_date, st.last_date, st.rows = store.daily_extent(session, ticker)
    st.history_from = want_from if full else min(st.history_from or want_from, want_from)
    st.last_success_at, st.last_error = store.to_utc(now), None
    session.commit()
    note = "full history" if full else "incremental"
    return RefreshResult(key, label, "updated", f"{len(df)} bars ({note})", len(df))


@dataclass
class Bars:
    ticker: str
    interval: str
    frame: pd.DataFrame
    last_complete: bool  # False when the final weekly/monthly bar covers an unfinished period
    freshness: Freshness


def resample(
    df: pd.DataFrame, interval: DailyInterval, expected: date
) -> tuple[pd.DataFrame, bool]:
    """Aggregate daily bars into weekly (Mon–Fri) or monthly bars, labelled by last session."""
    if interval == "1d" or df.empty:
        return df, True
    freq = "W-FRI" if interval == "1wk" else "M"
    periods = pd.DatetimeIndex(pd.to_datetime(df.index)).to_period(freq)
    grouped = df.assign(_date=list(df.index)).groupby(periods)
    out = grouped.agg(
        open=("open", "first"),
        high=("high", "max"),
        low=("low", "min"),
        close=("close", "last"),
        adj_close=("adj_close", "last"),
        volume=("volume", "sum"),
        _date=("_date", "last"),
    )
    last_period_end = out.index[-1].end_time.date()
    complete = expected >= last_period_end
    out.index = pd.Index(out.pop("_date"), name="date")
    return out, complete


def get_daily(
    session: Session,
    ticker: str,
    interval: DailyInterval = "1d",
    start: date | None = None,
    now: datetime | None = None,
) -> Bars:
    now = now or now_ist()
    df = store.read_daily(session, ticker, start)
    expected = expected_session(now, get_profiles().data.price_ready)
    frame, complete = resample(df, interval, expected)
    st = store.get_status(session, price_key(ticker))
    return Bars(ticker, interval, frame, complete, daily_freshness(st, now))


def intraday_freshness(st: SeriesStatus | None, now: datetime) -> Freshness:
    return assess_age(
        last_success_at=st.last_success_at if st else None,
        last_error=st.last_error if st else None,
        now=now,
        max_age=timedelta(minutes=get_profiles().data.intraday_stale_after_minutes),
        what="delayed intraday bars",
    )


def refresh_intraday(
    session: Session,
    ticker: str,
    interval: IntradayInterval,
    label: str | None = None,
    *,
    force: bool = False,
    retry_failed_after: timedelta | None = None,
    now: datetime | None = None,
) -> RefreshResult:
    now = now or now_ist()
    key = intraday_key(ticker, interval)
    st = store.status_row(session, key, "intraday", "yahoo", label)
    label = st.label or ticker
    if not force and intraday_freshness(st, now).status == "fresh":
        return RefreshResult(key, label, "skipped", "Already up to date")
    if failed_lately(st, now, retry_failed_after):
        return RefreshResult(key, label, "failed", st.last_error or "Last download failed")
    st.last_attempt_at = store.to_utc(now)
    try:
        df = yahoo.fetch_intraday(ticker, interval, get_profiles().data.intraday_max_days[interval])
    except FetchError as e:
        st.last_error = str(e)
        session.commit()
        return RefreshResult(key, label, "failed", str(e))
    store.replace_intraday(session, ticker, interval, df)
    st.rows = len(df)
    st.first_date = df.index[0].date() if len(df) else None
    st.last_date = df.index[-1].date() if len(df) else None
    st.last_success_at, st.last_error = store.to_utc(now), None
    session.commit()
    return RefreshResult(key, label, "updated", f"{len(df)} bars", len(df))


def get_intraday(
    session: Session, ticker: str, interval: IntradayInterval, now: datetime | None = None
) -> Bars:
    now = now or now_ist()
    st = store.get_status(session, intraday_key(ticker, interval))
    frame = store.read_intraday(session, ticker, interval)
    return Bars(ticker, interval, frame, True, intraday_freshness(st, now))
