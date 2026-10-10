"""Regenerate technical_reference.csv: a synthetic OHLCV series plus TA-Lib's indicator values.

TA-Lib is the reference implementation the app's hand-written indicators are tested against.
It is NOT an app dependency; run this with a throwaway environment:

    cd backend && uv run --with ta-lib python tests/fixtures/make_technical_fixture.py
"""

from pathlib import Path

import numpy as np
import pandas as pd
import talib

rng = np.random.default_rng(20261010)
n = 400
# A random walk with drift and regime changes, so trends, reversals and ranges all appear.
drift = np.concatenate(
    [np.full(120, 0.0015), np.full(100, -0.002), np.full(80, 0.0), np.full(100, 0.002)]
)
close = 1000 * np.exp(np.cumsum(drift + rng.normal(0, 0.015, n)))
open_ = close * np.exp(rng.normal(0, 0.006, n))
high = np.maximum(open_, close) * np.exp(np.abs(rng.normal(0, 0.008, n)))
low = np.minimum(open_, close) * np.exp(-np.abs(rng.normal(0, 0.008, n)))
volume = rng.integers(100_000, 1_000_000, n).astype(float)

df = pd.DataFrame(
    {"open": open_, "high": high, "low": low, "close": close, "volume": volume},
    index=pd.bdate_range("2025-01-01", periods=n, name="date"),
).round(4)
o, h, lo, c, v = (df[k].to_numpy() for k in ("open", "high", "low", "close", "volume"))

ref = {
    "sma20": talib.SMA(c, 20),
    "sma50": talib.SMA(c, 50),
    "sma200": talib.SMA(c, 200),
    "ema9": talib.EMA(c, 9),
    "ema21": talib.EMA(c, 21),
    "rsi14": talib.RSI(c, 14),
    "atr14": talib.ATR(h, lo, c, 14),
    "adx14": talib.ADX(h, lo, c, 14),
    "plus_di14": talib.PLUS_DI(h, lo, c, 14),
    "minus_di14": talib.MINUS_DI(h, lo, c, 14),
    "roc20": talib.ROC(c, 20),
    "obv": talib.OBV(c, v),
}
ref["macd"], ref["macd_signal"], ref["macd_hist"] = talib.MACD(c, 12, 26, 9)
ref["stoch_k"], ref["stoch_d"] = talib.STOCH(h, lo, c, 14, 3, 0, 3, 0)
ref["bb_upper"], ref["bb_mid"], ref["bb_lower"] = talib.BBANDS(c, 20, 2, 2, 0)

out = df.join(pd.DataFrame(ref, index=df.index))
path = Path(__file__).with_name("technical_reference.csv")
out.to_csv(path, float_format="%.10g")
print(f"wrote {path} ({len(out)} rows, talib {talib.__version__})")
