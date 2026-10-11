"""Score Shape endpoints, axis history, and the shape added to the watchlist and screener."""

import json
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.analysis.checks import get_checks
from app.core import db
from app.core.formatting import now_ist
from app.data import yahoo
from app.jobs.runner import get_runner
from app.models.tables import AxisRecord, SignalRecord
from tests.unit.fundamentals_fixture import fake_fund_download, statements_frames
from tests.unit.test_funds_api import _codes, _mfapi
from tests.unit.test_screener import _scan, _sources
from tests.unit.test_signals_api import _fake_sources, _import

STATUSES = {"pass", "fail", "no_data"}


def _assert_shape(b: dict, kind: str = "stock") -> None:  # type: ignore[type-arg]
    cfg = get_checks()
    keys = list(cfg.stock if kind == "stock" else cfg.fund)
    assert [s["key"] for s in b["sections"]] == keys
    assert b["axes"] == {s["key"]: s["score"] for s in b["sections"]}
    assert b["total"] == sum(v or 0 for v in b["axes"].values())
    assert b["max_total"] == 6 * sum(v is not None for v in b["axes"].values())
    assert b["checks_total"] == sum(len(s["checks"]) for s in b["sections"])
    for s in b["sections"]:
        assert len(s["checks"]) <= 6
        assert s["with_data"] == sum(c["status"] != "no_data" for c in s["checks"])
        assert s["passed"] == sum(c["status"] == "pass" for c in s["checks"])
        assert s["score"] is None or 0 <= s["score"] <= 6
        for c in s["checks"]:
            assert c["status"] in STATUSES and c["explanation"]
            # Every placeholder in the wording was filled in.
            assert "{" not in c["explanation"] and "}" not in c["explanation"], c
    assert b["confidence"] in ("high", "medium", "low") and b["summary"]


def test_stock_checks(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    _import(client)
    _fake_sources(monkeypatch)
    r = client.get("/analysis/stock/itc.ns/checks", params={"style": "swing"})
    assert r.status_code == 200, r.text
    b = r.json()
    _assert_shape(b)
    assert (
        b["ticker"] == "ITC.NS" and b["signal_label"] and "not investment advice" in b["disclaimer"]
    )
    checks = {c["check_id"]: c for s in b["sections"] for c in s["checks"]}
    # Fixture: debt 250 / equity 1,100 = 0.23×, within Medium's 1.0× limit.
    de = checks["debt_equity"]
    assert de["status"] == "pass" and de["display_threshold"] == "1.00×"
    assert "within your Medium risk limit of 1.00×" in de["explanation"]
    assert checks["revenue_cagr"]["status"] == "fail"  # 10% a year, below 15%
    assert (
        checks["pledge"]["status"] == "no_data" and "Screener.in" in checks["pledge"]["explanation"]
    )
    assert checks["dividend_consistent"]["status"] == "pass"
    # Lender-only checks don't appear for an industrial company.
    assert "capital_cushion" not in checks and "roce_good" in checks
    # No peers cached: no sector medians, so no fair value either.
    assert checks["fair_value"]["status"] == "no_data" and b["fair_value"] is None
    assert b["week_change"] is None  # no history yet

    # Style changes the signal shown, never the checks; risk changes the debt limit.
    lt = client.get(
        "/analysis/stock/ITC.NS/checks", params={"style": "long_term", "fetch": False}
    ).json()
    assert lt["axes"] == b["axes"] and lt["style"] == "long_term"
    low = client.get("/analysis/stock/ITC.NS/checks", params={"risk": "low", "fetch": False}).json()
    de_low = next(c for s in low["sections"] for c in s["checks"] if c["check_id"] == "debt_equity")
    assert de_low["display_threshold"] == "0.50×" and low["risk_label"] == "Low"


def test_lenders_get_their_own_health_checks(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _fake_sources(monkeypatch)
    frames = statements_frames()
    frames["info"] = {**frames["info"], "sector": "Financial Services"}
    monkeypatch.setattr(yahoo, "_fund_download", fake_fund_download(frames))
    b = client.get("/analysis/stock/HDFCBANK.NS/checks").json()
    _assert_shape(b)
    assert b["is_financial"]
    health = next(s for s in b["sections"] if s["key"] == "health")
    assert [c["check_id"] for c in health["checks"]] == [
        "pledge",
        "capital_cushion",
        "book_growth",
        "roa",
    ]
    assert health["score"] is not None  # 3 lender checks with data: enough for a score
    assert health["note"] == "Some checks don't apply to lenders and insurers"


def test_holdings_checks_and_portfolio_shape(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _import(client)
    _fake_sources(monkeypatch)
    r = client.get("/analysis/checks/holdings", params={"style": "swing"})
    assert r.status_code == 200, r.text
    b = r.json()
    assert b["holdings"] and b["style"] == "swing"
    shape = b["portfolio"]
    assert [a["key"] for a in shape["axes"]] == list(get_checks().stock)
    # Each portfolio axis is the value-weighted average of the holdings that have a score.
    for a in shape["axes"]:
        scored = [
            (h["value"], h["axes"][a["key"]])
            for h in b["holdings"]
            if h["value"] and h["axes"][a["key"]] is not None
        ]
        if scored:
            avg = sum(v * s for v, s in scored) / sum(v for v, _ in scored)
            assert a["score"] == pytest.approx(avg, abs=0.05)
    assert shape["holdings"] == len(b["holdings"])
    assert all(h["top"] for h in b["holdings"] if any(v is not None for v in h["axes"].values()))
    assert any("Mutual funds" in n for n in b["notes"])  # the sample has funds too
    assert isinstance(b["rewards"], list) and isinstance(b["risks"], list)
    # A read-only view: it doesn't write signal or axis history.
    with Session(db.get_engine()) as s:
        assert not s.exec(select(AxisRecord)).all()


def test_financial_history(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    _fake_sources(monkeypatch)
    b = client.get("/analysis/fundamental/ITC.NS/history").json()
    assert b["unit"] == "₹ Cr" and [y["fy"] for y in b["years"]] == [
        "FY2023",
        "FY2024",
        "FY2025",
        "FY2026",
    ]
    last = b["years"][-1]
    assert last["revenue"] == 1331 and last["net_income"] == 150
    assert last["debt_equity"] == pytest.approx(250 / 1100, abs=0.01)
    assert last["payout_pct"] == pytest.approx(30.0) and last["fcf"] == 110
    assert last["op_margin"] == pytest.approx(220 / 1331 * 100, abs=0.01)
    assert len(b["quarters"]) == 5 and b["quarters"][-1]["revenue"] == 368
    assert any(y["pe"] for y in b["years"])  # prices cover the year-ends
    assert b["fair_value"] is None and any("Fair value" in n for n in b["notes"])


def test_axis_history_and_week_change(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    _import(client)
    _fake_sources(monkeypatch)
    client.put("/settings/profile", json={"style": "swing", "risk": "medium"})
    client.get("/analysis/stock/ITC.NS/checks")  # download ITC's data (holdings use the cache)
    # Computing holdings' signals saves them, and now their shapes too.
    assert client.get("/analysis/signals/holdings").status_code == 200
    today = now_ist().date()
    with Session(db.get_engine()) as s:
        rows = s.exec(select(AxisRecord).where(AxisRecord.ticker == "ITC.NS")).all()
        assert len(rows) == 1 and rows[0].day == today and rows[0].risk == "medium"
        axes = json.loads(rows[0].axes_json)
        assert set(axes) == set(get_checks().stock)
        # A week ago: one axis lower and a different signal.
        old_axes = {**axes, "health": (axes["health"] or 0) - 2}
        week_ago = today - timedelta(days=8)
        s.add(
            AxisRecord(
                ticker="ITC.NS",
                day=week_ago,
                risk="medium",
                axes_json=json.dumps(old_axes),
                total=rows[0].total - 2,
                max_total=rows[0].max_total,
            )
        )
        current = s.exec(select(SignalRecord).where(SignalRecord.ticker == "ITC.NS")).one().signal
        other = "sell" if current != "sell" else "buy"
        s.add(
            SignalRecord(ticker="ITC.NS", day=week_ago, style="swing", risk="medium", signal=other)
        )
        s.commit()
    wc = client.get("/analysis/stock/ITC.NS/checks", params={"fetch": False}).json()["week_change"]
    assert wc["since"] == week_ago.isoformat()
    assert wc["axes"]["health"] == 2 and wc["total"] == 2
    assert wc["previous_signal"] == other and wc["signal_changed"]
    assert wc["previous_signal_label"]


def test_watchlist_items_carry_the_shape(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _sources(monkeypatch)
    client.post("/watchlist", json={"ticker": "ITC"})
    job = client.get("/jobs").json()[0]
    get_runner().wait(job["id"], timeout=60)
    item = client.get("/watchlist").json()["items"][0]
    assert set(item["axes"]) == set(get_checks().stock)
    assert item["shape_total"] == sum(v or 0 for v in item["axes"].values())
    assert item["shape_step"] in (1, 2, 3, 4, 5) and item["week_change"] is None


def test_screener_scans_store_axis_scores(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _sources(monkeypatch)
    _scan(client)
    top = client.post("/screener/screen", json={"preset": "top_scores"}).json()["candidates"]
    assert top and all("axis_health" in c["facts"] and "axis_total" in c["facts"] for c in top)
    assert all(0 <= c["facts"]["axis_total"] <= 36 for c in top)
    res = client.post(
        "/screener/screen", json={"filters": [{"field": "axis_health", "op": "gte", "value": 0}]}
    ).json()
    assert res["filters"] == ["Financial Health (shape) ≥ 0/6"] and res["candidates"]
    none = client.post(
        "/screener/screen", json={"filters": [{"field": "axis_total", "op": "gt", "value": 36}]}
    ).json()
    assert none["candidates"] == []


def test_fund_checks(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    _import(client)
    _fake_sources(monkeypatch)
    codes = _codes(client)
    regular = codes["Mirae Asset Large Cap Fund Regular Growth"]
    direct = codes["Parag Parikh Flexi Cap Fund Direct Growth"]
    _mfapi(monkeypatch, {regular: 11.0, direct: 60.0})
    r = client.get(f"/analysis/mf/{direct}/checks")
    assert r.status_code == 200, r.text
    b = r.json()
    _assert_shape(b, "fund")
    checks = {c["check_id"]: c for s in b["sections"] for c in s["checks"]}
    assert checks["direct_plan"]["status"] == "pass"
    assert checks["beat_bench_3y"]["status"] == "pass"  # 60% a year beats any fake benchmark
    assert checks["expense_ok"]["status"] == "no_data"  # not entered yet
    client.put(f"/analysis/mf/{direct}/expense-ratio", json={"expense_ratio_pct": 0.6})
    b = client.get(f"/analysis/mf/{direct}/checks", params={"fetch": False}).json()
    cost = next(s for s in b["sections"] if s["key"] == "cost")
    assert cost["score"] == 6 and cost["with_data"] == 2

    reg = client.get(f"/analysis/mf/{regular}/checks").json()
    dp = next(c for s in reg["sections"] for c in s["checks"] if c["check_id"] == "direct_plan")
    assert dp["status"] == "fail" and "pp a year" in dp["explanation"]
    assert any("Regular plan" in x for x in reg["risks"])

    # "holdings" isn't read as a scheme code.
    allf = client.get("/analysis/mf/holdings/checks")
    assert allf.status_code == 200 and len(allf.json()["funds"]) == len(codes)
    assert client.get("/analysis/mf/999999/checks").status_code == 404


def test_checks_config_endpoint(client: TestClient) -> None:
    b = client.get("/analysis/checks/config").json()
    assert b["axis_max"] == 6 and len(b["score_steps"]) == 4
    assert [a["key"] for a in b["stock"]] == list(get_checks().stock)
    assert b["stock"][1]["label"] == "Future Growth" and "forecasts" in b["stock"][1]["caption"]
    assert [a["key"] for a in b["fund"]] == list(get_checks().fund)
