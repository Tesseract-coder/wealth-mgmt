"""Indicators vs TA-Lib reference values (tests/fixtures/technical_reference.csv) + hand cases."""

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from app.analysis import indicators as ind

REF = pd.read_csv(Path(__file__).parents[1] / "fixtures" / "technical_reference.csv", index_col=0)
H, L, C, V = REF["high"], REF["low"], REF["close"], REF["volume"]


def assert_matches(
    mine: pd.Series, ref: pd.Series, *, tail: int | None = None, tol: float = 1e-6
) -> None:
    """Same NaN warm-up as the reference and the same values (CSV stores 10 significant digits)."""
    if tail is None:
        assert mine.first_valid_index() == ref.first_valid_index(), "warm-up length differs"
        both = ref.notna()
    else:
        both = ref.notna() & mine.notna()
        both[:-tail] = False
    np.testing.assert_allclose(mine[both].to_numpy(), ref[both].to_numpy(), rtol=tol, atol=tol)


@pytest.mark.parametrize(
    ("name", "compute"),
    [
        ("sma20", lambda: ind.sma(C, 20)),
        ("sma50", lambda: ind.sma(C, 50)),
        ("sma200", lambda: ind.sma(C, 200)),
        ("ema9", lambda: ind.ema(C, 9)),
        ("ema21", lambda: ind.ema(C, 21)),
        ("rsi14", lambda: ind.rsi(C, 14)),
        ("atr14", lambda: ind.atr(H, L, C, 14)),
        ("adx14", lambda: ind.adx(H, L, C, 14)["adx"]),
        ("plus_di14", lambda: ind.adx(H, L, C, 14)["plus_di"]),
        ("minus_di14", lambda: ind.adx(H, L, C, 14)["minus_di"]),
        ("roc20", lambda: ind.roc(C, 20)),
        ("obv", lambda: ind.obv(C, V)),
        ("stoch_d", lambda: ind.stochastic(H, L, C, 14, 3, 3)["d"]),
        ("bb_upper", lambda: ind.bollinger(C, 20, 2)["upper"]),
        ("bb_mid", lambda: ind.bollinger(C, 20, 2)["mid"]),
        ("bb_lower", lambda: ind.bollinger(C, 20, 2)["lower"]),
    ],
)
def test_matches_talib(name: str, compute) -> None:  # type: ignore[no-untyped-def]
    assert_matches(compute(), REF[name])


def test_stochastic_k_matches_talib_values() -> None:
    # TA-Lib only starts %K once %D exists (2 bars later); the values themselves agree.
    assert_matches(ind.stochastic(H, L, C)["k"], REF["stoch_k"], tail=len(REF))


@pytest.mark.parametrize(
    ("col", "name"), [("macd", "macd"), ("signal", "macd_signal"), ("hist", "macd_hist")]
)
def test_macd_converges_to_talib(col: str, name: str) -> None:
    # TA-Lib seeds the fast EMA later than a plain EMA(12); the difference decays away.
    # After 100+ bars the two agree to the fixture's precision.
    assert_matches(ind.macd(C)[col], REF[name], tail=250)


def test_sma_and_ema_by_hand() -> None:
    s = pd.Series([1.0, 2, 3, 4, 5, 6])
    assert ind.sma(s, 3).tolist()[2:] == [2.0, 3.0, 4.0, 5.0]
    e = ind.ema(s, 3)  # seed = mean(1,2,3) = 2, α = 0.5
    assert np.isnan(e[1]) and e[2] == 2.0 and e[3] == 3.0 and e[4] == 4.0


def test_ema_skips_leading_nans() -> None:
    s = pd.Series([np.nan, np.nan, 2.0, 4.0, 6.0, 8.0])
    e = ind.ema(s, 2)
    assert np.isnan(e[2]) and e[3] == 3.0 and e[4] == pytest.approx(5.0)


def test_rsi_edge_cases() -> None:
    up = pd.Series(np.arange(1.0, 30.0))
    assert ind.rsi(up, 14).iloc[-1] == 100.0
    flat = pd.Series([10.0] * 30)
    assert ind.rsi(flat, 14).iloc[-1] == 50.0
    short = pd.Series([1.0, 2.0, 3.0])
    assert ind.rsi(short, 14).isna().all()


def test_true_range_uses_previous_close() -> None:
    h = pd.Series([10.0, 12.0, 11.0])
    lo = pd.Series([9.0, 11.0, 7.0])
    c = pd.Series([9.5, 11.5, 8.0])
    tr = ind.true_range(h, lo, c)
    assert np.isnan(tr[0]) and tr[1] == 2.5 and tr[2] == 4.5  # gap up; then a wide range


def test_supertrend_follows_trend_and_flips() -> None:
    up_leg = [100.0 + i for i in range(30)]
    down_leg = [129.0 - 3 * i for i in range(20)]
    c = pd.Series(up_leg + down_leg)
    # Trending bars close near their extreme: highs in the up leg, lows in the down leg.
    h = pd.Series([x + 0.2 for x in up_leg] + [x + 1.8 for x in down_leg])
    lo = pd.Series([x - 1.8 for x in up_leg] + [x - 0.2 for x in down_leg])
    st = ind.supertrend(h, lo, c, n=5, mult=2.0)
    assert st["direction"].iloc[:5].isna().all()  # ATR warm-up
    up = st[st["direction"] > 0]
    down = st[st["direction"] < 0]
    assert (up["line"] < c[up.index]).all()  # line below price in an uptrend
    assert (down["line"] > c[down.index]).all()  # above price in a downtrend
    assert st["direction"].iloc[29] == 1 and st["direction"].iloc[-1] == -1
    # In an uptrend the line only ratchets up.
    rising = st["line"].iloc[6:30]
    assert (rising.diff().dropna() >= 0).all()


def test_supertrend_by_hand() -> None:
    # n=2, mult=1. TR: [nan, 2, 2, 5.5]; ATR(2) seeded at index 2 = 2, then (2+5.5)/2 = 3.75.
    h = pd.Series([11.0, 12.0, 13.0, 9.0])
    lo = pd.Series([9.0, 10.0, 11.0, 7.0])
    c = pd.Series([10.0, 11.0, 12.5, 7.5])
    st = ind.supertrend(h, lo, c, n=2, mult=1.0)
    # bar 2: hl2 12, bands 14 / 10; close 12.5 > hl2 → up, line = lower band 10
    assert st["direction"][2] == 1 and st["line"][2] == 10.0
    # bar 3: hl2 8, basic lower 4.25 < 10 and prev close 12.5 ≥ 10 → final lower stays 10;
    # close 7.5 < 10 → flips down; final upper: basic 11.75 < 14 → 11.75
    assert st["direction"][3] == -1 and st["line"][3] == 11.75


def test_obv_by_hand() -> None:
    c = pd.Series([10.0, 11.0, 11.0, 10.0])
    v = pd.Series([100.0, 50.0, 70.0, 30.0])
    assert ind.obv(c, v).tolist() == [100.0, 150.0, 150.0, 120.0]


def test_hist_volatility_annualises() -> None:
    rng = np.random.default_rng(1)
    c = pd.Series(100 * np.exp(np.cumsum(rng.normal(0, 0.01, 500))))
    hv = ind.hist_volatility(c, 400, 252).iloc[-1]
    assert hv == pytest.approx(0.01 * np.sqrt(252), rel=0.1)


def test_volume_ratio_excludes_today() -> None:
    v = pd.Series([100.0] * 20 + [300.0])
    assert ind.volume_ratio(v, 20).iloc[-1] == 3.0


def test_bars_since_cross() -> None:
    a = pd.Series([1.0, 2, 3, 4, 5])
    b = pd.Series([3.0, 3, 2.5, 2, 2])
    assert ind.bars_since_cross(a, b) == (2, 1)  # crossed above at index 2
    assert ind.bars_since_cross(a, a + 10) == (None, -1)  # never crossed, below
    assert ind.bars_since_cross(pd.Series([np.nan]), pd.Series([1.0])) == (None, 0)


def test_slope() -> None:
    assert ind.slope(pd.Series([1.0, 3, 5, 7]), 4) == pytest.approx(2.0)
    assert ind.slope(pd.Series([1.0, 2]), 4) is None


def test_bollinger_percent_b_and_flat_series() -> None:
    bb = ind.bollinger(pd.Series([5.0] * 25), 20, 2)
    assert bb["upper"].iloc[-1] == bb["lower"].iloc[-1] == 5.0
    assert np.isnan(bb["pct_b"].iloc[-1])  # zero width: undefined, not invented


def test_stochastic_zero_range_is_nan() -> None:
    flat = pd.Series([5.0] * 20)
    assert ind.stochastic(flat, flat, flat)["k"].isna().all()
