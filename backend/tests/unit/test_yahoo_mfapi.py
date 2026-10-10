import json
from datetime import date

import numpy as np
import pandas as pd
import pytest

from app.data import yahoo
from app.data.http import FetchError
from app.data.mfapi import parse_nav_history
from tests.conftest import yf_frame


def test_yahoo_ticker() -> None:
    assert yahoo.yahoo_ticker("RELIANCE", "NSE") == "RELIANCE.NS"
    assert yahoo.yahoo_ticker("M&M", None) == "M&M.NS"
    assert yahoo.yahoo_ticker("TCS", "BSE") == "TCS.BO"


def test_fetch_daily_uses_exchange_local_dates(monkeypatch: pytest.MonkeyPatch) -> None:
    frame = yf_frame(date(2026, 10, 5), date(2026, 10, 9))
    frame.iloc[2, frame.columns.get_loc("Close")] = np.nan  # a bad bar is dropped, not filled
    monkeypatch.setattr(yahoo, "_download", lambda *a, **k: frame)
    df = yahoo.fetch_daily("X.NS", date(2026, 10, 5))
    assert list(df.columns) == ["open", "high", "low", "close", "adj_close", "volume"]
    # midnight IST is the previous day in UTC; the stored date must be the IST session date
    assert list(df.index) == [
        date(2026, 10, 5),
        date(2026, 10, 6),
        date(2026, 10, 8),
        date(2026, 10, 9),
    ]


def test_fetch_daily_empty_is_an_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(yahoo, "_download", lambda *a, **k: pd.DataFrame())
    with pytest.raises(FetchError, match="no 1d data"):
        yahoo.fetch_daily("NOPE.NS", date(2026, 1, 1))


def test_fetch_retries_exceptions_then_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = []

    def boom(*a: object, **k: object) -> pd.DataFrame:
        calls.append(1)
        raise ConnectionError("reset")

    monkeypatch.setattr(yahoo, "_download", boom)
    with pytest.raises(FetchError, match="reset"):
        yahoo.fetch_daily("X.NS", date(2026, 1, 1))
    assert len(calls) == 4  # 1 + http_retries


def test_fetch_retry_recovers(monkeypatch: pytest.MonkeyPatch) -> None:
    frame = yf_frame(date(2026, 10, 5), date(2026, 10, 9))
    answers = [ConnectionError("x"), frame]

    def flaky(*a: object, **k: object) -> pd.DataFrame:
        a0 = answers.pop(0)
        if isinstance(a0, Exception):
            raise a0
        return a0

    monkeypatch.setattr(yahoo, "_download", flaky)
    assert len(yahoo.fetch_daily("X.NS", date(2026, 10, 5))) == 5


def test_fetch_intraday_index_is_utc(monkeypatch: pytest.MonkeyPatch) -> None:
    idx = pd.DatetimeIndex(["2026-10-09 09:15", "2026-10-09 09:30"]).tz_localize("Asia/Kolkata")
    frame = pd.DataFrame(
        {
            "Open": [1.0, 2.0],
            "High": [1, 2],
            "Low": [1, 2],
            "Close": [1.5, 2.5],
            "Volume": [10, 20],
        },
        index=idx,
    )
    monkeypatch.setattr(yahoo, "_download", lambda *a, **k: frame)
    df = yahoo.fetch_intraday("X.NS", "15m", 5)
    assert str(df.index.tz) == "UTC"
    assert df.index[0] == pd.Timestamp("2026-10-09 03:45", tz="UTC")


def _payload(code: str = "118989", rows: object = None, status: str = "SUCCESS") -> bytes:
    data = (
        rows
        if rows is not None
        else [
            {"date": "09-10-2026", "nav": "219.81600"},
            {"date": "08-10-2026", "nav": "217.07800"},
        ]
    )
    return json.dumps(
        {
            "meta": {"scheme_code": int(code), "scheme_name": "HDFC Mid Cap"},
            "data": data,
            "status": status,
        }
    ).encode()


def test_parse_nav_history_sorted_ascending() -> None:
    h = parse_nav_history("118989", _payload())
    assert h.scheme_name == "HDFC Mid Cap"
    assert h.points == [(date(2026, 10, 8), 217.078), (date(2026, 10, 9), 219.816)]


def test_parse_nav_history_skips_malformed_rows() -> None:
    rows = [
        {"date": "09-10-2026", "nav": "N.A."},
        {"date": "bad", "nav": "1"},
        {"date": "08-10-2026", "nav": "10"},
    ]
    assert parse_nav_history("118989", _payload(rows=rows)).points == [(date(2026, 10, 8), 10.0)]


@pytest.mark.parametrize(
    ("payload", "match"),
    [
        (b"<html>", "not JSON"),
        (_payload(status="FAIL"), "no NAV history"),
        (_payload(code="100000"), "asked for scheme 118989"),
        (_payload(rows=[]), "no usable NAV rows"),
    ],
)
def test_parse_nav_history_errors(payload: bytes, match: str) -> None:
    with pytest.raises(FetchError, match=match):
        parse_nav_history("118989", payload)
