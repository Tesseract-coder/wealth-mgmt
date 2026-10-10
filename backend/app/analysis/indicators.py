"""Technical indicators, hand-written on pandas/numpy.

Conventions follow TA-Lib (and the textbook definitions it implements), so values can be
checked against it (tests/unit/test_indicators.py uses TA-Lib-generated fixtures):

* EMA is seeded with the SMA of its first `n` values, then α = 2/(n+1).
* Wilder smoothing (RSI, ATR, ADX) is seeded with a simple average, then
  avg = (prev·(n−1) + x)/n.
* Bollinger bands use the population standard deviation.
* Values before an indicator has enough bars are NaN, never padded or guessed.

All functions take and return pandas Series aligned to the input index.
"""

import math

import numpy as np
import pandas as pd


def _out(index: pd.Index, values: np.ndarray, name: str) -> pd.Series:
    return pd.Series(values, index=index, name=name, dtype="float64")


def sma(s: pd.Series, n: int) -> pd.Series:
    return s.rolling(n, min_periods=n).mean().rename(f"sma{n}")


def ema(s: pd.Series, n: int) -> pd.Series:
    """EMA seeded with the SMA of the first n valid values (leading NaNs are skipped)."""
    x = s.to_numpy(dtype="float64")
    out = np.full(len(x), np.nan)
    valid = np.flatnonzero(~np.isnan(x))
    if len(valid) < n:
        return _out(s.index, out, f"ema{n}")
    start = valid[0]
    seed_end = start + n - 1
    out[seed_end] = x[start : seed_end + 1].mean()
    alpha = 2.0 / (n + 1)
    for i in range(seed_end + 1, len(x)):
        out[i] = out[i - 1] if np.isnan(x[i]) else alpha * x[i] + (1 - alpha) * out[i - 1]
    return _out(s.index, out, f"ema{n}")


def wilder(x: np.ndarray, n: int, first: int) -> np.ndarray:
    """Wilder moving average of x, seeded with mean(x[first:first+n]) at index first+n-1."""
    out = np.full(len(x), np.nan)
    if len(x) - first < n:
        return out
    out[first + n - 1] = x[first : first + n].mean()
    for i in range(first + n, len(x)):
        out[i] = (out[i - 1] * (n - 1) + x[i]) / n
    return out


def rsi(close: pd.Series, n: int = 14) -> pd.Series:
    c = close.to_numpy(dtype="float64")
    out = np.full(len(c), np.nan)
    if len(c) <= n:
        return _out(close.index, out, f"rsi{n}")
    d = np.diff(c, prepend=np.nan)
    gain, loss = np.where(d > 0, d, 0.0), np.where(d < 0, -d, 0.0)
    avg_g, avg_l = wilder(gain, n, 1), wilder(loss, n, 1)
    with np.errstate(divide="ignore", invalid="ignore"):
        total = avg_g + avg_l
        out = np.where(total > 0, 100.0 * avg_g / total, 50.0)  # flat prices: neither side
    out[:n] = np.nan
    return _out(close.index, out, f"rsi{n}")


def true_range(high: pd.Series, low: pd.Series, close: pd.Series) -> pd.Series:
    """TR from the second bar on (the first bar has no previous close)."""
    prev = close.shift(1)
    tr = pd.concat([high - low, (high - prev).abs(), (low - prev).abs()], axis=1).max(axis=1)
    tr.iloc[0] = np.nan
    return tr.rename("tr")


def atr(high: pd.Series, low: pd.Series, close: pd.Series, n: int = 14) -> pd.Series:
    tr = true_range(high, low, close).to_numpy(dtype="float64")
    return _out(close.index, wilder(tr, n, 1), f"atr{n}")


def macd(close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> pd.DataFrame:
    line = ema(close, fast) - ema(close, slow)
    sig = ema(line, signal)
    return pd.DataFrame({"macd": line, "signal": sig, "hist": line - sig}, index=close.index)


def stochastic(
    high: pd.Series, low: pd.Series, close: pd.Series, k: int = 14, smooth: int = 3, d: int = 3
) -> pd.DataFrame:
    """Slow stochastic: %K = SMA(smooth) of raw %K, %D = SMA(d) of %K. Zero range → NaN."""
    hh = high.rolling(k, min_periods=k).max()
    ll = low.rolling(k, min_periods=k).min()
    rng = (hh - ll).replace(0, np.nan)
    raw = 100 * (close - ll) / rng
    slow_k = raw.rolling(smooth, min_periods=smooth).mean()
    slow_d = slow_k.rolling(d, min_periods=d).mean()
    return pd.DataFrame({"k": slow_k, "d": slow_d}, index=close.index)


def roc(close: pd.Series, n: int) -> pd.Series:
    return ((close / close.shift(n) - 1) * 100).rename(f"roc{n}")


def bollinger(close: pd.Series, n: int = 20, k: float = 2.0) -> pd.DataFrame:
    mid = close.rolling(n, min_periods=n).mean()
    sd = close.rolling(n, min_periods=n).std(ddof=0)
    upper, lower = mid + k * sd, mid - k * sd
    width = (upper - lower) / mid
    pct_b = (close - lower) / (upper - lower).replace(0, np.nan)
    return pd.DataFrame(
        {"mid": mid, "upper": upper, "lower": lower, "bandwidth": width, "pct_b": pct_b},
        index=close.index,
    )


def adx(high: pd.Series, low: pd.Series, close: pd.Series, n: int = 14) -> pd.DataFrame:
    """Wilder's ADX with +DI/−DI, using TA-Lib's seeding (sums of the first n−1 moves)."""
    h, lo, c = (x.to_numpy(dtype="float64") for x in (high, low, close))
    size = len(c)
    plus_di = np.full(size, np.nan)
    minus_di = np.full(size, np.nan)
    adx_out = np.full(size, np.nan)
    if size < 2 * n:
        return pd.DataFrame(
            {"adx": adx_out, "plus_di": plus_di, "minus_di": minus_di}, index=close.index
        )
    up = np.diff(h, prepend=np.nan)
    down = -np.diff(lo, prepend=np.nan)
    pdm = np.where((up > down) & (up > 0), up, 0.0)
    mdm = np.where((down > up) & (down > 0), down, 0.0)
    tr = true_range(high, low, close).to_numpy(dtype="float64")
    s_p, s_m, s_tr = pdm[1:n].sum(), mdm[1:n].sum(), tr[1:n].sum()
    dx = np.full(size, np.nan)
    for i in range(n, size):
        s_p = s_p - s_p / n + pdm[i]
        s_m = s_m - s_m / n + mdm[i]
        s_tr = s_tr - s_tr / n + tr[i]
        if s_tr > 0:
            plus_di[i], minus_di[i] = 100 * s_p / s_tr, 100 * s_m / s_tr
            tot = plus_di[i] + minus_di[i]
            dx[i] = 100 * abs(plus_di[i] - minus_di[i]) / tot if tot > 0 else 0.0
    adx_out[2 * n - 1] = np.nanmean(dx[n : 2 * n])
    for i in range(2 * n, size):
        adx_out[i] = (adx_out[i - 1] * (n - 1) + dx[i]) / n
    return pd.DataFrame(
        {"adx": adx_out, "plus_di": plus_di, "minus_di": minus_di}, index=close.index
    )


def supertrend(
    high: pd.Series, low: pd.Series, close: pd.Series, n: int = 10, mult: float = 3.0
) -> pd.DataFrame:
    """Supertrend on Wilder ATR. `direction` is +1 (uptrend, line below price) or −1."""
    a = atr(high, low, close, n).to_numpy()
    h, lo, c = (x.to_numpy(dtype="float64") for x in (high, low, close))
    hl2 = (h + lo) / 2
    size = len(c)
    line = np.full(size, np.nan)
    direction = np.full(size, np.nan)
    upper_f = np.full(size, np.nan)
    lower_f = np.full(size, np.nan)
    start = int(np.argmax(~np.isnan(a))) if (~np.isnan(a)).any() else size
    for i in range(start, size):
        bu, bl = hl2[i] + mult * a[i], hl2[i] - mult * a[i]
        if i == start:
            upper_f[i], lower_f[i] = bu, bl
            direction[i] = 1.0 if c[i] > hl2[i] else -1.0
        else:
            upper_f[i] = (
                bu if (bu < upper_f[i - 1] or c[i - 1] > upper_f[i - 1]) else upper_f[i - 1]
            )
            lower_f[i] = (
                bl if (bl > lower_f[i - 1] or c[i - 1] < lower_f[i - 1]) else lower_f[i - 1]
            )
            if direction[i - 1] < 0 and c[i] > upper_f[i - 1]:
                direction[i] = 1.0
            elif direction[i - 1] > 0 and c[i] < lower_f[i - 1]:
                direction[i] = -1.0
            else:
                direction[i] = direction[i - 1]
        line[i] = lower_f[i] if direction[i] > 0 else upper_f[i]
    return pd.DataFrame({"line": line, "direction": direction}, index=close.index)


def obv(close: pd.Series, volume: pd.Series) -> pd.Series:
    """On-balance volume, starting from the first bar's volume (as TA-Lib does)."""
    sign = np.sign(close.diff().fillna(0.0))
    flow = (sign * volume.fillna(0.0)).to_numpy(dtype="float64", copy=True)
    flow[0] = float(volume.iloc[0]) if len(volume) and not pd.isna(volume.iloc[0]) else 0.0
    return _out(close.index, np.cumsum(flow), "obv")


def slope(s: pd.Series, n: int) -> float | None:
    """Least-squares slope per bar over the last n values; None if not enough data."""
    tail = s.dropna().iloc[-n:]
    if len(tail) < n:
        return None
    x = np.arange(n, dtype="float64")
    return float(np.polyfit(x, tail.to_numpy(dtype="float64"), 1)[0])


def hist_volatility(close: pd.Series, n: int, periods_per_year: float) -> pd.Series:
    """Annualised standard deviation of log returns over n bars (sample std)."""
    lr = np.log(close / close.shift(1))
    return (lr.rolling(n, min_periods=n).std(ddof=1) * math.sqrt(periods_per_year)).rename(f"hv{n}")


def volume_ratio(volume: pd.Series, n: int) -> pd.Series:
    """Volume vs the average of the previous n bars (today excluded, so a spike stands out)."""
    avg = volume.shift(1).rolling(n, min_periods=n).mean()
    return (volume / avg.replace(0, np.nan)).rename("volume_ratio")


def bars_since_cross(a: pd.Series, b: pd.Series) -> tuple[int | None, int]:
    """(bars since a last crossed b, side now: +1 a above b, −1 below, 0 unknown)."""
    diff = (a - b).dropna()
    if diff.empty:
        return None, 0
    side = np.sign(diff.to_numpy())
    now = int(side[-1])
    changes = np.flatnonzero(side[1:] != side[:-1])
    if len(changes) == 0:
        return None, now
    return int(len(side) - 1 - (changes[-1] + 1)), now
