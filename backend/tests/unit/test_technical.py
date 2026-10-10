from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest

from app.analysis.technical import analyse, analyse_context, analyse_frame, indicator_series
from app.core.profiles import get_profiles
from app.data.freshness import Freshness
from app.data.navs import LatestNav
from app.data.prices import Bars
from app.data.store import RefreshResult

CFG = get_profiles().technical


def trend(
    n: int, drift: float, seed: int = 7, start: float = 100.0, vol_drift: float = 0.0
) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    c = start * np.exp(np.cumsum(drift + rng.normal(0, 0.01, n)))
    o = c * np.exp(rng.normal(0, 0.003, n))
    days = pd.bdate_range("2023-01-02", periods=n)
    return pd.DataFrame(
        {
            "open": o,
            "high": np.maximum(o, c) * 1.005,
            "low": np.minimum(o, c) * 0.995,
            "close": c,
            "volume": 1e6 * np.exp(vol_drift * np.arange(n)) * rng.uniform(0.8, 1.2, n),
        },
        index=pd.Index([d.date() for d in days], name="date"),
    )


def keys(a) -> dict[str, str]:  # type: ignore[no-untyped-def]
    return {o.key: o.direction for o in a.observations}


def test_strong_uptrend_reads_bullish() -> None:
    a = analyse_frame(trend(400, 0.004), "1d", CFG)
    k = keys(a)
    for key in (
        "price_vs_sma200",
        "price_vs_sma50",
        "sma50_above_sma200",
        "ema_fast_above_slow",
        "supertrend_up",
        "roc_positive",
    ):
        assert k[key] == "bullish", key
    assert k["adx_strong_trend"] == "bullish"
    assert a.unavailable == []
    bull = sum(o.direction == "bullish" for o in a.observations)
    bear = sum(o.direction == "bearish" for o in a.observations)
    assert bull > 3 * max(bear, 1)


def test_downtrend_reads_bearish_and_text_shows_numbers() -> None:
    a = analyse_frame(trend(400, -0.004), "1d", CFG)
    k = keys(a)
    assert k["price_vs_sma200"] == "bearish" and k["supertrend_down"] == "bearish"
    assert k["sma50_below_sma200"] == "bearish"
    text = next(o.text for o in a.observations if o.key == "price_vs_sma200")
    assert "below its 200-day SMA" in text and "₹" in text
    rsi = next(o for o in a.observations if o.key.startswith("rsi_"))
    assert f"{rsi.value:.1f}" in rsi.text


def test_short_history_lists_unavailable_instead_of_guessing() -> None:
    a = analyse_frame(trend(60, 0.002), "1mo", CFG)
    assert a.values["sma200"] is None
    assert any("SMA 200 (needs 200 bars, have 60)" in u for u in a.unavailable)
    assert "price_vs_sma200" not in keys(a)
    assert "price_vs_sma50" in keys(a)  # 50 bars is enough
    texts = " ".join(o.text for o in a.observations)
    assert "50-month SMA" in texts  # units follow the timeframe


def test_tiny_frame() -> None:
    a = analyse_frame(trend(1, 0.0), "1d", CFG)
    assert a.observations == [] and "Not enough price history" in a.unavailable[0]


def test_no_volume_for_indices() -> None:
    df = trend(300, 0.001).assign(volume=0.0)
    a = analyse_frame(df, "1d", CFG, is_index=True)
    assert any("no volume data" in u for u in a.unavailable)
    assert not any(o.category == "volume" for o in a.observations)
    assert "₹" not in " ".join(o.text for o in a.observations)  # index points, not rupees


def test_rsi_extremes() -> None:
    df = trend(300, 0.0)
    crash = df.copy()
    crash.iloc[-15:, crash.columns.get_loc("close")] = np.linspace(
        df["close"].iloc[-16] * 0.97, df["close"].iloc[-16] * 0.6, 15
    )
    k = keys(analyse_frame(crash, "1d", CFG))
    assert k["rsi_oversold"] == "bullish"
    spike = df.copy()
    spike.iloc[-15:, spike.columns.get_loc("close")] = np.linspace(
        df["close"].iloc[-16] * 1.03, df["close"].iloc[-16] * 1.6, 15
    )
    assert keys(analyse_frame(spike, "1d", CFG))["rsi_overbought"] == "bearish"


def test_volume_surge_direction() -> None:
    df = trend(300, 0.001)
    df.iloc[-1, df.columns.get_loc("volume")] = df["volume"].iloc[-21:-1].mean() * 3
    df.iloc[-1, df.columns.get_loc("close")] = df["close"].iloc[-2] * 1.03
    k = keys(analyse_frame(df, "1d", CFG))
    assert k["volume_surge_up"] == "bullish"


def daily_ctx(n: int = 300, drift: float = 0.002) -> pd.DataFrame:
    return trend(n, drift)


def test_context_52w_and_relative_strength() -> None:
    stock = daily_ctx(300, 0.003)
    bench = daily_ctx(300, 0.0005)
    a = analyse_context(stock, bench, "Nifty 50", None, CFG)
    k = keys(a)
    assert k["rs_3m"] == "bullish" and k["rs_6m"] == "bullish"
    assert a.values["rs_3m"] is not None and a.values["rs_3m"] > 0
    assert "Outperformed Nifty 50" in next(o.text for o in a.observations if o.key == "rs_3m")
    assert any(o.key in ("near_52w_high", "range_52w") for o in a.observations)
    assert any("NSE-listed" in u for u in a.unavailable)


def test_context_rs_math_exact() -> None:
    idx = pd.Index([date(2026, 1, 1) + timedelta(days=i) for i in range(130)])
    stock = pd.DataFrame(
        {"close": np.linspace(100, 120, 130), "high": 121.0, "low": 99.0}, index=idx
    )
    bench = pd.DataFrame({"close": np.linspace(100, 110, 130)}, index=idx)
    a = analyse_context(stock, bench, "Nifty 50", None, CFG)
    s0, s1 = stock["close"].iloc[-64], stock["close"].iloc[-1]
    b0, b1 = bench["close"].iloc[-64], bench["close"].iloc[-1]
    assert a.values["rs_3m"] == pytest.approx(round(((s1 / s0) / (b1 / b0) - 1) * 100, 2))
    assert any("52-week high/low (needs 252 sessions, have 130)" in u for u in a.unavailable)


def test_context_delivery_surge() -> None:
    days = [date(2026, 9, 1) + timedelta(days=i) for i in range(21)]
    deliv = pd.DataFrame(
        {"deliv_pct": [40.0] * 20 + [70.0], "turnover_lacs": 1.0, "close": [100.0] * 20 + [104.0]},
        index=pd.Index(days),
    )
    a = analyse_context(daily_ctx(), None, "Nifty 50", deliv, CFG)
    obs = next(o for o in a.observations if o.key.startswith("delivery"))
    assert obs.key == "delivery_surge_up" and obs.direction == "bullish"
    assert "70%" in obs.text and "40%" in obs.text
    assert any("no benchmark data" in u for u in a.unavailable)
    empty = analyse_context(daily_ctx(), None, "Nifty 50", deliv.iloc[:0], CFG)
    assert any("no NSE bhavcopy data yet" in u for u in empty.unavailable)


def test_indicator_series_columns() -> None:
    s = indicator_series(trend(250, 0.001), CFG)
    for col in (
        "sma20",
        "sma200",
        "ema9",
        "bb_upper",
        "supertrend",
        "rsi14",
        "macd_hist",
        "stoch_k",
        "adx",
        "atr14",
        "obv",
    ):
        assert col in s.columns, col
    assert len(s) == 250 and np.isnan(s["sma200"].iloc[198]) and not np.isnan(s["sma200"].iloc[199])


class FakeProvider:
    def __init__(self, frames: dict[str, pd.DataFrame], fail: set[str] = frozenset()) -> None:  # type: ignore[assignment]
        self.frames, self.fail = frames, fail
        self.ensured: list[str] = []

    def _bars(self, ticker: str, interval: str) -> Bars:
        df = self.frames.get(
            ticker, pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
        )
        st = "fresh" if len(df) else "unavailable"
        return Bars(ticker, interval, df, True, Freshness(st, "test"))  # type: ignore[arg-type]

    def daily(self, ticker: str, interval: str = "1d", start: date | None = None) -> Bars:
        return self._bars(ticker, interval)

    def intraday(self, ticker: str, interval: str) -> Bars:
        return self._bars(f"{ticker}:{interval}", interval)

    def ensure_daily(
        self, ticker: str, label: str | None = None, force: bool = False
    ) -> RefreshResult:
        self.ensured.append(ticker)
        outcome = "failed" if ticker in self.fail else "skipped"
        return RefreshResult(
            ticker, label, outcome, f"{ticker} failed" if outcome == "failed" else "ok"
        )  # type: ignore[arg-type]

    def ensure_intraday(self, ticker: str, interval: str, force: bool = False) -> RefreshResult:
        self.ensured.append(f"{ticker}:{interval}")
        return RefreshResult(ticker, ticker, "skipped", "ok")

    def nav_history(self, code: str, start: date | None = None) -> pd.Series:
        return pd.Series(dtype="float64")

    def latest_nav(self, code: str) -> LatestNav:
        raise NotImplementedError

    def delivery(self, symbol: str, sessions: int) -> pd.DataFrame:
        return pd.DataFrame(columns=["deliv_pct", "turnover_lacs", "close"])


def test_analyse_uses_style_timeframes_and_reports_fetch_errors() -> None:
    p = FakeProvider({"ABC.NS": trend(400, 0.002), "^NSEI": trend(400, 0.0)}, fail={"^NSEI"})
    r = analyse(p, "ABC.NS", style="positional")  # type: ignore[arg-type]
    assert [tf.interval for tf in r.timeframes] == ["1d", "1wk"]
    assert p.ensured == ["ABC.NS", "^NSEI"]
    assert r.fetch_errors == ["^NSEI failed"]
    assert r.context.values.get("rs_3m") is not None  # cached benchmark still used


def test_analyse_intraday_notes_and_no_fetch() -> None:
    p = FakeProvider({"ABC.NS": trend(300, 0.001), "ABC.NS:15m": trend(300, 0.0)})
    r = analyse(p, "ABC.NS", style="intraday", fetch=False)  # type: ignore[arg-type]
    assert [tf.interval for tf in r.timeframes] == ["15m", "1h", "1d"]
    assert p.ensured == []
    assert any("delayed" in n for n in r.timeframes[0].notes)
    assert r.notes and "60 days" in r.notes[0]  # the style's Yahoo limitation note
    one_h = r.timeframes[1]
    assert one_h.bars == 0 and one_h.freshness.status == "unavailable"


def test_analyse_unknown_ticker_is_all_unavailable() -> None:
    r = analyse(FakeProvider({}), "NOPE.NS", style="swing", fetch=False)  # type: ignore[arg-type]
    tf = r.timeframes[0]
    assert tf.bars == 0 and tf.analysis.observations == [] and tf.last_close is None
    assert r.context.unavailable == ["No daily price history"]
