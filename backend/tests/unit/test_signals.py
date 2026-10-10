from datetime import date

import numpy as np
import pandas as pd
import pytest

from app.analysis import fundamental as fa
from app.analysis.signals import (
    Flag,
    PriceLevels,
    beta_vs,
    decide,
    flags_for,
    price_levels,
)
from app.core.profiles import get_profiles
from app.data.freshness import Freshness

P = get_profiles


def _decide(score: float | None, flags: list[Flag] | None = None, weight: float | None = 0.05):
    risk = P().risk_levels["medium"]  # buy 70, max weight 12%
    return decide(
        score, flags or [], weight, risk.max_weight_per_stock, risk.buy_threshold, P(), "Medium"
    )


RED = Flag("debt_above_limit", False, "Debt/equity 2.40, above your limit of 1")
SEVERE = Flag("pledge_severe", True, "30% pledged")


@pytest.mark.parametrize(
    ("score", "flags", "weight", "expected"),
    [
        (85, [], 0.05, "strong_buy"),  # ≥ 70 + 10
        (80, [], 0.05, "strong_buy"),
        (79.9, [], 0.05, "buy"),
        (70, [], 0.05, "buy"),
        (85, [RED], 0.05, "hold"),  # red flag blocks buying
        (69.9, [], 0.05, "hold"),
        (45, [], 0.05, "hold"),
        (44.9, [], 0.05, "reduce"),
        (35, [], 0.05, "reduce"),
        (34.9, [], 0.05, "sell"),
        (85, [], 0.13, "reduce"),  # over the 12% max weight
        (85, [SEVERE], 0.05, "sell"),
        (None, [], 0.05, "no_signal"),
        (None, [SEVERE], 0.05, "sell"),
        (None, [], 0.2, "reduce"),
        (85, [], None, "strong_buy"),  # not held
    ],
)
def test_signal_rules(
    score: float | None, flags: list[Flag], weight: float | None, expected: str
) -> None:
    sig, rule = _decide(score, flags, weight)
    assert sig == expected, rule
    assert rule


def test_rule_text_explains() -> None:
    assert "buy threshold 70" in _decide(72)[1]
    assert "red flags" in _decide(85, [RED])[1] and "Debt/equity" in _decide(85, [RED])[1]
    assert "12% limit" in _decide(85, [], 0.13)[1]
    assert _decide(85, [SEVERE])[1] == "Severe red flag: 30% pledged"


def frame(closes: list[float], spread: float = 1.0) -> pd.DataFrame:
    idx = pd.date_range("2026-01-01", periods=len(closes), freq="B")
    c = pd.Series(closes, index=idx)
    return pd.DataFrame(
        {"open": c, "high": c + spread, "low": c - spread, "close": c, "volume": 1000.0}
    )


def test_price_levels_atr_stop_and_targets() -> None:
    df = frame([100.0] * 40)  # true range 2 every bar → ATR 2
    lv = price_levels(
        df,
        "1d",
        atr_period=14,
        multiple=2,
        lookback=22,
        r_multiples=[2, 3],
        resistance=110.0,
    )
    assert lv is not None
    assert lv.atr == pytest.approx(2.0)
    assert lv.trailing_stop == pytest.approx(101 - 4)  # highest high − 2 × ATR
    assert lv.entry_stop == pytest.approx(96) and lv.risk_per_share == pytest.approx(4)
    assert [(t.label, t.price) for t in lv.targets] == [
        ("Nearest resistance", 110.0),
        ("2R", 108.0),
        ("3R", 112.0),
    ]
    assert not lv.stop_breached and "highest high of the last 22 days" in lv.basis


def test_price_levels_breach_and_short_history() -> None:
    df = frame([100.0] * 30 + [90.0])  # a drop well past 2 × ATR below the recent high
    lv = price_levels(
        df, "1d", atr_period=14, multiple=2, lookback=22, r_multiples=[2], resistance=95.0
    )
    assert lv is not None and lv.stop_breached
    assert [t.label for t in lv.targets] == ["Nearest resistance", "2R"]
    below = price_levels(
        df, "1d", atr_period=14, multiple=2, lookback=22, r_multiples=[2], resistance=80.0
    )
    assert below is not None and [t.label for t in below.targets] == ["2R"]
    assert (
        price_levels(
            frame([100.0] * 10),
            "1d",
            atr_period=14,
            multiple=2,
            lookback=22,
            r_multiples=[2],
            resistance=None,
        )
        is None
    )


def test_beta_vs_benchmark() -> None:
    rng = np.random.default_rng(1)
    rets = rng.normal(0, 0.01, 300)
    bench = pd.Series(100 * np.cumprod(1 + rets))
    stock = pd.Series(100 * np.cumprod(1 + 2 * rets))
    idx = pd.date_range("2025-01-01", periods=300, freq="B")
    b = pd.DataFrame({"close": bench.to_numpy()}, index=idx)
    s = pd.DataFrame({"close": stock.to_numpy()}, index=idx)
    beta, n = beta_vs(s, b, 252, 120)
    assert beta == pytest.approx(2.0, abs=1e-6) and n == 252
    assert beta_vs(s.iloc[:50], b, 252, 120) == (None, 49)
    assert beta_vs(s, None, 252, 120) == (None, 0)


def _fund(
    obs: list[fa.Observation], metrics: dict[str, float] | None = None
) -> fa.FundamentalReport:
    m = {k: fa.Metric(k, k, v, "", "test") for k, v in (metrics or {}).items()}
    return fa.FundamentalReport(
        "X.NS",
        "X",
        "Industrials",
        "nse:Industrials",
        False,
        "yahoo",
        date(2026, 3, 31),
        Freshness("fresh", "ok"),
        m,
        None,
        obs,
        [],
    )


def _levels(breached: bool) -> PriceLevels:
    return PriceLevels("1d", 90, "2026-10-09", 2, 2, 97, 86, breached, 4, [], "")


def test_flags_for() -> None:
    p = P()
    obs = [
        fa.Observation("pledge_high", "ownership", "bearish", "12% pledged"),
        fa.Observation("debt_above_limit", "health", "bearish", "Debt/equity 2.4"),
    ]
    fund = _fund(obs, {"consecutive_loss_years": 2, "debt_change": 50})
    flags = flags_for(fund, _levels(True), 1.5, 1.3, True, "Banks", 0.35, 0.30, p)
    by = {f.key: f for f in flags}
    assert by["stop_breached"].severe and by["losses_rising_debt"].severe
    assert not by["pledge_high"].severe and not by["debt_above_limit"].severe
    assert (
        "Beta 1.50" in by["beta_high"].text and "Banks is 35.0%" in by["sector_concentration"].text
    )

    # Not held, or a style that doesn't exit on stops: the breach is only a warning.
    assert not flags_for(_fund([]), _levels(True), None, None, False, None, None, 0.3, p)[0].severe
    warn = flags_for(
        _fund([]),
        _levels(True),
        None,
        None,
        True,
        None,
        None,
        0.3,
        p,
        stop_exits=False,
        style_label="Long-term investing",
    )[0]
    assert not warn.severe and "Long-term investing style doesn't exit" in warn.text
    # No limit (High risk has no max beta), no breach, losses without rising debt: no flags.
    calm = flags_for(
        _fund([], {"consecutive_loss_years": 3, "debt_change": -5}),
        _levels(False),
        2.0,
        None,
        True,
        "Banks",
        0.2,
        0.3,
        p,
    )
    assert calm == []
    sev = flags_for(
        _fund([fa.Observation("pledge_severe", "ownership", "bearish", "30% pledged")]),
        None,
        None,
        None,
        True,
        None,
        None,
        0.3,
        p,
    )
    assert [(f.key, f.severe) for f in sev] == [("pledge_severe", True)]
