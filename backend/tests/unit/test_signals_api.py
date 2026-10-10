from datetime import date
from pathlib import Path

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app.data import yahoo
from tests.conftest import yf_frame
from tests.unit.fundamentals_fixture import fake_fund_download

SAMPLES = Path(__file__).resolve().parents[3] / "sample_data"


def _fake_sources(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    asked: list[str] = []

    def dl(
        ticker: str, *, interval: str, start: date | None = None, period: str | None = None
    ) -> pd.DataFrame:
        asked.append(ticker)
        return yf_frame(start or date(2021, 1, 1), date.today())

    monkeypatch.setattr(yahoo, "_download", dl)
    fund = fake_fund_download()

    def fdl(ticker: str, what: str) -> object:
        asked.append(f"fund:{ticker}")
        return fund(ticker, what)

    monkeypatch.setattr(yahoo, "_fund_download", fdl)
    return asked


def _import(client: TestClient) -> None:
    for url, name in (
        ("/import/groww-stocks", "groww_stocks_holdings.xlsx"),
        ("/import/groww-mf", "groww_mf_holdings.xlsx"),
    ):
        with open(SAMPLES / name, "rb") as f:
            assert client.post(url, files={"file": (name, f)}).status_code == 200


def test_stock_signal_endpoint(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    _import(client)
    _fake_sources(monkeypatch)
    r = client.get("/analysis/stock/itc.ns", params={"style": "swing"})
    assert r.status_code == 200, r.text
    b = r.json()
    assert b["ticker"] == "ITC.NS" and b["style"] == "swing" and b["risk"] == "medium"
    assert b["signal"] in ("strong_buy", "buy", "hold", "reduce", "sell")
    assert b["signal_label"] and b["rule"]
    s = b["scores"]
    assert s["technical_weight"] == 0.7 and s["composite"] is not None
    assert s["confidence"] in ("high", "medium", "low")
    assert s["composite"] == pytest.approx(
        0.7 * s["technical"]["score"] + 0.3 * s["fundamental"]["score"], abs=0.2
    )
    assert b["bullish"] and all(x["points"] > 0 for x in b["bullish"])
    assert len(b["bullish"]) <= 3 and len(b["bearish"]) <= 3
    lv = b["levels"]
    assert lv["interval"] == "1d" and lv["trailing_stop"] < lv["close"] + 1e6
    assert [t["label"] for t in lv["targets"]][-2:] == ["2R", "3R"]
    assert b["position"]["quantity"] == 120 and b["weight"] > 0
    assert b["sector"] and b["max_weight"] == 0.12
    assert b["rebalance"]["action"] in ("add", "trim", "exit", "none")
    assert b["tax"]["term"] == "unknown" and "Verify" in b["tax"]["verify_note"]
    assert "not investment advice" in b["disclaimer"]
    # View the same stock under another style and risk.
    lt = client.get(
        "/analysis/stock/ITC.NS", params={"style": "long_term", "risk": "low", "fetch": False}
    ).json()
    assert lt["scores"]["technical_weight"] == 0.2 and lt["max_weight"] == 0.08
    assert [t["interval"] for t in lt["scores"]["technical"]["timeframes"]] == ["1wk", "1mo"]
    assert client.get("/analysis/stock/ITC.NS", params={"style": "nope"}).status_code == 422


def test_custom_style_uses_saved_slider(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _fake_sources(monkeypatch)
    client.put(
        "/settings/profile",
        json={"style": "custom", "risk": "high", "custom_technical_weight": 0.3},
    )
    b = client.get("/analysis/stock/ITC.NS").json()
    assert b["style"] == "custom" and b["risk"] == "high"
    assert b["scores"]["technical_weight"] == pytest.approx(0.3)
    assert b["position"] is None and b["weight"] is None


def test_unstyled_profile_falls_back_with_a_note(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _fake_sources(monkeypatch)
    b = client.get("/analysis/stock/ITC.NS").json()
    assert b["style"] == "positional" and any("No investing style" in n for n in b["notes"])


def test_holdings_signals_cached_only_and_history(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _import(client)
    _fake_sources(monkeypatch)
    client.get("/analysis/stock/RELIANCE.NS", params={"style": "swing"})  # caches one stock
    asked = _fake_sources(monkeypatch)
    body = client.get("/analysis/signals/holdings", params={"style": "swing"}).json()
    assert asked == []  # no network
    assert body["style"] == "swing" and body["weight_base"] == "portfolio"
    assert body["fund_value"] > 0 and body["total_value"] > body["stock_value"]
    rows = {h["ticker"]: h for h in body["holdings"]}
    assert len(rows) == 11
    rel = rows["RELIANCE.NS"]
    assert rel["composite"] is not None and rel["top_bullish"] and rel["stop"] is not None
    tcs = rows["TCS.NS"]  # nothing cached: no score, no guess
    assert tcs["composite"] is None and tcs["signal"] in ("no_signal", "reduce")
    assert sum(h["weight"] for h in body["holdings"]) < 1  # funds take the rest
    assert {s["sector"] for s in body["sectors"]}  # from NSE industry
    hist = client.get("/analysis/stock/RELIANCE.NS/history").json()
    assert len(hist) == 1 and hist[0]["style"] == "swing" and hist[0]["signal"] == rel["signal"]
    client.get("/analysis/signals/holdings", params={"style": "swing"})
    assert len(client.get("/analysis/stock/RELIANCE.NS/history").json()) == 1  # one per day
    client.get("/analysis/signals/holdings", params={"style": "long_term"})
    assert len(client.get("/analysis/stock/RELIANCE.NS/history").json()) == 2
    only = client.get("/analysis/stock/RELIANCE.NS/history", params={"style": "long_term"}).json()
    assert [h["style"] for h in only] == ["long_term"]


def test_market_refresh_records_signals(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.jobs import runner

    _import(client)
    _fake_sources(monkeypatch)
    job = client.post("/market/refresh", json={"scope": "prices"}).json()
    runner.get_runner().wait(job["id"], timeout=60)
    done = client.get(f"/jobs/{job['id']}").json()
    assert done["status"] == "done", done
    hist = client.get("/analysis/stock/ITC.NS/history").json()
    assert len(hist) == 1 and hist[0]["style"] == "positional"
