"""Technical engine: indicators → plain-English observations, per timeframe.

Every observation carries the numbers that produced it, a direction (bullish / bearish /
neutral) and its category. Anything that can't be computed (too few bars, no volume, no
delivery data) is listed under `unavailable` with the reason — never estimated.

Phase 6 turns these observations into the technical score; this module only reads the chart.
"""

import math
from dataclasses import dataclass, field
from datetime import date
from typing import Literal

import numpy as np
import pandas as pd

from app.analysis import indicators as ind
from app.analysis.structure import Level, candle_pattern, levels, nearest, recent_break
from app.core.formatting import IST, format_inr
from app.core.profiles import StyleKey, TechnicalConfig, get_profiles
from app.data.freshness import Freshness
from app.data.provider import DataProvider

Direction = Literal["bullish", "bearish", "neutral"]
Category = Literal[
    "trend", "momentum", "volatility", "volume", "structure", "relative_strength", "pattern"
]
Interval = Literal["15m", "1h", "1d", "1wk", "1mo"]
INTRADAY: tuple[Interval, ...] = ("15m", "1h")

UNIT = {"15m": "15-min bar", "1h": "hour", "1d": "day", "1wk": "week", "1mo": "month"}
# Bars per year, for annualising volatility. NSE trades 6h15m: Yahoo gives 25×15m / 7×1h bars.
BARS_PER_YEAR = {"15m": 252 * 25, "1h": 252 * 7, "1d": 252, "1wk": 52, "1mo": 12}


@dataclass(frozen=True)
class Observation:
    key: str
    category: Category
    direction: Direction
    text: str
    value: float | None = None
    minor: bool = False  # candlestick patterns and other weak evidence


@dataclass
class FrameAnalysis:
    values: dict[str, float | None]
    observations: list[Observation]
    unavailable: list[str]
    levels: list[Level]


@dataclass
class TimeframeReport:
    interval: Interval
    bars: int
    as_of: str | None
    last_close: float | None
    last_complete: bool
    freshness: Freshness
    analysis: FrameAnalysis
    notes: list[str] = field(default_factory=list)


@dataclass
class TechnicalReport:
    ticker: str
    label: str
    style: StyleKey | None
    timeframes: list[TimeframeReport]
    context: FrameAnalysis  # daily-based: 52-week range, relative strength, delivery
    fetch_errors: list[str]
    notes: list[str]


def _f(v: object) -> float | None:
    if v is None:
        return None
    try:
        x = float(v)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return None if math.isnan(x) or math.isinf(x) else x


def _last(s: pd.Series) -> float | None:
    return _f(s.iloc[-1]) if len(s) else None


def _r(v: float | None, nd: int = 2) -> float | None:
    return None if v is None else round(v, nd)


class _Fmt:
    def __init__(self, is_index: bool) -> None:
        self.is_index = is_index

    def px(self, v: float | None) -> str:
        if v is None:
            return "—"
        return f"{v:,.2f}" if self.is_index else format_inr(v)


def _need(name: str, needed: int, have: int) -> str:
    return f"{name} (needs {needed} bars, have {have})"


def analyse_frame(
    df: pd.DataFrame, interval: Interval, cfg: TechnicalConfig, *, is_index: bool = False
) -> FrameAnalysis:
    """Pure function over an OHLCV frame (columns open/high/low/close/volume, oldest first)."""
    p, t = cfg.periods, cfg.thresholds
    fmt = _Fmt(is_index)
    unit = UNIT[interval]
    obs: list[Observation] = []
    na: list[str] = []
    vals: dict[str, float | None] = {}
    n = len(df)
    if n < 2:
        return FrameAnalysis({}, [], [f"Not enough price history ({n} bars)"], [])
    h, lo, c = df["high"], df["low"], df["close"]
    vol = df["volume"] if "volume" in df else pd.Series(np.nan, index=df.index)
    close = float(c.iloc[-1])
    prev_close = float(c.iloc[-2])
    vals["close"] = close

    def add(
        key: str,
        cat: Category,
        d: Direction,
        text: str,
        v: float | None = None,
        minor: bool = False,
    ) -> None:
        obs.append(Observation(key, cat, d, text, _r(v), minor))

    # ---------------------------------------------------------------- trend
    smas = {k: ind.sma(c, k) for k in p.sma}
    for k, s in smas.items():
        vals[f"sma{k}"] = _r(_last(s))
        if vals[f"sma{k}"] is None:
            na.append(_need(f"SMA {k}", k, n))
    for k in sorted(p.sma, reverse=True)[:2]:  # 200 and 50
        m = _last(smas[k])
        if m:
            pct = (close / m - 1) * 100
            d: Direction = "bullish" if pct > 0 else "bearish"
            side = "above" if pct > 0 else "below"
            add(
                f"price_vs_sma{k}",
                "trend",
                d,
                f"Close {fmt.px(close)} is {abs(pct):.1f}% {side} its {k}-{unit} SMA ({fmt.px(m)})",
                pct,
            )
    if _last(smas[50]) is not None and _last(smas[200]) is not None:
        since, side_now = ind.bars_since_cross(smas[50], smas[200])
        if since is not None and since < t.cross_lookback_bars:
            if side_now > 0:
                add(
                    "golden_cross",
                    "trend",
                    "bullish",
                    f"Golden cross: 50-{unit} SMA crossed above the 200-{unit} SMA "
                    f"{since} bar(s) ago",
                )
            else:
                add(
                    "death_cross",
                    "trend",
                    "bearish",
                    f"Death cross: 50-{unit} SMA crossed below the 200-{unit} SMA "
                    f"{since} bar(s) ago",
                )
        elif side_now > 0:
            add(
                "sma50_above_sma200",
                "trend",
                "bullish",
                f"50-{unit} SMA is above the 200-{unit} SMA: long-term uptrend structure",
            )
        elif side_now < 0:
            add(
                "sma50_below_sma200",
                "trend",
                "bearish",
                f"50-{unit} SMA is below the 200-{unit} SMA: long-term downtrend structure",
            )

    fast_n, slow_n = p.ema
    ef, es = ind.ema(c, fast_n), ind.ema(c, slow_n)
    vals[f"ema{fast_n}"], vals[f"ema{slow_n}"] = _r(_last(ef)), _r(_last(es))
    if vals[f"ema{slow_n}"] is None:
        na.append(_need(f"EMA {slow_n}", slow_n, n))
    else:
        since, side_now = ind.bars_since_cross(ef, es)
        fresh = since is not None and since < t.cross_lookback_bars
        if side_now > 0:
            add(
                "ema_fast_above_slow",
                "trend",
                "bullish",
                f"EMA {fast_n} {'crossed above' if fresh else 'is above'} EMA {slow_n}"
                + (f" {since} bar(s) ago" if fresh else "")
                + ": short-term trend up",
            )
        elif side_now < 0:
            add(
                "ema_fast_below_slow",
                "trend",
                "bearish",
                f"EMA {fast_n} {'crossed below' if fresh else 'is below'} EMA {slow_n}"
                + (f" {since} bar(s) ago" if fresh else "")
                + ": short-term trend down",
            )

    a = ind.adx(h, lo, c, p.adx)
    adx_v, pdi, mdi = _last(a["adx"]), _last(a["plus_di"]), _last(a["minus_di"])
    vals.update(adx=_r(adx_v), plus_di=_r(pdi), minus_di=_r(mdi))
    if adx_v is None or pdi is None or mdi is None:
        na.append(_need(f"ADX {p.adx}", 2 * p.adx, n))
    else:
        di = f"(+DI {pdi:.1f} vs −DI {mdi:.1f})"
        if adx_v >= t.adx_trending:
            up = pdi > mdi
            add(
                "adx_strong_trend",
                "trend",
                "bullish" if up else "bearish",
                f"ADX {adx_v:.1f}: strong trend, {'buyers' if up else 'sellers'} in control {di}",
                adx_v,
            )
        elif adx_v < t.adx_weak:
            add("adx_no_trend", "trend", "neutral", f"ADX {adx_v:.1f}: no clear trend {di}", adx_v)
        else:
            add(
                "adx_developing",
                "trend",
                "neutral",
                f"ADX {adx_v:.1f}: trend developing {di}",
                adx_v,
            )

    st = ind.supertrend(h, lo, c, p.supertrend.period, p.supertrend.multiplier)
    st_line, st_dir = _last(st["line"]), _last(st["direction"])
    vals.update(supertrend=_r(st_line), supertrend_dir=st_dir)
    stp = f"Supertrend ({p.supertrend.period}, {p.supertrend.multiplier:g})"
    if st_line is None or st_dir is None:
        na.append(_need(stp, p.supertrend.period + 1, n))
    else:
        dirs = st["direction"].dropna().to_numpy()
        flips = np.flatnonzero(dirs[1:] != dirs[:-1])
        since = int(len(dirs) - 1 - (flips[-1] + 1)) if len(flips) else None
        recent = since is not None and since < t.cross_lookback_bars
        if st_dir > 0:
            add(
                "supertrend_up",
                "trend",
                "bullish",
                f"{stp} {'turned up ' + str(since) + ' bar(s) ago' if recent else 'is up'}; "
                f"it flips down below {fmt.px(st_line)}",
                st_line,
            )
        else:
            add(
                "supertrend_down",
                "trend",
                "bearish",
                f"{stp} {'turned down ' + str(since) + ' bar(s) ago' if recent else 'is down'}; "
                f"it flips up above {fmt.px(st_line)}",
                st_line,
            )

    # ---------------------------------------------------------------- momentum
    r = _last(ind.rsi(c, p.rsi))
    vals[f"rsi{p.rsi}"] = _r(r)
    lo_band, hi_band = t.rsi_neutral_band
    if r is None:
        na.append(_need(f"RSI {p.rsi}", p.rsi + 1, n))
    elif r <= t.rsi_oversold:
        add(
            "rsi_oversold",
            "momentum",
            "bullish",
            f"RSI({p.rsi}) {r:.1f}: oversold (at or below {t.rsi_oversold:g})",
            r,
        )
    elif r >= t.rsi_overbought:
        add(
            "rsi_overbought",
            "momentum",
            "bearish",
            f"RSI({p.rsi}) {r:.1f}: overbought (at or above {t.rsi_overbought:g})",
            r,
        )
    elif r > hi_band:
        add("rsi_positive", "momentum", "bullish", f"RSI({p.rsi}) {r:.1f}: positive momentum", r)
    elif r < lo_band:
        add("rsi_weak", "momentum", "bearish", f"RSI({p.rsi}) {r:.1f}: weak momentum", r)
    else:
        add("rsi_neutral", "momentum", "neutral", f"RSI({p.rsi}) {r:.1f}: neutral momentum", r)

    m = ind.macd(c, p.macd.fast, p.macd.slow, p.macd.signal)
    mv, ms, mh = _last(m["macd"]), _last(m["signal"]), _last(m["hist"])
    vals.update(macd=_r(mv), macd_signal=_r(ms), macd_hist=_r(mh))
    if mv is None or ms is None or mh is None:
        na.append(_need("MACD", p.macd.slow + p.macd.signal - 1, n))
    else:
        since, side_now = ind.bars_since_cross(m["macd"], m["signal"])
        fresh = since is not None and since < t.cross_lookback_bars
        zero = "above" if mv > 0 else "below"
        if side_now > 0:
            add(
                "macd_bullish",
                "momentum",
                "bullish",
                "MACD "
                + (
                    f"crossed above its signal line {since} bar(s) ago"
                    if fresh
                    else "is above its signal line"
                )
                + f" (histogram {mh:+.2f}, MACD {zero} zero)",
                mh,
            )
        elif side_now < 0:
            add(
                "macd_bearish",
                "momentum",
                "bearish",
                "MACD "
                + (
                    f"crossed below its signal line {since} bar(s) ago"
                    if fresh
                    else "is below its signal line"
                )
                + f" (histogram {mh:+.2f}, MACD {zero} zero)",
                mh,
            )

    sto = ind.stochastic(h, lo, c, p.stochastic.k, p.stochastic.smooth, p.stochastic.d)
    k_v, d_v = _last(sto["k"]), _last(sto["d"])
    vals.update(stoch_k=_r(k_v), stoch_d=_r(d_v))
    if k_v is None:
        na.append(_need("Stochastic", p.stochastic.k + p.stochastic.smooth - 1, n))
    elif k_v <= t.stoch_oversold:
        add("stoch_oversold", "momentum", "bullish", f"Stochastic %K {k_v:.1f}: oversold", k_v)
    elif k_v >= t.stoch_overbought:
        add("stoch_overbought", "momentum", "bearish", f"Stochastic %K {k_v:.1f}: overbought", k_v)
    else:
        add("stoch_neutral", "momentum", "neutral", f"Stochastic %K {k_v:.1f}: mid-range", k_v)

    roc_v = _last(ind.roc(c, p.roc))
    vals[f"roc{p.roc}"] = _r(roc_v)
    if roc_v is None:
        na.append(_need(f"ROC {p.roc}", p.roc + 1, n))
    else:
        add(
            "roc_positive" if roc_v > 0 else "roc_negative",
            "momentum",
            "bullish" if roc_v > 0 else "bearish",
            f"{'Up' if roc_v > 0 else 'Down'} {abs(roc_v):.1f}% "
            f"over the last {p.roc} {unit}s (ROC)",
            roc_v,
        )

    # ---------------------------------------------------------------- volatility
    bb = ind.bollinger(c, p.bollinger.period, p.bollinger.std)
    bu, bm, bl, bw, pb = (_last(bb[k]) for k in ("upper", "mid", "lower", "bandwidth", "pct_b"))
    vals.update(bb_upper=_r(bu), bb_mid=_r(bm), bb_lower=_r(bl), bb_pct_b=_r(pb, 3))
    if bu is None or bl is None or pb is None:
        na.append(_need("Bollinger Bands", p.bollinger.period, n))
    else:
        widths = bb["bandwidth"].dropna().iloc[-t.squeeze_lookback_bars :]
        if pb > 1:
            add(
                "bb_above_upper",
                "volatility",
                "bearish",
                f"Close is above the upper Bollinger Band ({fmt.px(bu)}): "
                "stretched, prone to pull back",
                pb,
                minor=True,
            )
        elif pb < 0:
            add(
                "bb_below_lower",
                "volatility",
                "bullish",
                f"Close is below the lower Bollinger Band ({fmt.px(bl)}): "
                "stretched to the downside",
                pb,
                minor=True,
            )
        if len(widths) >= t.squeeze_lookback_bars and bw is not None and bw <= widths.min():
            add(
                "bb_squeeze",
                "volatility",
                "neutral",
                f"Bollinger squeeze: band width is the narrowest in {t.squeeze_lookback_bars} bars;"
                " a large move often follows",
                bw,
            )
    atr_v = _last(ind.atr(h, lo, c, p.atr))
    vals[f"atr{p.atr}"] = _r(atr_v)
    if atr_v is None:
        na.append(_need(f"ATR {p.atr}", p.atr + 1, n))
    else:
        add(
            "atr",
            "volatility",
            "neutral",
            f"ATR({p.atr}) {fmt.px(atr_v)} ({atr_v / close * 100:.1f}% of price)",
            atr_v,
        )
    hv = _last(ind.hist_volatility(c, p.hist_vol, BARS_PER_YEAR[interval]))
    vals["hist_vol"] = _r(hv, 4)
    if hv is None:
        na.append(_need("Historical volatility", p.hist_vol + 1, n))
    else:
        add(
            "hist_vol",
            "volatility",
            "neutral",
            f"Historical volatility ({p.hist_vol} {unit}s) {hv * 100:.1f}% annualised",
            hv,
        )

    # ---------------------------------------------------------------- volume
    has_volume = vol.fillna(0).gt(0).sum() >= p.volume_avg + 1
    vr_series = ind.volume_ratio(vol, p.volume_avg)
    if not has_volume:
        na.append("Volume indicators (no volume data for this series)")
    else:
        vr = _last(vr_series)
        vals["volume_ratio"] = _r(vr)
        if vr is None:
            na.append(_need("Volume ratio", p.volume_avg + 1, n))
        elif vr >= t.volume_surge:
            up = close > prev_close
            add(
                "volume_surge_up" if up else "volume_surge_down",
                "volume",
                "bullish" if up else "bearish",
                f"Volume {vr:.1f}× its {p.volume_avg}-{unit} average "
                f"on {'an up' if up else 'a down'} move",
                vr,
            )
        else:
            add(
                "volume_normal",
                "volume",
                "neutral",
                f"Volume {vr:.1f}× its {p.volume_avg}-{unit} average",
                vr,
            )
        ob = ind.obv(c, vol)
        sl = ind.slope(ob, p.obv_trend)
        avg_vol = float(vol.iloc[-p.obv_trend :].mean())
        if sl is None or avg_vol <= 0:
            na.append(_need("OBV trend", p.obv_trend, n))
        else:
            norm = sl / avg_vol
            vals["obv_slope"] = _r(norm, 4)
            price_chg = close - float(c.iloc[-p.obv_trend])
            if norm > t.obv_slope_min:
                if price_chg < 0:
                    add(
                        "obv_bullish_divergence",
                        "volume",
                        "bullish",
                        "OBV is rising while price fell: accumulation (bullish divergence)",
                        norm,
                    )
                else:
                    add(
                        "obv_rising",
                        "volume",
                        "bullish",
                        "OBV is rising: volume confirms the move",
                        norm,
                    )
            elif norm < -t.obv_slope_min:
                if price_chg > 0:
                    add(
                        "obv_bearish_divergence",
                        "volume",
                        "bearish",
                        "OBV is falling while price rose: distribution (bearish divergence)",
                        norm,
                    )
                else:
                    add(
                        "obv_falling",
                        "volume",
                        "bearish",
                        "OBV is falling: selling volume dominates",
                        norm,
                    )
            else:
                add("obv_flat", "volume", "neutral", "OBV is flat: no clear volume trend", norm)

    # ---------------------------------------------------------------- structure
    sr = cfg.support_resistance
    lv = levels(df, sr)
    sup, res = nearest(lv, close)
    vals["support"] = sup.price if sup else None
    vals["resistance"] = res.price if res else None
    if not lv:
        na.append(_need("Support/resistance", 2 * sr.pivot_window + 1, n))
    else:
        parts = []
        if sup:
            parts.append(
                f"support {fmt.px(sup.price)} ({sup.touches} touches, "
                f"{(close - sup.price) / close * 100:.1f}% below)"
            )
        else:
            parts.append("support: none below (price is near the bottom of its range)")
        if res:
            parts.append(
                f"resistance {fmt.px(res.price)} ({res.touches} touches, "
                f"{(res.price - close) / close * 100:.1f}% above)"
            )
        else:
            parts.append("resistance: none above (price is near the top of its range)")
        text = "; ".join(parts)
        add("levels", "structure", "neutral", text[0].upper() + text[1:])
        brk = recent_break(df, vr_series, sr)
        if brk:
            confirmed = brk.volume_ratio is not None and brk.volume_ratio >= t.volume_surge
            vol_txt = (
                f" on {brk.volume_ratio:.1f}× volume"
                if confirmed
                else " without a volume surge (less reliable)"
            )
            when = "on the latest bar" if brk.bars_ago == 0 else f"{brk.bars_ago} bar(s) ago"
            if brk.kind == "breakout":
                add(
                    "breakout",
                    "structure",
                    "bullish",
                    f"Broke out above resistance {fmt.px(brk.level)} {when}{vol_txt}",
                    brk.level,
                )
            else:
                add(
                    "breakdown",
                    "structure",
                    "bearish",
                    f"Broke down below support {fmt.px(brk.level)} {when}{vol_txt}",
                    brk.level,
                )

    pat = candle_pattern(df, t)
    if pat:
        candles: dict[str, tuple[Direction, str]] = {
            "bullish_engulfing": ("bullish", "Bullish engulfing candle on the latest bar"),
            "bearish_engulfing": ("bearish", "Bearish engulfing candle on the latest bar"),
            "hammer": ("bullish", "Hammer candle after a decline on the latest bar"),
            "doji": ("neutral", "Doji on the latest bar: indecision"),
        }
        cdir, ctext = candles[pat]
        add(f"candle_{pat}", "pattern", cdir, ctext, minor=True)
    return FrameAnalysis(vals, obs, na, lv)


def analyse_context(
    daily: pd.DataFrame,
    benchmark: pd.DataFrame | None,
    benchmark_label: str,
    delivery: pd.DataFrame | None,
    cfg: TechnicalConfig,
    *,
    is_index: bool = False,
) -> FrameAnalysis:
    """Daily-only readings: 52-week range, relative strength, NSE delivery %."""
    p, t = cfg.periods, cfg.thresholds
    fmt = _Fmt(is_index)
    obs: list[Observation] = []
    na: list[str] = []
    vals: dict[str, float | None] = {}
    n = len(daily)
    if n == 0:
        return FrameAnalysis({}, [], ["No daily price history"], [])
    close = float(daily["close"].iloc[-1])

    win = p.high_low_sessions
    if n < win:
        na.append(f"52-week high/low (needs {win} sessions, have {n})")
    else:
        hi = float(daily["high"].iloc[-win:].max())
        lo = float(daily["low"].iloc[-win:].min())
        below_hi = (hi - close) / hi * 100
        above_lo = (close - lo) / lo * 100
        vals.update(
            high_52w=round(hi, 2),
            low_52w=round(lo, 2),
            pct_below_52w_high=round(below_hi, 2),
            pct_above_52w_low=round(above_lo, 2),
        )
        if below_hi <= t.near_52w_pct:
            obs.append(
                Observation(
                    "near_52w_high",
                    "structure",
                    "bullish",
                    f"{below_hi:.1f}% below its 52-week high of {fmt.px(hi)}: strength",
                    round(below_hi, 2),
                )
            )
        elif above_lo <= t.near_52w_pct:
            obs.append(
                Observation(
                    "near_52w_low",
                    "structure",
                    "bearish",
                    f"Only {above_lo:.1f}% above its 52-week low of {fmt.px(lo)}: weakness",
                    round(above_lo, 2),
                )
            )
        else:
            obs.append(
                Observation(
                    "range_52w",
                    "structure",
                    "neutral",
                    f"{below_hi:.1f}% below the 52-week high ({fmt.px(hi)}), "
                    f"{above_lo:.1f}% above the low ({fmt.px(lo)})",
                )
            )

    if benchmark is None or benchmark.empty:
        na.append(f"Relative strength vs {benchmark_label} (no benchmark data)")
    else:
        joined = daily[["close"]].join(benchmark[["close"]], rsuffix="_b", how="inner").dropna()
        for name, bars in p.relative_strength.items():
            if len(joined) <= bars:
                na.append(
                    f"Relative strength {name} "
                    f"(needs {bars + 1} common sessions, have {len(joined)})"
                )
                continue
            rs_ = joined["close"].iloc[-1] / joined["close"].iloc[-1 - bars] - 1
            rb = joined["close_b"].iloc[-1] / joined["close_b"].iloc[-1 - bars] - 1
            rel = ((1 + rs_) / (1 + rb) - 1) * 100
            vals[f"rs_{name}"] = round(rel, 2)
            better = rel > 0
            obs.append(
                Observation(
                    f"rs_{name}",
                    "relative_strength",
                    "bullish" if better else "bearish",
                    f"{'Outperformed' if better else 'Underperformed'} {benchmark_label} "
                    f"by {abs(rel):.1f}% "
                    f"over {name} (stock {rs_ * 100:+.1f}%, {benchmark_label} {rb * 100:+.1f}%)",
                    round(rel, 2),
                )
            )

    if delivery is None:
        na.append("Delivery % (only available for NSE-listed stocks)")
    else:
        d = delivery.dropna(subset=["deliv_pct"])
        if len(d) < 2:
            na.append("Delivery % (no NSE bhavcopy data yet; run a market-data refresh)")
        else:
            last = d.iloc[-1]
            hist = d["deliv_pct"].iloc[-1 - p.delivery_avg : -1]
            avg = float(hist.mean())
            pct = float(last["deliv_pct"])
            when = f"{pd.Timestamp(d.index[-1]):%d %b}"
            vals.update(delivery_pct=round(pct, 2), delivery_avg_pct=round(avg, 2))
            ratio = pct / avg if avg > 0 else None
            prev_c = d["close"].iloc[-2]
            up = bool(last["close"] > prev_c) if not pd.isna(prev_c) else None
            short = len(hist) < p.delivery_avg
            avg_txt = f"{len(hist)}-session average {avg:.0f}%" + (
                ", only a short history so far" if short else ""
            )
            if ratio is not None and ratio >= t.delivery_surge and up is not None:
                obs.append(
                    Observation(
                        "delivery_surge_up" if up else "delivery_surge_down",
                        "volume",
                        "bullish" if up else "bearish",
                        f"Delivery {pct:.0f}% on {when} vs {avg_txt}, "
                        f"on {'an up' if up else 'a down'} day: "
                        + ("buying with conviction" if up else "sellers taking delivery"),
                        round(pct, 2),
                    )
                )
            else:
                obs.append(
                    Observation(
                        "delivery_normal",
                        "volume",
                        "neutral",
                        f"Delivery {pct:.0f}% on {when} ({avg_txt})",
                        round(pct, 2),
                    )
                )
    return FrameAnalysis(vals, obs, na, [])


def _iso(label: object) -> str | None:
    if label is None:
        return None
    if isinstance(label, pd.Timestamp):
        return str((label.tz_convert(IST) if label.tz is not None else label).isoformat())
    if isinstance(label, date):
        return label.isoformat()
    return str(label)


def timeframes_for(style: StyleKey | None) -> list[Interval]:
    profiles = get_profiles()
    if style is None:
        return ["1d"]
    return [tf for tf in profiles.styles[style].timeframes if tf in UNIT]  # type: ignore[misc]


def analyse(
    provider: DataProvider,
    ticker: str,
    *,
    label: str | None = None,
    style: StyleKey | None = None,
    timeframes: list[Interval] | None = None,
    fetch: bool = True,
) -> TechnicalReport:
    """Full technical read of one ticker. With fetch=True, missing/stale data is fetched first."""
    profiles = get_profiles()
    cfg = profiles.technical
    tfs = timeframes or timeframes_for(style)
    is_index = ticker.startswith("^")
    errors: list[str] = []
    notes: list[str] = []

    def ensure(fn_result_outcome: str, message: str) -> None:
        if fn_result_outcome == "failed":
            errors.append(message)

    if fetch:
        res = provider.ensure_daily(ticker, label)
        ensure(res.outcome, res.message)
    frames: list[TimeframeReport] = []
    for tf in tfs:
        if tf in INTRADAY:
            if fetch:
                res = provider.ensure_intraday(ticker, tf)  # type: ignore[arg-type]
                ensure(res.outcome, res.message)
            bars = provider.intraday(ticker, tf)  # type: ignore[arg-type]
        else:
            bars = provider.daily(ticker, tf)  # type: ignore[arg-type]
        df = bars.frame
        tf_notes = []
        if not bars.last_complete:
            tf_notes.append(f"The latest {UNIT[tf]} is still in progress; its bar will change.")
        if tf == "15m" or tf == "1h":
            tf_notes.append(
                "Intraday bars from Yahoo Finance are delayed and limited to "
                f"{profiles.data.intraday_max_days[tf]} days."
            )
        frames.append(
            TimeframeReport(
                interval=tf,
                bars=len(df),
                as_of=_iso(df.index[-1]) if len(df) else None,
                last_close=_f(df["close"].iloc[-1]) if len(df) else None,
                last_complete=bars.last_complete,
                freshness=bars.freshness,
                analysis=analyse_frame(df, tf, cfg, is_index=is_index),
                notes=tf_notes,
            )
        )

    bench_key = "nifty50"
    bench_ticker = profiles.data.benchmarks.get(bench_key)
    bench_df = None
    if bench_ticker and bench_ticker != ticker:
        if fetch:
            res = provider.ensure_daily(bench_ticker, "Nifty 50")
            ensure(res.outcome, res.message)
        bench_df = provider.daily(bench_ticker).frame
    deliv = None
    if ticker.endswith(".NS"):
        deliv = provider.delivery(ticker.removesuffix(".NS"), cfg.periods.delivery_avg + 1)
    daily = provider.daily(ticker).frame
    context = analyse_context(daily, bench_df, "Nifty 50", deliv, cfg, is_index=is_index)
    if style == "intraday" and profiles.styles["intraday"].note:
        notes.append(profiles.styles["intraday"].note)
    return TechnicalReport(
        ticker=ticker,
        label=label or ticker,
        style=style,
        timeframes=frames,
        context=context,
        fetch_errors=errors,
        notes=notes,
    )


def indicator_series(df: pd.DataFrame, cfg: TechnicalConfig) -> pd.DataFrame:
    """Full indicator time series for charting (Phase 8): one column per line."""
    p = cfg.periods
    h, lo, c = df["high"], df["low"], df["close"]
    out = pd.DataFrame(index=df.index)
    for k in p.sma:
        out[f"sma{k}"] = ind.sma(c, k)
    for k in p.ema:
        out[f"ema{k}"] = ind.ema(c, k)
    bb = ind.bollinger(c, p.bollinger.period, p.bollinger.std)
    out[["bb_upper", "bb_mid", "bb_lower"]] = bb[["upper", "mid", "lower"]]
    st = ind.supertrend(h, lo, c, p.supertrend.period, p.supertrend.multiplier)
    out["supertrend"], out["supertrend_dir"] = st["line"], st["direction"]
    out[f"rsi{p.rsi}"] = ind.rsi(c, p.rsi)
    m = ind.macd(c, p.macd.fast, p.macd.slow, p.macd.signal)
    out[["macd", "macd_signal", "macd_hist"]] = m[["macd", "signal", "hist"]]
    sto = ind.stochastic(h, lo, c, p.stochastic.k, p.stochastic.smooth, p.stochastic.d)
    out[["stoch_k", "stoch_d"]] = sto[["k", "d"]]
    a = ind.adx(h, lo, c, p.adx)
    out[["adx", "plus_di", "minus_di"]] = a[["adx", "plus_di", "minus_di"]]
    out[f"atr{p.atr}"] = ind.atr(h, lo, c, p.atr)
    if "volume" in df:
        out["obv"] = ind.obv(c, df["volume"])
    return out
