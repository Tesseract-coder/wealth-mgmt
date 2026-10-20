from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest

from app.analysis import mf
from app.analysis.returns import (
    beta,
    cagr,
    risk_stats,
    rolling_vs,
    trailing_cagr,
    value_on,
    xirr,
)
from app.core.profiles import get_profiles
from app.data.amfi import Scheme


def daily(start: date, days: int, rate_pct: float, base: float = 100.0) -> pd.Series:
    """A series growing at a constant annual rate, one point a calendar day."""
    idx = pd.date_range(pd.Timestamp(start), periods=days, freq="D")
    t = np.arange(days) / 365.25
    return pd.Series(base * (1 + rate_pct / 100) ** t, index=idx)


def test_cagr_and_trailing_cagr() -> None:
    assert cagr(100, 121, 365.25 * 2) == pytest.approx(10)
    assert cagr(0, 10, 100) is None
    s = daily(date(2019, 1, 1), 365 * 6, 12)
    for y in (1, 3, 5):
        assert trailing_cagr(s, y) == pytest.approx(12, abs=0.05)
    assert trailing_cagr(daily(date(2024, 1, 1), 400, 12), 3) is None  # too short
    assert value_on(s, date(2018, 1, 1)) is None


def test_xirr_known_values() -> None:
    # 1,000 in, 1,100 out a year later: 10%
    assert xirr([(date(2025, 1, 1), -1000), (date(2026, 1, 1), 1100)]) == pytest.approx(
        10, abs=0.05
    )
    # SIP of 1,000 at month starts, valued at 12,500 after a year
    flows = [(date(2025, m, 1), -1000.0) for m in range(1, 13)] + [(date(2026, 1, 1), 12500.0)]
    r = xirr(flows)
    assert r is not None and 7 < r < 9
    assert xirr([(date(2025, 1, 1), -1000)]) is None
    assert xirr([]) is None


def test_risk_stats() -> None:
    rng = np.random.default_rng(3)
    idx = pd.bdate_range("2022-01-03", periods=800)
    r = rng.normal(0.0005, 0.01, len(idx))
    s = pd.Series(100 * np.cumprod(1 + r), index=idx)
    st = risk_stats(s, 6.5, 3, 365)
    assert st is not None
    assert st.volatility == pytest.approx(
        float(np.std(r[1:], ddof=1) * np.sqrt(len(r) / (st.years))) * 100, rel=0.05
    )
    assert st.max_drawdown < 0 and st.drawdown_peak <= st.drawdown_trough
    assert st.sharpe is not None and st.sortino is not None
    assert risk_stats(s.iloc[:100], 6.5, 3, 365) is None


def test_rolling_vs_benchmark() -> None:
    f = daily(date(2018, 1, 1), 365 * 6, 14)
    b = daily(date(2018, 1, 1), 365 * 6, 10)
    r = rolling_vs(f, b, 3, 30)
    assert r is not None and r.windows > 30
    assert r.fund_avg == pytest.approx(14, abs=0.1) and r.bench_avg == pytest.approx(10, abs=0.1)
    assert r.avg_excess == pytest.approx(4, abs=0.1) and r.beat_share == 1.0
    assert rolling_vs(f.iloc[:300], b, 3, 30) is None


def test_beta_helper() -> None:
    rng = np.random.default_rng(5)
    idx = pd.bdate_range("2024-01-01", periods=300)
    rb = rng.normal(0, 0.01, 300)
    b = pd.Series(100 * np.cumprod(1 + rb), index=idx)
    a = pd.Series(100 * np.cumprod(1 + 0.5 * rb), index=idx)
    val, n = beta(a, b, 252, 120)
    assert val == pytest.approx(0.5, abs=1e-6) and n == 252


@pytest.mark.parametrize(
    ("name", "category", "label"),
    [
        ("Mirae Asset Large Cap Fund", "Equity Schemes - Large Cap Fund", "Nifty 50"),
        ("UTI Nifty 50 Index Fund", "Other Scheme - Index Funds", "Nifty 50"),
        ("UTI Nifty Next 50 Index Fund", "Other Scheme - Index Funds", "Nifty Next 50"),
        ("Kotak Emerging Equity", "Equity Scheme - Mid Cap Fund", "Nifty Midcap 150"),
        ("SBI Small Cap Fund", "Equity Scheme - Small Cap Fund", "Nifty Smallcap 250"),
        (
            "Mirae Emerging Bluechip",
            "Equity Scheme - Large & Mid Cap Fund",
            "Nifty 500 (proxy for LargeMidcap 250)",
        ),
        ("Parag Parikh Flexi Cap", "Equity Scheme - Flexi Cap Fund", "Nifty 500"),
        ("Axis ELSS Tax Saver", "Equity Schemes - ELSS- Tax Saver Fund", "Nifty 500"),
        ("SBI Banking & Financial Services", "Equity Scheme - Sectoral/ Thematic", "Nifty Bank"),
    ],
)
def test_benchmark_mapping(name: str, category: str, label: str) -> None:
    b = mf.benchmark_for(name, category, get_profiles().mf)
    assert b is not None and b.label == label


def test_no_benchmark_for_debt_and_other() -> None:
    cfg = get_profiles().mf
    assert (
        mf.benchmark_for("SBI Banking & PSU Debt Fund", "Debt Scheme - Banking and PSU Fund", cfg)
        is None
    )
    assert mf.asset_class_of("Debt Scheme - Liquid Fund", cfg) == "debt"
    assert mf.asset_class_of("Hybrid Scheme - Arbitrage Fund", cfg) == "hybrid"
    assert mf.asset_class_of("Other Scheme - FoF Overseas", cfg) == "other"
    assert mf.asset_class_of("Equity Scheme - Flexi Cap Fund", cfg) == "equity"
    assert mf.benchmark_for("Some Thematic Fund", "Equity Scheme - Sectoral/ Thematic", cfg) is None


def _signal(**kw):  # type: ignore[no-untyped-def]
    cfg = get_profiles().mf
    base = dict(
        has_nav=True,
        plan="direct",
        twin=None,
        gap=None,
        gap_basis="",
        rolling=[],
        returns={1: None, 3: None, 5: None},
        bench_returns={1: None, 3: None, 5: None},
        bench=cfg.benchmarks[1],
        risk=None,
        bench_risk=None,
        ter=None,
        acls="equity",
        overlaps=[],
        peers=[],
        cfg=cfg,
    )
    base.update(kw)
    return mf.fund_signal(**base)  # type: ignore[arg-type]


def _roll(excess: float, beat: float):  # type: ignore[no-untyped-def]
    from app.analysis.returns import Rolling

    return Rolling(
        3,
        100,
        10 + excess,
        10,
        excess,
        beat,
        excess - 2,
        excess + 2,
        date(2020, 1, 1),
        date(2022, 1, 1),
    )


def test_fund_signal_rules() -> None:
    twin = Scheme(
        "2", "X Direct", None, None, "direct", "growth", 10, date(2026, 10, 9), None, None
    )
    assert _signal(has_nav=False)[0] == "no_signal"
    sig, rule, reasons = _signal(plan="regular", twin=twin, gap=1.04, gap_basis="Over 3 years")
    assert sig == "switch" and "Direct plan (2)" in rule and "+1.04 pp" in rule
    assert "exit load" in rule
    assert _signal(rolling=[_roll(-4.0, 0.1)])[0] == "switch"
    assert _signal(rolling=[_roll(-4.0, 0.5)])[0] == "review"  # lags, but often beats
    assert _signal(rolling=[_roll(-1.5, 0.4)])[0] == "review"
    sig, _, reasons = _signal(rolling=[_roll(2.0, 0.8)])
    assert sig == "continue" and any(
        r.direction == "bullish" and "Rolling 3-year" in r.text for r in reasons
    )
    assert (
        _signal(returns={1: -10.0, 3: None, 5: None}, bench_returns={1: 0.0, 3: None, 5: None})[0]
        == "review"
    )
    assert _signal(ter=1.8)[0] == "review" and _signal(ter=0.6)[0] == "continue"
    assert _signal(ter=0.8, acls="debt")[0] == "review"
    over = mf.Overlap("3", "Other Fund", 62.0, 30, False, "")
    sig, rule, _ = _signal(overlaps=[over])
    assert sig == "review" and "62% of its portfolio overlaps with Other Fund" in rule
    sig, rule, _ = _signal(peers=["A", "B"])
    assert sig == "review" and "3 funds in the same segment" in rule
    assert _signal(peers=["A"])[0] == "continue"


def test_overlap_formula() -> None:
    cfg = get_profiles().mf
    today = date(2026, 10, 10)
    a = mf.FundPortfolio(
        "1", today - timedelta(days=10), {"isin:A": 10, "isin:B": 5, "isin:C": 85}, 100
    )
    b = mf.FundPortfolio(
        "2", today - timedelta(days=10), {"isin:A": 4, "isin:B": 8, "isin:D": 88}, 100
    )
    pct, common, approx, _ = mf.overlap(a, b, cfg, today)
    assert (pct, common, approx) == (9.0, 2, False)  # min(10,4) + min(5,8)
    old = mf.FundPortfolio("2", date(2025, 1, 1), b.weights, 60)
    _, _, approx, note = mf.overlap(a, old, cfg, today)
    assert approx and "cover only 60%" in note and "Jan 2025" in note


def test_short_scheme_name_drops_plan_and_option() -> None:
    from app.analysis.mf import short_scheme_name

    assert short_scheme_name("Axis ELSS- Tax Saver Fund - Direct Plan - Growth Option") == (
        "Axis ELSS- Tax Saver Fund"
    )
    assert short_scheme_name("Quant ELSS Tax Saver Fund - Growth Option - Direct Plan") == (
        "Quant ELSS Tax Saver Fund"
    )
    assert (
        short_scheme_name("HDFC Index Fund-NIFTY 50 Plan-Direct Plan")
        == "HDFC Index Fund-NIFTY 50 Plan"
    )
    assert short_scheme_name("Plain Fund") == "Plain Fund"
