import json
from datetime import date, datetime, timedelta

import httpx
import pandas as pd
import pytest
from sqlmodel import Session

from app.core.formatting import IST
from app.data import http, store, yahoo
from app.data.navs import latest_nav, refresh_nav
from app.data.prices import get_daily, history_start, price_key, refresh_daily, resample
from tests.conftest import FRI_EVENING, yf_frame


class FakeYahoo:
    """Serves yf_frame() bars from the requested start up to `last`."""

    def __init__(self, last: date, factor: float = 1.0) -> None:
        self.last, self.factor = last, factor
        self.starts: list[date] = []

    def __call__(
        self, ticker: str, *, interval: str, start: date | None = None, period: str | None = None
    ) -> pd.DataFrame:
        assert start is not None
        self.starts.append(start)
        return yf_frame(start, self.last, factor=self.factor)


def test_first_refresh_downloads_full_history_then_skips(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = FakeYahoo(date(2026, 10, 9))
    monkeypatch.setattr(yahoo, "_download", fake)
    r = refresh_daily(session, "ABC.NS", "ABC", now=FRI_EVENING)
    assert r.outcome == "updated" and "full history" in r.message
    assert fake.starts == [date(2021, 10, 10)]  # 5 years back
    st = store.get_status(session, price_key("ABC.NS"))
    assert st and st.last_date == date(2026, 10, 9) and st.rows > 1200 and st.last_error is None

    again = refresh_daily(session, "ABC.NS", "ABC", now=FRI_EVENING + timedelta(hours=1))
    assert again.outcome == "skipped" and len(fake.starts) == 1


def test_next_day_refresh_is_incremental(session: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(yahoo, "_download", FakeYahoo(date(2026, 10, 9)))
    refresh_daily(session, "ABC.NS", "ABC", now=FRI_EVENING)
    fake = FakeYahoo(date(2026, 10, 12))
    monkeypatch.setattr(yahoo, "_download", fake)
    monday = datetime(2026, 10, 12, 17, 0, tzinfo=IST)
    r = refresh_daily(session, "ABC.NS", "ABC", now=monday)
    assert r.outcome == "updated" and "incremental" in r.message
    assert fake.starts == [date(2026, 10, 2)]  # last bar minus 7 days of overlap
    assert store.get_status(session, price_key("ABC.NS")).last_date == date(2026, 10, 12)  # type: ignore[union-attr]


def test_split_triggers_full_redownload(session: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(yahoo, "_download", FakeYahoo(date(2026, 10, 9)))
    refresh_daily(session, "ABC.NS", "ABC", now=FRI_EVENING)
    # After a 1:2 split Yahoo back-adjusts every close to half.
    fake = FakeYahoo(date(2026, 10, 12), factor=0.5)
    monkeypatch.setattr(yahoo, "_download", fake)
    monday = datetime(2026, 10, 12, 17, 0, tzinfo=IST)
    refresh_daily(session, "ABC.NS", "ABC", now=monday)
    assert fake.starts == [date(2026, 10, 2), history_start(monday)]
    df = store.read_daily(session, "ABC.NS")
    first = df.index[0]
    expected_first = yf_frame(first, first, factor=0.5)["Close"].iloc[0]
    assert df["close"].iloc[0] == pytest.approx(expected_first)  # old unadjusted bars replaced


def test_unfinished_session_bar_is_not_stored(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(yahoo, "_download", FakeYahoo(date(2026, 10, 9)))
    during_market = datetime(2026, 10, 9, 11, 0, tzinfo=IST)
    refresh_daily(session, "ABC.NS", "ABC", now=during_market)
    assert store.get_status(session, price_key("ABC.NS")).last_date == date(2026, 10, 8)  # type: ignore[union-attr]


def test_failure_keeps_old_data_and_marks_stale(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(yahoo, "_download", FakeYahoo(date(2026, 10, 8)))
    refresh_daily(session, "ABC.NS", "ABC", now=datetime(2026, 10, 8, 17, tzinfo=IST))
    monkeypatch.setattr(yahoo, "_download", lambda *a, **k: pd.DataFrame())
    r = refresh_daily(session, "ABC.NS", "ABC", now=FRI_EVENING)
    assert r.outcome == "failed"
    bars = get_daily(session, "ABC.NS", now=FRI_EVENING)
    assert bars.frame.index[-1] == date(2026, 10, 8)
    assert bars.freshness.status == "stale" and "no 1d data" in bars.freshness.reason


def test_unknown_ticker_is_unavailable(session: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(yahoo, "_download", lambda *a, **k: pd.DataFrame())
    refresh_daily(session, "NOPE.NS", "NOPE", now=FRI_EVENING)
    bars = get_daily(session, "NOPE.NS", now=FRI_EVENING)
    assert bars.frame.empty and bars.freshness.status == "unavailable"


def _daily(start: date, end: date) -> pd.DataFrame:
    f = yf_frame(start, end)
    f.index = pd.Index([ts.date() for ts in f.index], name="date")
    return f.rename(columns=str.lower).rename(columns={"adj close": "adj_close"})


def test_resample_weekly_and_monthly() -> None:
    df = _daily(date(2026, 9, 28), date(2026, 10, 8))  # Mon 28 Sep .. Thu 8 Oct
    df = df.drop(date(2026, 10, 2))  # Gandhi Jayanti
    wk, complete = resample(df, "1wk", expected=date(2026, 10, 8))
    assert list(wk.index) == [date(2026, 10, 1), date(2026, 10, 8)]  # labelled by last session
    assert (
        wk["open"].iloc[0] == df["open"].iloc[0]
        and wk["close"].iloc[0] == df.loc[date(2026, 10, 1), "close"]
    )
    assert wk["volume"].iloc[0] == 4000 and not complete  # Friday 9 Oct not over yet
    _, complete = resample(df, "1wk", expected=date(2026, 10, 9))
    assert complete
    mo, complete = resample(df, "1mo", expected=date(2026, 10, 9))
    assert list(mo.index) == [date(2026, 9, 30), date(2026, 10, 8)] and not complete


def _mfapi(points: dict[str, str], code: str = "118989") -> None:
    payload = {
        "meta": {"scheme_code": int(code), "scheme_name": "HDFC Mid Cap Fund"},
        "status": "SUCCESS",
        "data": [{"date": d, "nav": v} for d, v in points.items()],
    }
    http.set_client(
        httpx.Client(
            transport=httpx.MockTransport(
                lambda r: httpx.Response(200, content=json.dumps(payload))
            )
        )
    )


def test_refresh_nav_and_latest(session: Session) -> None:
    _mfapi({"09-10-2026": "220.0", "08-10-2026": "200.0"})
    late = datetime(2026, 10, 9, 23, 45, tzinfo=IST)
    r = refresh_nav(session, "118989", "HDFC Mid", now=late)
    assert r.outcome == "updated"
    n = latest_nav(session, "118989", now=late)
    assert (n.nav, n.nav_date, n.previous_nav, n.source) == (
        220.0,
        date(2026, 10, 9),
        200.0,
        "mfapi",
    )
    assert n.freshness.status == "fresh"
    assert refresh_nav(session, "118989", "HDFC Mid", now=late).outcome == "skipped"


def test_latest_nav_prefers_newer_amfi_list(session: Session) -> None:
    # The bundled AMFI list has 118989 at 08 Oct 2026; mfapi here only up to 06 Oct.
    _mfapi({"06-10-2026": "1.0", "05-10-2026": "0.9"})
    refresh_nav(session, "118989", "HDFC Mid", now=FRI_EVENING)
    n = latest_nav(session, "118989", now=FRI_EVENING)
    assert n.source == "amfi" and n.nav_date == date(2026, 10, 8) and n.nav == 217.078
    assert n.previous_nav is None  # 06 Oct isn't the session before 08 Oct
    assert n.freshness.status == "stale"  # bundled list, never refreshed — says so


def test_latest_nav_unknown_scheme(session: Session) -> None:
    n = latest_nav(session, "999999999", now=FRI_EVENING)
    assert n.nav is None and n.freshness.status == "unavailable"


def test_failed_download_is_not_retried_on_page_loads(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[str] = []

    def empty(ticker: str, **_: object) -> pd.DataFrame:
        calls.append(ticker)
        return pd.DataFrame()

    monkeypatch.setattr(yahoo, "_download", empty)
    hour = timedelta(hours=1)
    assert refresh_daily(session, "NOPE.NS", now=FRI_EVENING, retry_failed_after=hour).outcome == (
        "failed"
    )
    n = len(calls)
    later = FRI_EVENING + timedelta(minutes=30)
    r = refresh_daily(session, "NOPE.NS", now=later, retry_failed_after=hour)
    assert r.outcome == "failed" and "no 1d data" in r.message
    assert len(calls) == n  # remembered: no second download
    refresh_daily(session, "NOPE.NS", now=later)  # refresh jobs always retry
    assert len(calls) > n
    n = len(calls)
    refresh_daily(session, "NOPE.NS", now=later + 2 * hour, retry_failed_after=hour)
    assert len(calls) > n  # tried again once the hour has passed
