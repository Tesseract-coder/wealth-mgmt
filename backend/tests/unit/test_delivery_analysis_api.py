from datetime import date

import httpx
import pandas as pd
import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.data import http, yahoo
from app.data.delivery import delivery_history, parse_bhavcopy, refresh_delivery, wanted_sessions
from app.models.tables import BhavcopyDay
from tests.conftest import FRI_EVENING, yf_frame

HEADER = "SYMBOL, SERIES, DATE1, PREV_CLOSE, OPEN_PRICE, HIGH_PRICE, LOW_PRICE, LAST_PRICE, CLOSE_PRICE, AVG_PRICE, TTL_TRD_QNTY, TURNOVER_LACS, NO_OF_TRADES, DELIV_QTY, DELIV_PER\n"


def bhav(day: str, pct: float = 44.65) -> bytes:
    return (
        HEADER
        + f"RELIANCE, EQ, {day}, 1178.00, 1179.00, 1180.00, 1165.00, 1170.00, 1170.30, 1171.00, 1000000, 11710.00, 50000, 540000, {pct}\n"
        + f"XYZ, BE, {day}, 10, 10, 10, 10, 10, 10, 10, 100, 0.01, 1, 100, 100.00\n"
        + f"NODELIV, EQ, {day}, 10, 10, 10, 10, 10, 10, 10, 100, 0.01, 1, -, -\n"
    ).encode()


def test_parse_bhavcopy_keeps_eq_only() -> None:
    rows = parse_bhavcopy(bhav("09-Oct-2026").decode(), date(2026, 10, 9))
    assert [r["symbol"] for r in rows] == ["RELIANCE", "NODELIV"]
    assert rows[0]["deliv_pct"] == 44.65 and rows[0]["turnover_lacs"] == 11710.0
    assert rows[1]["deliv_pct"] is None  # "-" means not reported, not zero


def test_wanted_sessions_are_completed_weekdays() -> None:
    got = wanted_sessions(FRI_EVENING, 6)
    assert got[0] == date(2026, 10, 9) and date(2026, 10, 4) not in got and len(got) == 6


def test_refresh_delivery_remembers_holidays(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("app.data.delivery.get_profiles", lambda: _profiles_with_lookback(3))
    calls: list[str] = []

    def handler(req: httpx.Request) -> httpx.Response:
        name = req.url.path.rsplit("_", 1)[-1]
        calls.append(name)
        if name == "08102026.csv":
            return httpx.Response(404)
        return httpx.Response(200, content=bhav("x", 50.0))

    http.set_client(httpx.Client(transport=httpx.MockTransport(handler)))
    r = refresh_delivery(session, now=FRI_EVENING)
    assert r.outcome == "updated" and "2 session(s) fetched, 1 holiday" in r.message
    days = {d.date: d.status for d in session.exec(select(BhavcopyDay))}
    assert days[date(2026, 10, 8)] == "missing" and days[date(2026, 10, 9)] == "ok"
    assert refresh_delivery(session, now=FRI_EVENING).outcome == "skipped"
    assert len(calls) == 3  # nothing re-fetched, the holiday included
    hist = delivery_history(session, "RELIANCE", 10)
    assert list(hist.index) == [date(2026, 10, 7), date(2026, 10, 9)]


def test_refresh_delivery_records_errors(session: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.data.delivery.get_profiles", lambda: _profiles_with_lookback(2))
    http.set_client(httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(503))))
    r = refresh_delivery(session, now=FRI_EVENING)
    assert r.outcome == "failed" and "HTTP 503" in r.message
    assert session.exec(select(BhavcopyDay)).all() == []  # will retry next time


def _profiles_with_lookback(n: int):  # type: ignore[no-untyped-def]
    from app.core.profiles import get_profiles

    p = get_profiles()
    return p.model_copy(
        update={"technical": p.technical.model_copy(update={"delivery_lookback_sessions": n})}
    )


def _fake_yahoo(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    asked: list[str] = []

    def dl(
        ticker: str, *, interval: str, start: date | None = None, period: str | None = None
    ) -> pd.DataFrame:
        asked.append(f"{ticker}:{interval}")
        if ticker == "NOPE.NS":
            return pd.DataFrame()
        if period:  # intraday
            idx = pd.date_range("2026-10-09 09:15", periods=60, freq="15min", tz="Asia/Kolkata")
            base = yf_frame(date(2026, 1, 1), date(2026, 4, 1)).iloc[:60]
            return base.set_axis(idx)
        return yf_frame(start or date(2021, 1, 1), date.today())

    monkeypatch.setattr(yahoo, "_download", dl)
    return asked


def test_technical_endpoint(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    asked = _fake_yahoo(monkeypatch)
    r = client.get("/analysis/technical/abc.ns", params={"style": "positional"})
    assert r.status_code == 200
    body = r.json()
    assert body["ticker"] == "ABC.NS" and [t["interval"] for t in body["timeframes"]] == [
        "1d",
        "1wk",
    ]
    daily = body["timeframes"][0]
    assert daily["bars"] > 1000 and daily["freshness"]["status"] in ("fresh", "stale")
    obs = daily["analysis"]["observations"]
    assert obs and all({"key", "direction", "text", "category"} <= o.keys() for o in obs)
    assert body["context"]["values"]["rs_3m"] is not None  # benchmark fetched too
    assert "not investment advice" in body["disclaimer"]
    assert asked == ["ABC.NS:1d", "^NSEI:1d"]
    client.get("/analysis/technical/ABC.NS", params={"style": "positional"})
    assert len(asked) == 2  # cached, fresh: no refetch


def test_technical_endpoint_uses_saved_style(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _fake_yahoo(monkeypatch)
    client.put("/settings/profile", json={"style": "long_term", "risk": "medium"})
    body = client.get("/analysis/technical/ABC.NS").json()
    assert body["style"] == "long_term" and [t["interval"] for t in body["timeframes"]] == [
        "1wk",
        "1mo",
    ]


def test_technical_endpoint_intraday_and_errors(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    asked = _fake_yahoo(monkeypatch)
    body = client.get("/analysis/technical/ABC.NS", params={"timeframes": ["15m"]}).json()
    tf = body["timeframes"][0]
    assert tf["interval"] == "15m" and tf["bars"] == 60 and tf["as_of"].endswith("+05:30")
    assert "ABC.NS:15m" in asked
    bad = client.get("/analysis/technical/NOPE.NS").json()
    assert bad["timeframes"][0]["bars"] == 0 and any("no 1d data" in e for e in bad["fetch_errors"])
    assert client.get("/analysis/technical/ABC.NS", params={"style": "weird"}).status_code == 422


def test_series_endpoint(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    _fake_yahoo(monkeypatch)
    client.get("/market/prices/ABC.NS")
    body = client.get("/analysis/technical/ABC.NS/series", params={"start": "2026-01-01"}).json()
    assert body["t"][0] >= "2026-01-01"
    assert len(body["columns"]["sma200"]) == len(body["t"])
    assert all(v is not None for v in body["columns"]["sma200"])  # computed on full history
    empty = client.get("/analysis/technical/ZZZ.NS/series").json()
    assert empty["t"] == [] and empty["columns"] == {}


def test_holdings_summary_uses_cache_only(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    with open("../sample_data/groww_stocks_holdings.xlsx", "rb") as f:
        client.post("/import/groww-stocks", files={"file": f})
    _fake_yahoo(monkeypatch)
    client.get("/market/prices/RELIANCE.NS")
    asked = _fake_yahoo(monkeypatch)
    rows = client.get("/analysis/technical/holdings", params={"style": "swing"}).json()
    assert asked == []  # no network
    assert len(rows) == 11
    rel = next(r for r in rows if r["ticker"] == "RELIANCE.NS")
    assert rel["bullish"] + rel["bearish"] > 0 and rel["freshness"]["status"] != "unavailable"
    other = next(r for r in rows if r["ticker"] == "TCS.NS")
    assert (
        other["freshness"]["status"] == "unavailable" and other["bullish"] == other["bearish"] == 0
    )
