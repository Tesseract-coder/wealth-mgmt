"""Screener: filters, pre-filters, ranking, the scan job, saved screens, watchlist."""

import csv
import io
import json
from datetime import date, timedelta

import pandas as pd
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlmodel import Session, select

from app.analysis.positions import Portfolio, Position
from app.core import db
from app.core.profiles import ScreenFilter, get_profiles
from app.data import yahoo
from app.jobs.runner import get_runner
from app.models.tables import SignalRecord, WatchItem
from app.screener.fields import FIELD_BY_KEY
from app.screener.scan import (
    Levels,
    ScanRow,
    avg_traded_value_cr,
    custom_members,
    parse_symbols,
)
from app.screener.screens import check, describe, prefilter_failures, screen, sector_impact
from app.screener.watchlist import last_change
from tests.conftest import yf_frame
from tests.unit.fundamentals_fixture import CR, statements_frames
from tests.unit.test_funds_api import _import

# ---------------------------------------------------------------------------- pure functions


def F(field: str, op: str, value: float | list[float]) -> ScreenFilter:
    return ScreenFilter(field=field, op=op, value=value)  # type: ignore[arg-type]


def row(sym: str, composite: float | None = 75, **facts: float | None) -> ScanRow:
    base: dict[str, float | None] = {"market_cap": 50000, "debt_equity": 0.2, "beta": 1.0}
    return ScanRow(
        ticker=f"{sym}.NS",
        symbol=sym,
        label=sym.title(),
        sector=str(facts.pop("sector", "IT")),
        status="scored",
        facts={**base, **facts, "composite": composite},
        signal="buy" if (composite or 0) >= 70 else "hold",
        signal_label="Buy / Add",
        rule="r",
        confidence="high",
        composite=composite,
        levels=Levels("1d", 100, 4, 98, 100, "zone", 92, -8, [], "basis"),
    )


def test_presets_in_config_are_valid_and_use_known_fields() -> None:
    presets = get_profiles().screener.presets
    assert {
        "quality_fair_price",
        "momentum_breakout",
        "pullback_uptrend",
        "growth",
        "dividend_value",
    } <= set(presets)
    for p in presets.values():
        assert all(f.field in FIELD_BY_KEY for f in p.filters)


@pytest.mark.parametrize(
    ("kw", "msg"),
    [
        ({"field": "nope", "op": "gt", "value": 1}, "unknown screener field"),
        ({"field": "rsi", "op": "between", "value": 30}, r"needs \[low, high\]"),
        ({"field": "rsi", "op": "between", "value": [50, 30]}, "low is above high"),
        ({"field": "rsi", "op": "gt", "value": [1, 2]}, "single number"),
        ({"field": "rsi", "op": "eq", "value": 1}, "Input should be"),
    ],
)
def test_filter_validation(kw: dict[str, object], msg: str) -> None:
    with pytest.raises(ValidationError, match=msg):
        ScreenFilter(**kw)  # type: ignore[arg-type]


def test_check_ops_missing_values_and_financial_exemption() -> None:
    assert check(F("rsi", "gt", 50), 51, False) and not check(F("rsi", "gt", 50), 50, False)
    assert check(F("rsi", "gte", 50), 50, False) and check(F("rsi", "lte", 50), 50, False)
    assert not check(F("rsi", "lt", 50), 50, False)
    assert check(F("rsi", "between", [35, 45]), 35, False)
    assert not check(F("rsi", "between", [35, 45]), 45.1, False)
    assert check(F("roe", "gte", 15), None, False) is None  # missing fails, never assumed
    assert check(F("roe", "gte", 15), None, True) is None  # ROE applies to banks too
    assert check(F("debt_equity", "lte", 0.5), None, True) is True  # not for lenders
    assert describe(F("rsi", "between", [35, 45])) == "RSI (14) between 35 and 45"
    assert describe(F("roe", "gte", 15)) == "ROE ≥ 15%"


def test_parse_symbols_and_custom_universe() -> None:
    assert parse_symbols("tcs, INFY.ns\nTCS  itc") == ["TCS", "INFY", "ITC"]
    members, unknown = custom_members(["TCS", "NIFTYBEES", "NOSUCH"])
    assert [m.ticker for m in members] == ["TCS.NS"] and members[0].industry
    assert unknown == ["NIFTYBEES", "NOSUCH"]  # ETFs aren't stock ideas


def test_avg_traded_value() -> None:
    df = pd.DataFrame({"close": [100.0, 200.0, 300.0], "volume": [1e6, 1e6, None]})
    assert avg_traded_value_cr(df, 2) == 15.0  # (₹10 Cr + ₹20 Cr) / 2; the gap is skipped
    assert avg_traded_value_cr(pd.DataFrame(), 20) is None


def test_prefilters_from_risk_level() -> None:
    med = get_profiles().risk_levels["medium"]
    assert prefilter_failures(row("A"), med) == []
    assert "unknown" in prefilter_failures(row("A", market_cap=None), med)[0]
    assert "below your ₹5,000 Cr minimum" in prefilter_failures(row("A", market_cap=4000), med)[0]
    assert "Debt/equity 1.50" in prefilter_failures(row("A", debt_equity=1.5), med)[0]
    bank = row("B", debt_equity=8.0)
    bank.is_financial = True
    assert prefilter_failures(bank, med) == []  # leverage is a bank's business
    assert "Beta 1.50" in prefilter_failures(row("A", beta=1.5), med)[0]
    assert (
        prefilter_failures(row("A", beta=None, debt_equity=None), med) == []
    )  # unknown: unchecked
    high = get_profiles().risk_levels["high"]
    assert prefilter_failures(row("A", beta=3.0), high) == []  # no beta limit on High


def test_screen_ranks_filters_and_counts() -> None:
    p = get_profiles()
    med = p.risk_levels["medium"]
    rows = [
        row("LOW", 72, rsi=40),
        row("TOP", 88, rsi=42),
        row("MID", 80, rsi=60),  # fails the RSI filter
        row("NODATA", 85),  # no RSI at all
        row("HELD", 90, rsi=40),
        row("SMALL", 95, rsi=40, market_cap=100),
        row("AVOID", 30, rsi=40),
        ScanRow("X.NS", "X", "X", None, "illiquid"),
    ]
    rows[4].held = True
    rows[6].signal = "sell"
    res = screen(rows, [F("rsi", "between", [35, 45])], p, med, None)
    assert [c.row.symbol for c in res.candidates] == ["TOP", "LOW"]
    assert res.candidates[0].rank == 1 and res.candidates[0].passed == [
        "RSI (14) between 35 and 45"
    ]
    assert res.counts == {
        "universe": 8, "not_scored": 1, "held": 1, "prefilter": 1, "signal": 1,
        "filters": 1, "missing_data": 1, "passed": 2,
    }  # fmt: skip
    assert {r.symbol for r, _ in res.near_misses} == {"MID", "NODATA"}
    assert any("(no data)" in f for _, fs in res.near_misses for f in fs)
    assert any("Market cap" in t for t in res.prefilters)
    assert any("Sell / Exit" in t for t in res.prefilters)
    # Holdings can be included; top_n caps the list.
    inc = screen(rows, [F("rsi", "between", [35, 45])], p, med, None, include_held=True, top_n=1)
    assert [c.row.symbol for c in inc.candidates] == ["HELD"]
    assert "Import your holdings" in inc.candidates[0].impact.text


def test_sector_impact_of_a_starter_position() -> None:
    p = get_profiles()
    med = p.risk_levels["medium"]
    pos = Position("A.NS", "A", 10, 100, 1000, 100, "x", 25000, "IT", [])
    pf = Portfolio({"A.NS": pos}, 100000, 100000, 0, {"IT": 25000}, "portfolio")
    imp = sector_impact(row("B"), pf, med, p.rebalance)
    target = 0.12 * p.rebalance.buy_target  # 9%
    amount = target * 100000 / (1 - target)
    assert imp.amount == pytest.approx(amount, abs=0.01) and imp.quantity == int(amount // 100)
    assert imp.before == 0.25 and imp.after == pytest.approx(
        (25000 + amount) / (100000 + amount), abs=1e-4
    )
    assert imp.over_limit and "above your 30% sector limit" in imp.text
    other = sector_impact(row("C", sector="Energy"), pf, med, p.rebalance)
    assert other.before == 0 and not other.over_limit


def test_last_signal_change(session: Session) -> None:
    d = date(2026, 10, 1)
    for i, sig in enumerate(["hold", "hold", "buy", "buy"]):
        session.add(
            SignalRecord(
                ticker="A.NS", day=d + timedelta(days=i), style="swing", risk="medium", signal=sig
            )
        )
    session.commit()
    chg = last_change(session, "A.NS", "swing", "medium")
    assert chg and (chg.previous, chg.current, chg.day) == ("hold", "buy", date(2026, 10, 3))
    assert last_change(session, "A.NS", "long_term", "medium") is None


# ---------------------------------------------------------------------------- scan job + API

UNIVERSE = "TCS, INFY, ITC, HDFCBANK, LT, NOSUCH"


def _sources(
    monkeypatch: pytest.MonkeyPatch, *, thin: str = "LT", broken: str = "INFY"
) -> list[str]:
    """Rising prices (different slopes), ample volume except `thin`; `broken` has no data."""
    asked: list[str] = []
    slope = {"TCS.NS": 1.2, "ITC.NS": 0.9, "HDFCBANK.NS": 1.05}

    def dl(
        ticker: str, *, interval: str, start: date | None = None, period: str | None = None
    ) -> pd.DataFrame:
        asked.append(ticker)
        if ticker == f"{broken}.NS":
            raise ConnectionError("no data")
        df = yf_frame(start or date(2021, 1, 1), date.today(), factor=slope.get(ticker, 1.0))
        df["Volume"] = 1000.0 if ticker == f"{thin}.NS" else 5e6
        return df

    frames = statements_frames()
    # ~₹50,000 Cr at these prices (price × shares): above every risk level's minimum
    frames["info"] = {**frames["info"], "sharesOutstanding": 1e9, "marketCap": 60000 * CR}

    def fdl(ticker: str, what: str) -> object:
        asked.append(f"fund:{ticker}")
        if ticker == f"{broken}.NS":
            raise ConnectionError("no data")
        return frames[what]

    monkeypatch.setattr(yahoo, "_download", dl)
    monkeypatch.setattr(yahoo, "_fund_download", fdl)
    return asked


def _scan(client: TestClient, **body: object) -> dict:  # type: ignore[type-arg]
    r = client.post("/screener/run", json={"universe": "custom", "symbols": UNIVERSE, **body})
    assert r.status_code == 202, r.text
    job_id = r.json()["job"]["id"]
    get_runner().wait(job_id, timeout=60)
    b = client.get(f"/screener/jobs/{job_id}").json()
    assert b["job"]["status"] == "done", b
    return b  # type: ignore[no-any-return]


def test_config_lists_universes_presets_and_fields(client: TestClient) -> None:
    b = client.get("/screener/config").json()
    sizes = {u["key"]: u["size"] for u in b["universes"]}
    assert sizes["nifty50"] == 50 and sizes["nifty500"] >= 450 and "custom" in sizes
    assert b["default_universe"] == "nifty500" and b["top_n"] == 20
    assert b["seconds_per_stock"] == 6.5  # 6 Yahoo requests at 60 a minute + 0.5 s pause
    assert [p["key"] for p in b["presets"]][0] == "top_scores"
    assert {f["key"] for f in b["fields"]} >= {"roe", "rsi", "pe_vs_sector", "composite"}
    assert b["latest_scan"] is None and "not investment advice" in b["disclaimer"]


def test_scan_job_scores_universe_and_screens_instantly(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    asked = _sources(monkeypatch)
    b = _scan(client)
    scan = b["scan"]
    assert scan["status"] == "complete" and scan["total"] == 5 and scan["scored"] == 3
    assert scan["style"] == "positional"  # no style chosen yet: the documented fallback
    assert any("NOSUCH" in n for n in scan["notes"])
    assert "fund:LT.NS" not in asked  # illiquid: no fundamentals downloaded
    assert any("INFY" in e for e in b["job"]["errors"])
    stocks = {s["ticker"]: s for s in client.get(f"/screener/scans/{scan['id']}/stocks").json()}
    assert (
        stocks["LT.NS"]["status"] == "illiquid"
        and "₹0.0 Cr a day" in stocks["LT.NS"]["status_text"]
    )
    assert stocks["INFY.NS"]["status"] == "no_prices"

    r = client.post("/screener/screen", json={"preset": "top_scores"})
    assert r.status_code == 200, r.text
    res = r.json()
    assert res["counts"]["universe"] == 5 and res["counts"]["not_scored"] == 2
    cands = res["candidates"]
    assert cands and [c["rank"] for c in cands] == list(range(1, len(cands) + 1))
    comps = [c["composite"] for c in cands]
    assert comps == sorted(comps, reverse=True)
    c = cands[0]
    lv = c["levels"]
    assert lv["stop"] < lv["entry_low"] <= lv["entry_high"] == lv["close"]
    assert lv["targets"] and lv["targets"][-1]["label"] == "3R"
    assert c["bullish"] and c["signal_label"] and c["rule"]
    assert "Import your holdings" in c["impact"]["text"]
    assert all(x["signal"] not in ("sell", "reduce") for x in cands)
    assert "not investment advice" in res["disclaimer"]

    # Ad-hoc filters run on the stored scan without downloading anything.
    n = len(asked)
    adhoc = client.post(
        "/screener/screen", json={"filters": [{"field": "rsi", "op": "gt", "value": 101}]}
    ).json()
    assert adhoc["candidates"] == [] and adhoc["title"] == "Custom filters" and len(asked) == n
    assert adhoc["filters"] == ["RSI (14) > 101"]
    bad = client.post(
        "/screener/screen", json={"filters": [{"field": "x", "op": "gt", "value": 1}]}
    )
    assert bad.status_code == 422 and "unknown screener field" in bad.json()["detail"]
    assert client.post("/screener/screen", json={"preset": "nope"}).status_code == 404

    # A cached-only rescan downloads nothing.
    _scan(client, fetch="cached")
    assert len(asked) == n

    # CSV export ends with the disclaimer.
    text = client.get("/export/screener.csv", params={"preset": "top_scores"}).text.lstrip("﻿")
    out = list(csv.reader(io.StringIO(text)))
    assert out[0][:3] == ["Rank", "Ticker", "Name"] and out[1][0] == "1"
    assert out[-1][0] == "Disclaimer" and "Custom list" in out[-2][1]
    pdf = client.get("/export/screener.pdf", params={"preset": "top_scores"})
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")


def test_holdings_are_excluded_unless_asked_and_sector_effect_shown(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _import(client)  # the sample holds TCS, ITC, HDFCBANK …
    _sources(monkeypatch)
    _scan(client)
    res = client.post("/screener/screen", json={"preset": "top_scores"}).json()
    assert res["counts"]["held"] >= 1 and all(not c["held"] for c in res["candidates"])
    inc = client.post(
        "/screener/screen", json={"preset": "top_scores", "include_held": True}
    ).json()
    assert any(c["held"] for c in inc["candidates"])
    c = inc["candidates"][0]
    assert c["impact"]["before"] is not None and "takes" in c["impact"]["text"]


def test_style_change_marks_scan_stale(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    _sources(monkeypatch)
    _scan(client, style="swing")
    assert client.post("/screener/screen", json={}).json()["stale_note"] is None
    client.put("/settings/profile", json={"style": "long_term", "risk": "medium"})
    assert "different style" in client.post("/screener/screen", json={}).json()["stale_note"]


def test_screen_needs_a_scan(client: TestClient) -> None:
    r = client.post("/screener/screen", json={"preset": "growth"})
    assert r.status_code == 404 and "Run a scan first" in r.json()["detail"]
    r = client.post("/screener/run", json={"universe": "custom", "symbols": " "})
    assert r.status_code == 422


def test_saved_screens_crud(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    body = {"name": "Cheap quality", "filters": [{"field": "roe", "op": "gte", "value": 12}]}
    r = client.post("/screener/screens", json=body)
    assert r.status_code == 201, r.text
    sid = r.json()["id"]
    assert client.post("/screener/screens", json=body).status_code == 409
    preset_name = {**body, "name": "Growth"}
    assert client.post("/screener/screens", json=preset_name).status_code == 409
    bad = {**body, "name": "x", "filters": [{"field": "rsi", "op": "between", "value": [5, 1]}]}
    assert client.post("/screener/screens", json=bad).status_code == 422
    assert client.post("/screener/screens", json={**body, "filters": []}).status_code == 422
    up = client.put(
        f"/screener/screens/{sid}",
        json={"name": "Cheap quality", "filters": [{"field": "pe", "op": "lt", "value": 20}]},
    )
    assert up.status_code == 200 and up.json()["filters"][0]["field"] == "pe"
    assert [s["name"] for s in client.get("/screener/config").json()["screens"]] == [
        "Cheap quality"
    ]

    _sources(monkeypatch)
    _scan(client)
    res = client.post("/screener/screen", json={"screen_id": sid}).json()
    assert res["title"] == "Cheap quality" and res["filters"] == ["P/E < 20"]
    assert client.delete(f"/screener/screens/{sid}").status_code == 204
    assert client.post("/screener/screen", json={"screen_id": sid}).status_code == 404


def test_cancel_keeps_finished_part(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    _sources(monkeypatch)
    from app.screener import scan as scan_mod

    real = scan_mod.fetch_data
    calls: list[str] = []

    def slow(session, provider, m, *a, **kw):  # type: ignore[no-untyped-def]
        calls.append(m.symbol)
        if len(calls) == 2:  # ask to stop while the second stock is being fetched
            client.post(f"/jobs/{job_id}/cancel")
        return real(session, provider, m, *a, **kw)

    monkeypatch.setattr(scan_mod, "fetch_data", slow)
    r = client.post("/screener/run", json={"universe": "custom", "symbols": UNIVERSE})
    job_id = r.json()["job"]["id"]
    get_runner().wait(job_id, timeout=60)
    b = client.get(f"/screener/jobs/{job_id}").json()
    assert b["job"]["status"] == "cancelled" and b["scan"]["status"] == "partial"
    assert len(calls) == 2 and any("Stopped early" in n for n in b["scan"]["notes"])
    assert client.post(f"/jobs/{job_id}/cancel").status_code == 409  # already finished


def test_scan_pauses_only_after_downloads(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.data.provider import CachedProvider
    from app.jobs.runner import Progress
    from app.models.tables import ScreenerScan
    from app.screener.scan import ScanParams, run_scan

    _sources(monkeypatch)
    slept: list[float] = []
    params = ScanParams("custom", "swing", "medium", 0.5, "missing", ["TCS", "ITC"])

    def go(p: ScanParams) -> ScreenerScan:
        scan = ScreenerScan(
            universe="custom", universe_label="c", style="swing", risk="medium", fetch=p.fetch
        )
        session.add(scan)
        session.commit()
        run_scan(session, CachedProvider(session), p, Progress(0), scan, sleep=slept.append)
        return scan

    s1 = go(params)
    assert slept == [0.5, 0.5] and s1.scored == 2
    rows = json.loads(s1.rows_json)
    assert all(isinstance(v, float | None) for r in rows for v in r["facts"].values())
    slept.clear()
    go(params)  # everything is cached and fresh now
    assert slept == []


# ---------------------------------------------------------------------------- watchlist


def test_watchlist_add_view_note_remove(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _sources(monkeypatch)
    assert client.post("/watchlist", json={"ticker": "NOSUCH"}).status_code == 422
    etf = client.post("/watchlist", json={"ticker": "NIFTYBEES"})
    assert etf.status_code == 422 and "ETF" in etf.json()["detail"]

    # No data cached yet: a background download starts and the item says so.
    r = client.post("/watchlist", json={"ticker": "itc", "source": "Screener: Growth"})
    assert r.status_code == 201, r.text
    assert r.json()["ticker"] == "ITC.NS" and r.json()["status"] == "no_data"
    job = client.get("/jobs").json()[0]
    assert job["kind"] == "watchlist_fetch"
    get_runner().wait(job["id"], timeout=60)

    assert client.get("/watchlist/tickers").json() == ["ITC.NS"]
    b = client.get("/watchlist").json()
    item = b["items"][0]
    assert item["status"] == "ok" and item["signal_label"] and item["composite"] is not None
    assert item["added_signal"] == item["signal"] and item["score_change"] == 0  # baseline set
    assert item["source"] == "Screener: Growth" and item["price"] and item["stop"]
    assert "not investment advice" in b["disclaimer"]

    # Adding again keeps the baseline and only updates the note.
    again = client.post("/watchlist", json={"ticker": "ITC.NS", "note": "results on 20th"})
    assert (
        again.json()["note"] == "results on 20th" and again.json()["added_signal"] == item["signal"]
    )
    assert client.patch("/watchlist/ITC.NS", json={"note": " "}).json()["note"] is None

    # Score and price changes are measured against the baseline.
    with Session(db.get_engine()) as s:
        w = s.get(WatchItem, "ITC.NS")
        assert w is not None
        w.added_price, w.added_score, w.added_signal = (
            item["price"] / 2,
            (item["composite"] or 0) - 5,
            "sell",
        )
        s.add(w)
        s.commit()
    item = client.get("/watchlist").json()["items"][0]
    assert item["price_change_pct"] == pytest.approx(100, abs=0.01) and item["score_change"] == 5
    assert item["signal_changed_since_added"] and item["added_signal_label"] == "Sell / Exit"

    assert client.delete("/watchlist/ITC.NS").status_code == 204
    assert client.get("/watchlist").json()["items"] == []
    assert client.delete("/watchlist/ITC.NS").status_code == 404


def test_refresh_includes_watchlist(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    asked = _sources(monkeypatch)
    client.post("/watchlist", json={"ticker": "TCS"})
    get_runner().wait(client.get("/jobs").json()[0]["id"], timeout=60)
    asked.clear()
    r = client.post("/market/refresh", json={"scope": "prices", "force": True})
    assert r.status_code in (200, 202), r.text
    get_runner().wait(r.json()["id"], timeout=60)
    assert "TCS.NS" in asked
    with Session(db.get_engine()) as s:
        recs = s.exec(select(SignalRecord).where(SignalRecord.ticker == "TCS.NS")).all()
    assert len(recs) == 1  # today's watchlist signal is in the history


def test_watchlist_baseline_uses_your_portfolio(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Sector-limit flags depend on your holdings; the baseline must see them too."""
    _import(client)
    _sources(monkeypatch)
    _scan(client)  # caches data for the universe
    r = client.post("/watchlist", json={"ticker": "TCS"}).json()
    assert r["status"] == "ok" and r["added_signal"] == r["signal"]
    assert not r["signal_changed_since_added"]
