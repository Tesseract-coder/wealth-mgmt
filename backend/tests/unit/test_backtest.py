from datetime import date

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app.analysis.backtest import max_drawdown, run_backtest
from app.data.freshness import Freshness
from app.data.prices import Bars
from app.data.store import RefreshResult

BENCH = "^NSEI"


def frame(
    closes: np.ndarray, start: str = "2022-01-03", adj: np.ndarray | None = None
) -> pd.DataFrame:
    days = pd.bdate_range(start, periods=len(closes))
    c = pd.Series(closes, index=pd.Index([d.date() for d in days], name="date"))
    return pd.DataFrame(
        {
            "open": c.shift(1).fillna(c.iloc[0]),
            "high": c * 1.01,
            "low": c * 0.99,
            "close": c,
            "adj_close": c if adj is None else adj,
            "volume": 1_000_000.0,
        }
    )


def wave(n: int, seed: int = 1) -> np.ndarray:
    """Up for two years, down for one, up again: something for every signal."""
    rng = np.random.default_rng(seed)
    t = np.arange(n)
    drift = np.where(t < n * 0.55, 0.0008, np.where(t < n * 0.8, -0.0012, 0.001))
    return 100 * np.exp(np.cumsum(drift + rng.normal(0, 0.012, n)))


class Fake:
    def __init__(self, frames: dict[str, pd.DataFrame]) -> None:
        self.frames = frames
        self.ensured: list[str] = []

    def daily(self, ticker: str, interval: str = "1d", start: date | None = None) -> Bars:
        df = self.frames.get(ticker)
        if df is None:
            df = pd.DataFrame(columns=["open", "high", "low", "close", "adj_close", "volume"])
        return Bars(ticker, interval, df, True, Freshness("fresh", "test"))

    def ensure_daily(self, ticker: str, label: str | None = None, **_: object) -> RefreshResult:
        self.ensured.append(ticker)
        return RefreshResult(f"price:{ticker}", label or ticker, "fresh", "cached", 0)


N = 1100


@pytest.fixture(scope="module")
def prices() -> dict[str, pd.DataFrame]:
    return {"ABC.NS": frame(wave(N)), BENCH: frame(wave(N, seed=7))}


def test_max_drawdown() -> None:
    assert max_drawdown(pd.Series([1.0, 1.2, 0.9, 1.3, 1.0])) == pytest.approx(0.9 / 1.2 - 1)
    assert max_drawdown(pd.Series([1.0, 1.1, 1.2])) == 0.0


def test_too_little_history_says_so() -> None:
    fake = Fake({"ABC.NS": frame(wave(200))})
    r = run_backtest(fake, "ABC.NS", style="swing", risk_key="medium", fetch=False)  # type: ignore[arg-type]
    assert r.status == "insufficient_data"
    assert "200 are cached" in r.message
    assert r.points == [] and r.strategy is None


def test_replay_shape_and_stats(prices: dict[str, pd.DataFrame]) -> None:
    fake = Fake(prices)
    r = run_backtest(fake, "ABC.NS", style="swing", risk_key="medium", fetch=True)  # type: ignore[arg-type]
    assert fake.ensured == ["ABC.NS", BENCH]
    assert r.status == "ok"
    assert r.horizon_sessions == 20 and r.step_sessions == 5 and r.timeframes == ["1d"]
    # Three years of weekly evaluations, ending on the latest session.
    assert r.evaluations == len(r.points) == 152
    assert r.points[-1].date == prices["ABC.NS"].index[-1].isoformat()
    groups = {s.group: s for s in r.stats}
    assert {"buy", "exit", "all"} <= set(groups)
    assert groups["all"].count == r.evaluations
    # The last `horizon` sessions have no forward window yet.
    assert groups["all"].measured == r.evaluations - 4
    assert sum(s.count for s in r.stats if s.group != "all") == r.evaluations
    for s in r.stats:
        assert s.hit_rate is None or 0 <= s.hit_rate <= 1
    assert r.strategy is not None and r.buy_hold is not None
    assert r.buy_hold.exposure == 1.0 and 0 <= r.strategy.exposure <= 1
    assert r.strategy.max_drawdown <= 0 and r.buy_hold.max_drawdown <= 0
    # Buy-and-hold is the plain price ratio over the replay window.
    df = prices["ABC.NS"]
    start_i = df.index.get_loc(date.fromisoformat(r.points[0].date))
    expected = df["close"].iloc[-1] / df["close"].iloc[start_i] - 1
    assert r.buy_hold.total_return == pytest.approx(expected, abs=1e-3)
    # In the market only after a Buy, out after a Reduce/Sell.
    held = False
    for p in r.points:
        if p.signal in ("buy", "strong_buy"):
            held = True
        elif p.signal in ("reduce", "sell"):
            held = False
        assert p.in_market == held
    assert "not predict" in r.caveat


def test_no_look_ahead(prices: dict[str, pd.DataFrame]) -> None:
    """Changing prices after a day must not change any signal on or before that day."""
    base = run_backtest(Fake(prices), "ABC.NS", style="swing", risk_key="medium", fetch=False)  # type: ignore[arg-type]
    cut = 900
    altered = prices["ABC.NS"].copy()
    altered.iloc[cut + 1 :, :5] *= 0.5  # a crash that only the future knows about
    other = run_backtest(
        Fake({**prices, "ABC.NS": altered}),
        "ABC.NS",
        style="swing",
        risk_key="medium",
        fetch=False,  # type: ignore[arg-type]
    )
    day = altered.index[cut].isoformat()
    before = [(p.date, p.score, p.signal) for p in base.points if p.date <= day]
    assert before and before == [(p.date, p.score, p.signal) for p in other.points if p.date <= day]
    assert other.points[-1].close == pytest.approx(base.points[-1].close / 2, abs=0.01)


def test_splits_use_adjusted_prices() -> None:
    closes = wave(N, seed=3)
    adj = closes.copy()
    raw = closes.copy()
    raw[: N // 2] *= 2  # a 1:1 bonus halfway: the raw close halves overnight
    prices = {"ABC.NS": frame(raw, adj=adj), BENCH: frame(wave(N, seed=7))}
    r = run_backtest(Fake(prices), "ABC.NS", style="swing", risk_key="medium", fetch=False)  # type: ignore[arg-type]
    clean = run_backtest(
        Fake({**prices, "ABC.NS": frame(adj)}),
        "ABC.NS",
        style="swing",
        risk_key="medium",
        fetch=False,  # type: ignore[arg-type]
    )
    assert r.buy_hold is not None and clean.buy_hold is not None
    assert r.buy_hold.total_return == pytest.approx(clean.buy_hold.total_return, abs=1e-3)
    assert r.buy_hold.max_drawdown > -0.45  # no fake 50% crash


def test_intraday_style_replays_daily_bars(prices: dict[str, pd.DataFrame]) -> None:
    r = run_backtest(Fake(prices), "ABC.NS", style="intraday", risk_key="medium", fetch=False)  # type: ignore[arg-type]
    assert r.timeframes == ["1d"]
    assert any("Intraday timeframes are left out" in n for n in r.notes)
    pos = run_backtest(Fake(prices), "ABC.NS", style="positional", risk_key="high", fetch=False)  # type: ignore[arg-type]
    assert pos.timeframes == ["1d", "1wk"] and pos.horizon_sessions == 60


def test_backtest_api(client: TestClient) -> None:
    r = client.get("/analysis/backtest/NOPE.NS", params={"fetch": False})
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "insufficient_data"
    assert body["style"] == "positional"  # no style saved yet
    assert any("No investing style chosen" in n for n in body["notes"])
    assert client.get("/analysis/backtest/bad ticker!").status_code == 422
