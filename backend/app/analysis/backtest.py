"""Backtest helper: replay the technical signal rules over past prices for one ticker.

This is a historical test. It does not predict the future. At every `step_sessions`-th session
of the last `years` years it:

1. cuts the price history at that day (nothing after it is visible),
2. runs the same technical engine and technical score as the live signal, on the style's
   daily-or-longer timeframes, with the ATR trailing stop,
3. turns the score into a signal with the same rules (`decide`), treating a stop breach as
   the live app does: an exit when "held" and the style exits on stops, otherwise a red flag.

Fundamentals are left out because free sources have no point-in-time history (today's P/E
replayed into 2023 would be look-ahead). Delivery % is left out for the same reason.

Two measures come out:
- **Hit rate:** a Buy was right if the price was higher `horizon` sessions later; a
  Reduce/Sell was right if it was lower. Compare with the base rate (how often the price was
  higher after any evaluation day) to see whether the rule added anything.
- **Rule-following strategy:** be in after a Buy, out after a Reduce/Sell, unchanged on Hold;
  trade at the next session's open. Total return and maximum drawdown vs buying and holding.
  No costs, taxes or slippage.
"""

from dataclasses import dataclass, field

import pandas as pd

from app.analysis.scoring import score_technical
from app.analysis.signals import SIGNAL_LABEL, Flag, SignalKey, decide, price_levels
from app.analysis.technical import (
    INTRADAY,
    FrameAnalysis,
    Interval,
    TechnicalReport,
    TimeframeReport,
    analyse_context,
    analyse_frame,
)
from app.core.formatting import format_inr
from app.core.profiles import Profiles, RiskKey, StyleKey, get_profiles
from app.data.freshness import Freshness
from app.data.prices import resample
from app.data.provider import DataProvider

CAVEAT = (
    "Historical test of the technical rules only. Past results do not predict future returns. "
    "No brokerage, taxes or slippage; fundamentals and delivery % are not replayed."
)
BUY: tuple[SignalKey, ...] = ("strong_buy", "buy")
EXIT: tuple[SignalKey, ...] = ("reduce", "sell")


@dataclass
class BacktestPoint:
    date: str
    close: float
    score: float | None
    signal: SignalKey
    in_market: bool
    strategy: float  # equity, starting at 1.0
    buy_hold: float


@dataclass
class SignalStats:
    group: str  # "buy", "hold", "exit", "no_signal", "all"
    label: str
    count: int
    measured: int  # evaluations with a full forward window
    hit_rate: float | None  # share that went the signal's way (None for hold / all)
    rise_rate: float | None  # share with a higher price after the horizon
    avg_forward_return: float | None


@dataclass
class Performance:
    total_return: float
    max_drawdown: float  # negative fraction, e.g. -0.18
    exposure: float  # share of sessions in the market


@dataclass
class BacktestResult:
    ticker: str
    label: str
    style: StyleKey
    style_label: str
    risk: RiskKey
    risk_label: str
    status: str  # "ok" or "insufficient_data"
    message: str
    start: str | None = None
    end: str | None = None
    sessions: int = 0
    evaluations: int = 0
    step_sessions: int = 0
    horizon_sessions: int = 0
    timeframes: list[str] = field(default_factory=list)
    stats: list[SignalStats] = field(default_factory=list)
    strategy: Performance | None = None
    buy_hold: Performance | None = None
    trades: int = 0
    points: list[BacktestPoint] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    caveat: str = CAVEAT


def _adjusted(df: pd.DataFrame) -> pd.DataFrame:
    """Open and close scaled by adj_close/close so splits and bonuses don't look like crashes."""
    out = df[["open", "close"]].astype(float).copy()
    if "adj_close" in df:
        factor = (df["adj_close"].astype(float) / df["close"].astype(float)).fillna(1.0)
        out = out.mul(factor, axis=0)
    return out


def max_drawdown(equity: pd.Series) -> float:
    if equity.empty:
        return 0.0
    return float((equity / equity.cummax() - 1).min())


def _frames(daily: pd.DataFrame, intervals: list[Interval]) -> list[tuple[Interval, pd.DataFrame]]:
    out: list[tuple[Interval, pd.DataFrame]] = []
    expected = pd.Timestamp(daily.index[-1]).date()
    for tf in intervals:
        frame, _ = resample(daily, tf, expected)  # type: ignore[arg-type]
        out.append((tf, frame))
    return out


def _evaluate(
    daily: pd.DataFrame,
    bench: pd.DataFrame | None,
    intervals: list[Interval],
    p: Profiles,
    *,
    held: bool,
    stop_exits: bool,
    multiple: float,
    max_weight: float,
    buy_threshold: float,
    risk_label: str,
    is_index: bool,
) -> tuple[float | None, SignalKey]:
    cfg = p.technical
    fresh = Freshness("fresh", "replay")
    frames = _frames(daily, intervals)
    reports = [
        TimeframeReport(
            interval=tf,
            bars=len(df),
            as_of=None,
            last_close=None,
            last_complete=True,
            freshness=fresh,
            analysis=analyse_frame(df, tf, cfg, is_index=is_index),
        )
        for tf, df in frames
    ]
    context: FrameAnalysis = analyse_context(daily, bench, "Nifty 50", None, cfg, is_index=is_index)
    rep = TechnicalReport("", "", None, reports, context, [], [])
    score = score_technical(rep, p.scoring).side.score
    tf0, df0 = frames[0]
    res = reports[0].analysis.values.get("resistance")
    levels = price_levels(
        df0,
        tf0,
        atr_period=cfg.periods.atr,
        multiple=multiple,
        lookback=p.signals.stop_loss_lookback_bars,
        r_multiples=p.signals.target_r_multiples,
        resistance=res,
    )
    flags: list[Flag] = []
    if levels and levels.stop_breached:
        flags.append(Flag("stop_breached", held and stop_exits, "Closed below the trailing stop"))
    signal, _ = decide(score, flags, None, max_weight, buy_threshold, p, risk_label)
    return score, signal


def _stats(
    group: str, label: str, signals: list[SignalKey], fwd: list[float | None], keys: tuple[str, ...]
) -> SignalStats:
    picked = [f for s, f in zip(signals, fwd, strict=True) if not keys or s in keys]
    measured = [f for f in picked if f is not None]
    rise = sum(1 for f in measured if f > 0) / len(measured) if measured else None
    if group == "buy":
        hit = rise
    elif group == "exit":
        hit = sum(1 for f in measured if f < 0) / len(measured) if measured else None
    else:
        hit = None
    avg = sum(measured) / len(measured) if measured else None
    return SignalStats(group, label, len(picked), len(measured), hit, rise, avg)


def run_backtest(
    provider: DataProvider,
    ticker: str,
    *,
    style: StyleKey,
    risk_key: RiskKey,
    label: str | None = None,
    fetch: bool = True,
) -> BacktestResult:
    p = get_profiles()
    cfg = p.backtest
    st = p.styles[style]
    risk = p.risk_levels[risk_key]
    notes: list[str] = []
    intervals: list[Interval] = [
        tf  # type: ignore[misc]
        for tf in st.timeframes
        if tf not in INTRADAY
    ]
    if len(intervals) < len(st.timeframes):
        notes.append(
            "Intraday timeframes are left out: Yahoo Finance keeps only weeks of intraday bars, "
            "so the replay uses daily bars."
        )
    if not intervals:
        intervals = ["1d"]
    horizon = cfg.horizon_sessions[style]
    base = BacktestResult(
        ticker=ticker,
        label=label or ticker,
        style=style,
        style_label=st.label,
        risk=risk_key,
        risk_label=risk.label,
        status="insufficient_data",
        message="",
        step_sessions=cfg.step_sessions,
        horizon_sessions=horizon,
        timeframes=list(intervals),
        notes=notes,
    )
    bench_ticker = p.data.benchmarks.get("nifty50")
    if fetch:
        res = provider.ensure_daily(ticker, label)
        if res.outcome == "failed":
            notes.append(f"Price download failed: {res.message}. Using cached prices.")
        if bench_ticker and bench_ticker != ticker:
            provider.ensure_daily(bench_ticker, "Nifty 50")
    daily = provider.daily(ticker).frame
    bench = provider.daily(bench_ticker).frame if bench_ticker and bench_ticker != ticker else None
    n = len(daily)
    window = cfg.years * 252
    first = max(cfg.warmup_sessions, n - window)
    if n - first < max(cfg.step_sessions * 4, horizon + cfg.step_sessions):
        base.message = (
            f"Needs at least {cfg.warmup_sessions + horizon + cfg.step_sessions * 4} sessions of "
            f"daily prices; {n} are cached."
        )
        return base
    if n - first < window:
        notes.append(
            f"Only {n} sessions of history: the replay covers {(n - first) / 252:.1f} years "
            f"instead of {cfg.years}."
        )

    # Evaluate from the latest session backwards so today's signal is always included.
    idxs = sorted(range(n - 1, first - 1, -cfg.step_sessions))
    adj = _adjusted(daily)
    closes = adj["close"].to_numpy()
    opens = adj["open"].to_numpy()
    is_index = ticker.startswith("^")
    held = False
    sig_at: dict[int, tuple[float | None, SignalKey, bool]] = {}
    for i in idxs:
        cut = daily.iloc[: i + 1]
        day = cut.index[-1]
        b = bench.loc[bench.index <= day] if bench is not None else None
        score, signal = _evaluate(
            cut,
            b,
            intervals,
            p,
            held=held,
            stop_exits=st.stop_breach_exits,
            multiple=risk.stop_loss_atr_multiple,
            max_weight=risk.max_weight_per_stock,
            buy_threshold=risk.buy_threshold,
            risk_label=risk.label,
            is_index=is_index,
        )
        if signal in BUY:
            held = True
        elif signal in EXIT:
            held = False
        sig_at[i] = (score, signal, held)

    # Daily equity: a change of state decided at the close of day i takes effect at i+1's open.
    start = idxs[0]
    strat, bh = [1.0], [1.0]
    state = sig_at[start][2]
    in_days = 0
    trades = 1 if state else 0
    for d in range(start + 1, n):
        prev_c, o, c = closes[d - 1], opens[d], closes[d]
        new_state = state
        if (d - 1) in sig_at:
            new_state = sig_at[d - 1][2]
        if state and new_state:
            r = c / prev_c - 1
        elif not state and new_state:
            r = c / o - 1
            trades += 1
        elif state and not new_state:
            r = o / prev_c - 1
        else:
            r = 0.0
        state = new_state
        in_days += int(state)
        strat.append(strat[-1] * (1 + r))
        bh.append(bh[-1] * (c / prev_c))
    strat_s = pd.Series(strat)
    bh_s = pd.Series(bh)
    span = n - 1 - start

    signals = [sig_at[i][1] for i in idxs]
    fwd = [float(closes[i + horizon] / closes[i] - 1) if i + horizon < n else None for i in idxs]
    groups = [
        ("buy", "Buy / Strong Buy", BUY),
        ("hold", SIGNAL_LABEL["hold"], ("hold",)),
        ("exit", "Reduce / Sell", EXIT),
        ("no_signal", SIGNAL_LABEL["no_signal"], ("no_signal",)),
        ("all", "Every evaluation (base rate)", ()),
    ]
    stats = [_stats(g, lab, signals, fwd, keys) for g, lab, keys in groups]
    stats = [s for s in stats if s.count > 0 or s.group in ("buy", "exit", "all")]

    points = [
        BacktestPoint(
            date=pd.Timestamp(daily.index[i]).date().isoformat(),
            close=round(float(daily["close"].iloc[i]), 2),
            score=sig_at[i][0],
            signal=sig_at[i][1],
            in_market=sig_at[i][2],
            strategy=round(float(strat[i - start]), 4),
            buy_hold=round(float(bh[i - start]), 4),
        )
        for i in idxs
    ]
    base.status = "ok"
    buys = stats[0]
    base.message = (
        f"{len(idxs)} evaluations over {span} sessions; {buys.count} Buy signals"
        + (
            f", {buys.hit_rate * 100:.0f}% higher after {horizon} sessions"
            if buys.hit_rate is not None
            else ""
        )
        + f". Last close {format_inr(float(daily['close'].iloc[-1]))}."
    )
    base.start = points[0].date
    base.end = points[-1].date
    base.sessions = span
    base.evaluations = len(idxs)
    base.stats = stats
    base.strategy = Performance(
        round(float(strat[-1]) - 1, 4), round(max_drawdown(strat_s), 4), round(in_days / span, 3)
    )
    base.buy_hold = Performance(round(float(bh[-1]) - 1, 4), round(max_drawdown(bh_s), 4), 1.0)
    base.trades = trades
    base.points = points
    return base
