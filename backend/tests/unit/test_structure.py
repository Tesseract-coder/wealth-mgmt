import pandas as pd
import pytest

from app.analysis.structure import candle_pattern, cluster, levels, nearest, pivots, recent_break
from app.core.profiles import get_profiles


@pytest.fixture
def sr():  # type: ignore[no-untyped-def]
    return get_profiles().technical.support_resistance.model_copy(
        update={"pivot_window": 2, "min_touches": 2, "cluster_pct": 1.5, "breakout_window_bars": 3}
    )


def frame(closes: list[float], spread: float = 0.5, volume: float = 1000.0) -> pd.DataFrame:
    c = pd.Series(closes, dtype="float64")
    return pd.DataFrame(
        {"open": c, "high": c + spread, "low": c - spread, "close": c, "volume": volume},
        index=pd.RangeIndex(len(c)),
    )


# A range between ~100 and ~110, touching each side three times.
RANGE = [
    105,
    107,
    110,
    107,
    104,
    101,
    100,
    102,
    106,
    109,
    110.5,
    108,
    104,
    101,
    100.5,
    103,
    106,
    109,
    110,
    107,
    105,
]


def test_pivots_are_strict_and_unconfirmed_tail_excluded() -> None:
    df = frame(RANGE)
    ph, pl = pivots(df["high"], df["low"], 2)
    assert list(ph.index) == [2, 10, 18]
    assert list(pl.index) == [6, 14]
    plateau = frame([1, 2, 5, 5, 2, 1, 0])
    ph2, _ = pivots(plateau["high"], plateau["low"], 2)
    assert ph2.empty  # equal highs side by side are not a single clean pivot


def test_cluster_groups_nearby_prices() -> None:
    pts = pd.Series([100.0, 101.0, 110.0, 100.5, 111.0], index=[1, 2, 3, 4, 5])
    got = cluster(pts, 1.5)
    assert [(round(p, 2), n, last) for p, n, last in got] == [(100.5, 3, 4), (110.5, 2, 5)]


def test_levels_and_nearest(sr) -> None:  # type: ignore[no-untyped-def]
    df = frame(RANGE)
    lv = levels(df, sr)
    kinds = {round(x.price): x.kind for x in lv}
    assert kinds == {100: "support", 111: "resistance"}
    sup, res = nearest(lv, 105.0)
    assert sup and res and sup.price < 105 < res.price and sup.touches == 2 and res.touches == 3


def test_breakout_detected_with_volume(sr) -> None:  # type: ignore[no-untyped-def]
    closes = RANGE + [108, 113]  # clears ~110.8 resistance by more than 1%
    df = frame(closes)
    df.loc[len(df) - 1, "volume"] = 3000.0
    vr = df["volume"] / df["volume"].shift(1).rolling(20, min_periods=1).mean()
    brk = recent_break(df, vr, sr)
    assert brk and brk.kind == "breakout" and brk.bars_ago == 0 and brk.volume_ratio == 3.0


def test_breakdown_and_no_false_break(sr) -> None:  # type: ignore[no-untyped-def]
    vr = pd.Series(1.0, index=range(len(RANGE) + 2))
    down = recent_break(frame(RANGE + [102, 97]), vr, sr)
    assert down and down.kind == "breakdown"
    inside = recent_break(frame(RANGE + [106, 108]), vr, sr)
    assert inside is None
    marginal = recent_break(frame(RANGE + [108, 111.2]), vr, sr)  # within the 1% buffer
    assert marginal is None


def _candles(rows: list[tuple[float, float, float, float]]) -> pd.DataFrame:
    return pd.DataFrame(rows, columns=["open", "high", "low", "close"])


T = get_profiles().technical.thresholds
LEAD = [(110.0, 111, 109, 110)] * 4


def test_engulfing_patterns() -> None:
    bull = _candles(LEAD + [(105, 106, 101, 102), (101, 107, 100, 106)])
    assert candle_pattern(bull, T) == "bullish_engulfing"
    bear = _candles(LEAD + [(102, 106, 101, 105), (106, 107, 100, 101)])
    assert candle_pattern(bear, T) == "bearish_engulfing"


def test_hammer_needs_prior_decline_and_doji() -> None:
    hammer = (100.0, 100.6, 95.0, 100.5)  # long lower shadow, tiny upper
    falling = _candles([(120.0, 121, 119, 120 - i * 3) for i in range(5)] + [hammer])
    assert candle_pattern(falling, T) == "hammer"
    rising = _candles([(80.0, 81, 79, 80 + i) for i in range(5)] + [hammer])
    assert candle_pattern(rising, T) != "hammer"
    doji = _candles(LEAD + [(110, 111, 109, 110.5), (110, 112, 108, 110.1)])
    assert candle_pattern(doji, T) == "doji"
    assert candle_pattern(_candles(LEAD[:3]), T) is None  # too short
