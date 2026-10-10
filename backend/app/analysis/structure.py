"""Price structure: swing pivots → support/resistance levels, breakouts, simple candle patterns."""

from dataclasses import dataclass
from typing import Any, Literal

import numpy as np
import pandas as pd

from app.core.profiles import SupportResistance, TechnicalThresholds


@dataclass(frozen=True)
class Level:
    price: float
    touches: int
    kind: Literal["support", "resistance"]
    last_touch: Any  # index label of the most recent pivot in the cluster


def pivots(high: pd.Series, low: pd.Series, k: int) -> tuple[pd.Series, pd.Series]:
    """Swing highs/lows: a bar whose high (low) is the strict extreme of the k bars each side.

    The last k bars can't be confirmed yet and are never pivots."""
    win = 2 * k + 1
    hmax = high.rolling(win, center=True, min_periods=win).max()
    lmin = low.rolling(win, center=True, min_periods=win).min()
    is_h = high.eq(hmax)
    is_l = low.eq(lmin)
    # Strict: reject plateaus where the extreme repeats inside the window.
    h_count = high.rolling(win, center=True, min_periods=win).apply(
        lambda w: float((w == w.max()).sum()), raw=True
    )
    l_count = low.rolling(win, center=True, min_periods=win).apply(
        lambda w: float((w == w.min()).sum()), raw=True
    )
    return high[is_h & h_count.eq(1)], low[is_l & l_count.eq(1)]


def cluster(points: pd.Series, pct: float) -> list[tuple[float, int, Any]]:
    """Greedy clustering of pivot prices: a point joins the current cluster if it is within
    pct% of the cluster's running mean. Returns (mean price, touches, last touch label)."""
    if points.empty:
        return []
    ordered = sorted(zip(points.to_numpy(dtype="float64"), points.index, strict=True))
    clusters: list[list[tuple[float, Any]]] = [[ordered[0]]]
    for price, label in ordered[1:]:
        mean = float(np.mean([p for p, _ in clusters[-1]]))
        if abs(price - mean) / mean * 100 <= pct:
            clusters[-1].append((price, label))
        else:
            clusters.append([(price, label)])
    out = []
    for c in clusters:
        labels = [lab for _, lab in c]
        out.append((float(np.mean([p for p, _ in c])), len(c), max(labels)))
    return out


def levels(df: pd.DataFrame, cfg: SupportResistance) -> list[Level]:
    """Support/resistance levels relative to the last close, strongest (most touches) first."""
    window = df.iloc[-cfg.lookback_bars :]
    if len(window) < 2 * cfg.pivot_window + 1:
        return []
    ph, pl = pivots(window["high"], window["low"], cfg.pivot_window)
    close = float(window["close"].iloc[-1])
    out = []
    for price, touches, last in cluster(pd.concat([ph, pl]), cfg.cluster_pct):
        if touches >= cfg.min_touches:
            kind: Literal["support", "resistance"] = "support" if price < close else "resistance"
            out.append(Level(round(price, 2), touches, kind, last))
    return sorted(out, key=lambda lv: (-lv.touches, abs(lv.price - close)))


def nearest(levels_: list[Level], close: float) -> tuple[Level | None, Level | None]:
    sup = [lv for lv in levels_ if lv.price < close]
    res = [lv for lv in levels_ if lv.price > close]
    return (
        max(sup, key=lambda lv: lv.price) if sup else None,
        min(res, key=lambda lv: lv.price) if res else None,
    )


@dataclass(frozen=True)
class Break:
    kind: Literal["breakout", "breakdown"]
    level: float
    bars_ago: int
    volume_ratio: float | None


def recent_break(df: pd.DataFrame, vol_ratio: pd.Series, cfg: SupportResistance) -> Break | None:
    """A close through a level that existed *before* the move, within the last few bars."""
    n = len(df)
    for ago in range(cfg.breakout_window_bars):
        i = n - 1 - ago
        if i < 1:
            break
        prior = levels(df.iloc[:i], cfg)  # levels known before bar i
        prev_close, close = float(df["close"].iloc[i - 1]), float(df["close"].iloc[i])
        buf = cfg.breakout_buffer_pct / 100
        vr = vol_ratio.iloc[i]
        vr_f = None if pd.isna(vr) else float(vr)
        for lv in prior:
            if prev_close <= lv.price < close / (1 + buf):
                return Break("breakout", lv.price, ago, vr_f)
            if prev_close >= lv.price > close / (1 - buf):
                return Break("breakdown", lv.price, ago, vr_f)
    return None


Candle = Literal["bullish_engulfing", "bearish_engulfing", "hammer", "doji"]


def candle_pattern(df: pd.DataFrame, t: TechnicalThresholds) -> Candle | None:
    """Pattern on the latest bar. Minor input only."""
    if len(df) < 6:
        return None
    o, h, lo, c = (float(df[k].iloc[-1]) for k in ("open", "high", "low", "close"))
    po, pc = float(df["open"].iloc[-2]), float(df["close"].iloc[-2])
    rng = h - lo
    body = abs(c - o)
    if rng <= 0:
        return None
    if pc < po and c > o and o <= pc and c >= po and body > abs(pc - po):
        return "bullish_engulfing"
    if pc > po and c < o and o >= pc and c <= po and body > abs(pc - po):
        return "bearish_engulfing"
    lower = min(o, c) - lo
    upper = h - max(o, c)
    fell = c < float(df["close"].iloc[-6])
    if body > 0 and lower >= t.candle_hammer_shadow * body and upper <= body and fell:
        return "hammer"
    if body <= t.candle_doji_body * rng:
        return "doji"
    return None
