import csv
import io
from datetime import date

import pytest
from fastapi.testclient import TestClient

from app.analysis.actions import SEVERITY_ORDER, Action
from app.core.profiles import get_profiles
from app.core.settings import get_settings
from tests.unit.test_funds_api import _codes, _import, _mfapi
from tests.unit.test_signals_api import _fake_sources


def _items(body: dict) -> dict[str, dict]:  # type: ignore[type-arg]
    return {i["path"]: i for i in body["items"]}


def test_thresholds_edit_validate_and_reset(client: TestClient) -> None:
    b = client.get("/settings/thresholds").json()
    items = _items(b)
    path = "risk_levels.medium.buy_threshold"
    base = items[path]["default"]
    assert items[path]["value"] == base and not items[path]["edited"] and b["edited"] == 0
    assert "styles.custom.technical_weight" not in items  # custom uses your saved slider

    r = client.put("/settings/thresholds", json={"values": {path: base + 2}})
    assert r.status_code == 200, r.text
    items = _items(r.json())
    assert items[path]["value"] == base + 2 and items[path]["edited"] and r.json()["edited"] == 1
    assert get_profiles().risk_levels["medium"].buy_threshold == base + 2  # live, no restart
    assert get_settings().profiles_override_path.exists()

    # Style weights stay in step so they add up to 1.
    client.put("/settings/thresholds", json={"values": {"styles.swing.technical_weight": 0.7}})
    sw = get_profiles().styles["swing"]
    assert (sw.technical_weight, sw.fundamental_weight) == pytest.approx((0.7, 0.3))

    # Nullable limits can be cleared; required ones can't.
    ok = client.put("/settings/thresholds", json={"values": {"risk_levels.low.max_beta": None}})
    assert ok.status_code == 200 and get_profiles().risk_levels["low"].max_beta is None
    bad = client.put("/settings/thresholds", json={"values": {path: None}})
    assert bad.status_code == 400 and "needs a value" in bad.json()["detail"]

    # Invalid values are refused before anything is written.
    bad = client.put(
        "/settings/thresholds", json={"values": {"risk_levels.medium.max_weight_per_stock": 2}}
    )
    assert bad.status_code == 400 and "Max weight per stock" in bad.json()["detail"]
    bad = client.put("/settings/thresholds", json={"values": {"signals.hold_floor": 10}})
    assert bad.status_code == 400  # reduce_floor must stay below hold_floor
    bad = client.put("/settings/thresholds", json={"values": {"tax.ltcg_rate": 0}})
    assert bad.status_code == 400 and "can't be edited" in bad.json()["detail"]
    assert get_profiles().risk_levels["medium"].max_weight_per_stock <= 1

    r = client.delete("/settings/thresholds")
    assert r.json()["edited"] == 0 and not get_settings().profiles_override_path.exists()
    assert get_profiles().risk_levels["medium"].buy_threshold == base


def test_holdings_signals_carry_position_columns(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _import(client)
    _fake_sources(monkeypatch)
    client.get("/analysis/stock/RELIANCE.NS")
    rel = next(
        h
        for h in client.get("/analysis/signals/holdings").json()["holdings"]
        if h["ticker"] == "RELIANCE.NS"
    )
    assert rel["quantity"] > 0 and rel["avg_price"] > 0 and rel["price"] > 0
    assert rel["value"] == pytest.approx(rel["quantity"] * rel["price"], rel=1e-3)
    assert rel["pnl_pct"] == pytest.approx(rel["pnl"] / rel["invested"] * 100, abs=0.01)


def test_actions_sorted_by_severity(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    _import(client)
    _fake_sources(monkeypatch)
    codes = _codes(client)
    regular = codes["Mirae Asset Large Cap Fund Regular Growth"]
    _mfapi(monkeypatch, {regular: 11.0})
    client.get(f"/analysis/mf/{regular}")
    b = client.get("/portfolio/actions").json()
    acts = b["actions"]
    assert acts and b["risk_label"] and b["disclaimer"]
    ranks = [SEVERITY_ORDER[a["severity"]] for a in acts]
    assert ranks == sorted(ranks)
    switch = [a for a in acts if a["kind"] == "fund" and a["title"] == "Switch"]
    assert switch and switch[0]["link"] == f"/mutual-funds/{regular}"
    assert switch[0]["severity"] == "medium"  # a cheaper plan, not underperformance
    # Uncached stocks show as data problems, never as invented signals.
    assert any(a["kind"] == "data" for a in acts)
    assert not any(a["title"] == "Red flag" and "sector limit" in a["detail"] for a in acts)


def test_actions_empty(client: TestClient) -> None:
    assert client.get("/portfolio/actions").json()["actions"] == []


def test_action_dataclass_order() -> None:
    a = [
        Action("low", "fund", "B", "Review", "", None),
        Action("high", "stock", "A", "Sell", "", None),
    ]
    a.sort(key=lambda x: SEVERITY_ORDER[x.severity])
    assert [x.title for x in a] == ["Sell", "Review"]


def test_fund_chart(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    _import(client)
    _fake_sources(monkeypatch)
    codes = _codes(client)
    code = codes["Mirae Asset Large Cap Fund Regular Growth"]
    _mfapi(monkeypatch)
    client.get(f"/analysis/mf/{code}")  # downloads NAVs and the benchmark
    c = client.get(f"/analysis/mf/{code}/chart", params={"years": 3}).json()
    assert c["benchmark"]["label"] == "Nifty 50"
    assert c["fund"][0] == 100.0 and c["bench"][0] == 100.0
    assert len(c["dates"]) == len(c["fund"]) == len(c["bench"])
    span = (date.fromisoformat(c["dates"][-1]) - date.fromisoformat(c["dates"][0])).days
    assert span <= 3 * 366
    assert c["rolling"] and all(
        len(r["starts"]) == len(r["fund"]) == len(r["benchmark"]) for r in c["rolling"]
    )
    assert any("price index" in n for n in c["notes"])
    assert client.get("/analysis/mf/9999999/chart").status_code == 404


def test_fund_chart_without_navs(client: TestClient) -> None:
    c = client.get("/analysis/mf/118825/chart").json()
    assert c["fund"] == [] and "No NAV history" in c["notes"][0]


def test_csv_exports_end_with_the_disclaimer(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _import(client)
    _fake_sources(monkeypatch)
    _mfapi(monkeypatch)
    for path, first, n in (
        ("/export/stocks.csv", "Ticker", 11),
        ("/export/funds.csv", "AMFI code", 5),
    ):
        r = client.get(path)
        assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv")
        assert "attachment" in r.headers["content-disposition"]
        rows = list(csv.reader(io.StringIO(r.content.decode("utf-8-sig"))))
        assert rows[0][0] == first
        body = rows[1 : rows.index([])]
        assert len(body) == n
        assert rows[-1][0] == "Disclaimer" and "not investment advice" in rows[-1][1]
        assert all(len(row) == len(rows[0]) for row in body)
