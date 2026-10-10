from datetime import date

import pandas as pd
import pytest
from sqlmodel import Session

from app.analysis.fundamental import (
    Metric,
    compute_metrics,
    observations,
    piotroski,
    quarter_yoy,
    sector_medians,
    store_metrics,
    ttm_net_income,
)
from app.analysis.statements import fill_missing, from_rows, from_yahoo
from app.core.profiles import get_profiles
from app.data import yahoo
from tests.unit.fundamentals_fixture import fake_fund_download

P = get_profiles()
CFG = P.fundamental
MEDIUM = P.risk_levels["medium"]


@pytest.fixture
def raw(monkeypatch: pytest.MonkeyPatch) -> dict:  # type: ignore[type-arg]
    monkeypatch.setattr(yahoo, "_fund_download", fake_fund_download())
    info, statements = yahoo.fetch_fundamentals("FAKE.NS")
    return {"info": info, "statements": statements}


def test_from_yahoo_converts_units_and_signs(raw) -> None:  # type: ignore[no-untyped-def]
    st = from_yahoo(raw["statements"])
    a = st.annual
    assert list(a.index) == [
        date(2023, 3, 31),
        date(2024, 3, 31),
        date(2025, 3, 31),
        date(2026, 3, 31),
    ]
    assert a["revenue"].iloc[-1] == pytest.approx(1331)  # ₹ crore
    assert a["capex"].iloc[-1] == pytest.approx(70)  # outflow made positive
    assert a["dividends_paid"].iloc[-1] == pytest.approx(45)
    assert a["free_cash_flow"].iloc[-1] == pytest.approx(110)  # derived: 180 − 70
    assert a["shares"].iloc[-1] == 1e8  # a count, not converted
    assert len(st.quarterly) == 5
    assert raw["info"]["longName"] == "Fake Industries Ltd"


def test_fetch_fundamentals_partial_and_total_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    def flaky(ticker: str, what: str) -> object:
        if what == "cashflow":
            raise ConnectionError("reset")
        return fake_fund_download()(ticker, what)

    monkeypatch.setattr(yahoo, "_fund_download", flaky)
    info, st = yahoo.fetch_fundamentals("FAKE.NS")
    assert st["cashflow"] == {} and st["income"]  # one statement missing is not fatal

    def dead(ticker: str, what: str) -> object:
        raise ConnectionError("down")

    monkeypatch.setattr(yahoo, "_fund_download", dead)
    from app.data.http import FetchError

    with pytest.raises(FetchError, match="no fundamentals"):
        yahoo.fetch_fundamentals("FAKE.NS")


def metrics_for(raw, price: float = 300.0, financial: bool = False, screener: dict | None = None):  # type: ignore[no-untyped-def]
    return compute_metrics(
        from_yahoo(raw["statements"]),
        price=price,
        price_basis="close ₹300",
        info=raw["info"],
        screener=screener or {},
        financial=financial,
    )


def test_metrics_values(raw) -> None:  # type: ignore[no-untyped-def]
    m, na = metrics_for(raw)
    v = {k: x.value for k, x in m.items()}
    assert v["market_cap"] == 3000  # 300 × 10 Cr shares
    # last 4 quarters are consecutive: Sep 25 + Dec 25 + Mar 26 + Jun 26
    assert v["pe"] == pytest.approx(round(3000 / (37 + 38 + 40 + 42), 2))
    assert "TTM to Jun 2026" in m["pe"].basis
    assert v["pb"] == pytest.approx(round(3000 / 1100, 2))
    assert v["ev_ebitda"] == pytest.approx(round((3000 + 250 - 50) / 285, 2))
    assert v["dividend_yield"] == pytest.approx(1.5)
    assert v["revenue_cagr_3y"] == pytest.approx(10.0)
    assert v["profit_cagr_3y"] == pytest.approx(round(((150 / 100) ** (1 / 3) - 1) * 100, 2))
    assert v["peg"] == pytest.approx(round(v["pe"] / v["profit_cagr_3y"], 2), abs=0.01)
    assert v["roe"] == pytest.approx(round(150 / 1050 * 100, 2))  # average equity
    assert v["roce"] == pytest.approx(round(230 / (1800 - 450) * 100, 2))
    assert v["op_margin"] == pytest.approx(round(220 / 1331 * 100, 2))
    assert v["op_margin_change"] == pytest.approx(round(220 / 1331 * 100 - 15.0, 2))
    assert v["debt_equity"] == pytest.approx(round(250 / 1100, 2))
    assert v["interest_coverage"] == pytest.approx(10.0)
    assert v["current_ratio"] == pytest.approx(round(760 / 450, 2))
    assert v["fcf"] == 110 and v["fcf_positive_years"] == 3
    assert v["revenue_qoq_yoy"] == pytest.approx(15.0)
    assert v["consecutive_loss_years"] == 0 and v["debt_change"] == -10
    assert any("CAGR 5y (needs 6 years of results, have 4)" in u for u in na)
    assert any("Ownership" in u for u in na)


def test_ttm_requires_consecutive_quarters() -> None:
    q = pd.DataFrame(
        {"net_income": [1.0, 2, 3, 4]},
        index=[date(2025, 3, 31), date(2025, 9, 30), date(2025, 12, 31), date(2026, 3, 31)],
    )
    assert ttm_net_income(q) == (None, None)  # Jun 2025 missing
    yoy, basis = quarter_yoy(q, "net_income")
    assert yoy == pytest.approx(300.0) and basis and "Mar 2026" in basis


def test_loss_making_and_currency_mismatch(raw) -> None:  # type: ignore[no-untyped-def]
    st = from_yahoo(raw["statements"])
    st.annual.loc[st.annual.index[-1], "net_income"] = -20
    st.quarterly["net_income"] = -5
    m, na = compute_metrics(
        st, price=300, price_basis="", info=raw["info"], screener={}, financial=False
    )
    assert "pe" not in m and any("loss-making" in u for u in na)
    assert m["consecutive_loss_years"].value == 1
    m2, na2 = compute_metrics(
        from_yahoo(raw["statements"]),
        price=300,
        price_basis="",
        info={**raw["info"], "financialCurrency": "USD"},
        screener={},
        financial=False,
    )
    assert "pe" not in m2 and any("USD" in u for u in na2)


def test_financials_skip_irrelevant_metrics(raw) -> None:  # type: ignore[no-untyped-def]
    m, _ = metrics_for(raw, financial=True)
    for k in (
        "ev_ebitda",
        "roce",
        "debt_equity",
        "interest_coverage",
        "current_ratio",
        "op_margin",
        "fcf",
    ):
        assert k not in m, k
    assert "roe" in m and "pb" in m and "net_margin" in m


def test_screener_fields_fill_gaps_but_dont_override(raw) -> None:  # type: ignore[no-untyped-def]
    scr = {
        "sales_growth_5y_pct": 12.0,
        "revenue_cagr_3y": 99,
        "promoter_pct": 55.0,
        "promoter_change_pct": -2.0,
        "pledge_pct": 30.0,
        "roe_pct": 99.0,
    }
    m, na = metrics_for(raw, screener=scr)
    assert m["revenue_cagr_5y"].value == 12.0 and m["revenue_cagr_5y"].basis == "Screener.in"
    assert m["roe"].value != 99.0  # computed value wins
    assert m["pledge_pct"].value == 30.0
    assert not any("Ownership" in u for u in na)


def test_piotroski_by_hand(raw) -> None:  # type: ignore[no-untyped-def]
    fs = piotroski(from_yahoo(raw["statements"]).annual, financial=False)
    passed = {t.name: t.passed for t in fs.tests}
    assert passed["Profitable (ROA > 0)"] is True  # 150 / 1700
    assert passed["ROA improving"] is True  # 130/1600=8.1% → 150/1700=8.8%
    assert passed["Cash flow exceeds profit (earnings quality)"] is True  # 180 > 150
    assert passed["Leverage not rising"] is True  # 180/1700 → 170/1800
    assert passed["Current ratio improving"] is True  # 700/440=1.59 → 760/450=1.69
    assert passed["No new shares issued"] is True
    assert passed["Gross margin improving"] is True  # 41.3% → 42.1%
    assert passed["Asset turnover improving"] is True  # 1210/1600 → 1331/1700
    assert fs.score == 9 and fs.computable == 9


def test_piotroski_partial_is_not_scored(raw) -> None:  # type: ignore[no-untyped-def]
    a = from_yahoo(raw["statements"]).annual.drop(columns=["gross_profit"])
    fs = piotroski(a, financial=False)
    assert fs.score is None and fs.computable == 8


def M(
    key: str, value: float, median: float | None = None, peers: int = 0, basis: str = ""
) -> Metric:
    return Metric(key, key, value, "", basis, median, peers)


def obs_for(*ms: Metric, fscore=None):  # type: ignore[no-untyped-def]
    return {
        o.key: o for o in observations({x.key: x for x in ms}, fscore, CFG, MEDIUM, "Medium", 25)
    }


def test_valuation_vs_sector_median() -> None:
    o = obs_for(M("pe", 15, 25, 10), M("pb", 6, 4, 10), M("ev_ebitda", 10, 10.5, 10))
    assert o["pe_cheap"].direction == "bullish" and "sector median 25.0" in o["pe_cheap"].text
    assert o["pb_rich"].direction == "bearish"
    assert o["ev_ebitda_inline"].direction == "neutral"
    o2 = obs_for(M("pe", 15, None, 2))
    assert "no sector median: 2 peer(s)" in o2["pe_value"].text


def test_debt_against_your_risk_limit() -> None:
    o = obs_for(M("debt_equity", 2.4))
    assert o["debt_above_limit"].text == "Debt/equity 2.40, above your limit of 1 (Medium risk)"
    assert obs_for(M("debt_equity", 0.1))["debt_low"].direction == "bullish"


def test_ownership_flags() -> None:
    o = obs_for(
        M("promoter_change", -2.1),
        M("promoter_pct", 48.0),
        M("pledge_pct", 30.0),
        M("fii_change", 1.5),
    )
    assert (
        o["promoter_selling"].direction == "bearish" and "now 48.0%" in o["promoter_selling"].text
    )
    assert "severe red flag" in o["pledge_severe"].text
    assert o["fii_change_up"].direction == "bullish"
    assert obs_for(M("pledge_pct", 12.0))["pledge_high"].direction == "bearish"


def test_growth_profitability_and_health_bands() -> None:
    o = obs_for(
        M("revenue_cagr_3y", 20),
        M("profit_cagr_3y", -4),
        M("roe", 22),
        M("roce", 5),
        M("interest_coverage", 1.5),
        M("current_ratio", 0.8),
        M("op_margin", 12.0),
        M("op_margin_change", -2.5, basis="FY2023→FY2026"),
    )
    assert o["revenue_cagr_3y_strong"].direction == "bullish"
    assert o["profit_cagr_3y_falling"].direction == "bearish"
    assert o["roe_good"].direction == "bullish" and o["roce_poor"].direction == "bearish"
    assert o["interest_cover_poor"].direction == "bearish"
    assert o["current_ratio_poor"].direction == "bearish"
    assert (
        o["op_margin_change_down"].text == "Operating margin down 2.5 pp to 12.0% (FY2023→FY2026)"
    )


def test_sector_medians_need_enough_peers(session: Session) -> None:
    for i, pe in enumerate([10, 12, 14, 16]):
        store_metrics(session, f"P{i}.NS", "nse:Test", {"pe": M("pe", pe)})
    session.commit()
    med, n = sector_medians(session, "nse:Test", "SELF.NS")["pe"]
    assert med is None and n == 4  # min peers is 5
    store_metrics(session, "P4.NS", "nse:Test", {"pe": M("pe", 40)})
    store_metrics(session, "SELF.NS", "nse:Test", {"pe": M("pe", 1000)})
    session.commit()
    assert sector_medians(session, "nse:Test", "SELF.NS")["pe"] == (14.0, 5)  # self excluded


def test_fill_missing_whole_columns_only() -> None:
    scr = from_rows(
        "screener", {"2025-03-31": {"revenue": 10.0}, "2026-03-31": {"revenue": 12.0}}, {}
    )
    yah = from_rows(
        "yahoo",
        {
            "2025-03-31": {"revenue": 99.0, "current_assets": 5.0},
            "2026-03-31": {"revenue": 99.0, "current_assets": 6.0},
        },
        {},
    )
    filled = fill_missing(scr, yah)
    assert filled == ["Current assets"]
    assert scr.annual["revenue"].tolist() == [10.0, 12.0]  # never overwritten
    assert scr.annual["current_assets"].tolist() == [5.0, 6.0]


def test_foreign_currency_statements_hide_amounts(raw) -> None:  # type: ignore[no-untyped-def]
    info = {**raw["info"], "financialCurrency": "USD"}
    m, na = compute_metrics(
        from_yahoo(raw["statements"]),
        price=300,
        price_basis="",
        info=info,
        screener={},
        financial=False,
    )
    assert "fcf" not in m and "fcf_positive_years" in m  # count is currency-free, the amount isn't
    assert m["debt_change"].unit == "USD (Yahoo units)"
    assert "roe" in m and "op_margin" in m  # ratios are currency-free
    assert any("Free cash flow amount (statements are in USD)" in u for u in na)
