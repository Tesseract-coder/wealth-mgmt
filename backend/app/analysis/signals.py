"""Signals: composite score + risk overlays → Buy / Hold / Sell for one stock, with the why.

Order of the rules (thresholds from `signals:` and the active risk level in profiles.yaml):

1. **Sell / Exit**: a severe red flag (price closed below the ATR trailing stop, pledge above
   the severe limit, sustained losses while debt rose) or composite below `reduce_floor`.
2. **Reduce / Trim**: position above the max weight per stock, or composite in
   [reduce_floor, hold_floor).
3. **Strong Buy / Add**: composite ≥ buy threshold + strong_buy_margin, no red flags, and the
   position below the max weight.
4. **Buy / Add**: composite ≥ buy threshold and no red flags.
5. **Hold**: everything else, including a buy-level score held back by red flags.

With no composite score and no rule-1/2 trigger the result is "Insufficient data" — the app
never guesses.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

import numpy as np
import pandas as pd
from sqlmodel import Session, col, select

from app.analysis import indicators as ind
from app.analysis.fundamental import FundamentalReport, analyse_fundamentals
from app.analysis.positions import (
    Portfolio,
    Position,
    Rebalance,
    TaxNote,
    load_portfolio,
    stock_sector,
    suggest,
    tax_note,
)
from app.analysis.scoring import Composite, Reading, composite, top_reasons
from app.analysis.technical import INTRADAY, Interval, TechnicalReport, analyse
from app.core.formatting import format_inr, now_ist
from app.core.profiles import Profiles, RiskKey, StyleKey, get_profiles
from app.data.provider import CachedProvider, DataProvider
from app.data.store import RefreshResult
from app.models.tables import SignalRecord, UserProfile, utcnow

SignalKey = Literal["strong_buy", "buy", "hold", "reduce", "sell", "no_signal"]
SIGNAL_LABEL: dict[str, str] = {
    "strong_buy": "Strong Buy / Add",
    "buy": "Buy / Add",
    "hold": "Hold",
    "reduce": "Reduce / Trim",
    "sell": "Sell / Exit",
    "no_signal": "Insufficient data",
}
FALLBACK_STYLE: StyleKey = "positional"


@dataclass(frozen=True)
class Flag:
    key: str
    severe: bool
    text: str


@dataclass(frozen=True)
class Target:
    label: str
    price: float
    pct: float  # from the latest close


@dataclass(frozen=True)
class PriceLevels:
    interval: str
    close: float
    as_of: str
    atr: float
    multiple: float
    trailing_stop: float
    entry_stop: float
    stop_breached: bool
    risk_per_share: float
    targets: list[Target]
    basis: str


@dataclass
class StockSignal:
    ticker: str
    label: str
    style: StyleKey
    style_label: str
    risk: RiskKey
    risk_label: str
    signal: SignalKey
    rule: str
    score: Composite
    bullish: list[Reading]
    bearish: list[Reading]
    flags: list[Flag]
    levels: PriceLevels | None
    beta: float | None
    beta_basis: str
    position: Position | None
    weight: float | None
    max_weight: float
    sector: str | None
    sector_weight: float | None
    max_sector_weight: float
    rebalance: Rebalance
    tax: TaxNote | None
    technical: TechnicalReport
    fundamental: FundamentalReport
    notes: list[str] = field(default_factory=list)

    @property
    def signal_label(self) -> str:
        return SIGNAL_LABEL[self.signal]


# ---------------------------------------------------------------------------- price levels


def price_levels(
    df: pd.DataFrame,
    interval: str,
    *,
    atr_period: int,
    multiple: float,
    lookback: int,
    r_multiples: list[float],
    resistance: float | None,
) -> PriceLevels | None:
    """ATR trailing stop (highest high of `lookback` bars − multiple × ATR), entry stop
    (close − multiple × ATR) and targets: the nearest resistance and close + k·R."""
    if len(df) < max(atr_period + 1, 2):
        return None
    a = ind.atr(df["high"], df["low"], df["close"], atr_period)
    atr_v = a.iloc[-1]
    if pd.isna(atr_v) or atr_v <= 0:
        return None
    atr_f = float(atr_v)
    close = float(df["close"].iloc[-1])
    hh = float(df["high"].iloc[-lookback:].max())
    trailing = hh - multiple * atr_f
    risk = multiple * atr_f
    targets: list[Target] = []
    if resistance is not None and resistance > close:
        targets.append(
            Target("Nearest resistance", round(resistance, 2), (resistance / close - 1) * 100)
        )
    for k in r_multiples:
        p = close + k * risk
        targets.append(Target(f"{k:g}R", round(p, 2), (p / close - 1) * 100))
    idx = df.index[-1]
    as_of = idx.isoformat() if hasattr(idx, "isoformat") else str(idx)
    unit = {"15m": "15-min bars", "1h": "hours", "1d": "days", "1wk": "weeks", "1mo": "months"}
    return PriceLevels(
        interval=interval,
        close=round(close, 2),
        as_of=as_of,
        atr=round(atr_f, 2),
        multiple=multiple,
        trailing_stop=round(trailing, 2),
        entry_stop=round(close - risk, 2),
        stop_breached=close < trailing,
        risk_per_share=round(risk, 2),
        targets=targets,
        basis=(
            f"Trailing stop = highest high of the last {lookback} {unit.get(interval, 'bars')} "
            f"({format_inr(hh)}) − {multiple:g} × ATR({atr_period}) {format_inr(atr_f)}. "
            f"For a new purchase: stop at close − {multiple:g} × ATR; R = {format_inr(risk)}."
        ),
    )


def beta_vs(
    daily: pd.DataFrame, bench: pd.DataFrame | None, lookback: int, min_sessions: int
) -> tuple[float | None, int]:
    """Beta of daily returns vs the benchmark over the last `lookback` common sessions."""
    if bench is None or bench.empty or daily.empty:
        return None, 0
    j = daily[["close"]].join(bench[["close"]], rsuffix="_b", how="inner").dropna()
    r = j.pct_change().dropna().iloc[-lookback:]
    if len(r) < min_sessions:
        return None, len(r)
    var = float(np.var(r["close_b"], ddof=1))
    if var <= 0:
        return None, len(r)
    cov = float(np.cov(r["close"], r["close_b"], ddof=1)[0, 1])
    return cov / var, len(r)


# ---------------------------------------------------------------------------- decision


def decide(
    score: float | None,
    flags: list[Flag],
    weight: float | None,
    max_weight: float,
    buy_threshold: float,
    p: Profiles,
    risk_label: str,
) -> tuple[SignalKey, str]:
    rules = p.signals
    severe = [f for f in flags if f.severe]
    red = [f for f in flags if not f.severe]
    sc = "—" if score is None else f"{score:.0f}"
    if severe:
        return "sell", "Severe red flag: " + "; ".join(f.text for f in severe)
    if score is not None and score < rules.reduce_floor:
        return "sell", f"Composite {sc} is below {rules.reduce_floor:g}"
    if weight is not None and weight > max_weight:
        return (
            "reduce",
            f"Position is {weight * 100:.1f}% of your portfolio, above your "
            f"{max_weight * 100:g}% limit per stock ({risk_label} risk)",
        )
    if score is None:
        return "no_signal", "Not enough data for a score"
    if score < rules.hold_floor:
        return (
            "reduce",
            f"Composite {sc} is between {rules.reduce_floor:g} and {rules.hold_floor:g}",
        )
    strong = buy_threshold + rules.strong_buy_margin
    if score >= buy_threshold and red:
        return (
            "hold",
            f"Composite {sc} reaches the buy threshold {buy_threshold:g}, but red flags hold it "
            "back: " + "; ".join(f.text for f in red),
        )
    if score >= strong and (weight is None or weight < max_weight):
        return (
            "strong_buy",
            f"Composite {sc} ≥ {strong:g} (buy threshold {buy_threshold:g} + "
            f"{rules.strong_buy_margin:g}), no red flags, position below your limit",
        )
    if score >= buy_threshold:
        return (
            "buy",
            f"Composite {sc} ≥ buy threshold {buy_threshold:g} ({risk_label} risk), no red flags",
        )
    return (
        "hold",
        f"Composite {sc} is between {rules.hold_floor:g} and the buy threshold {buy_threshold:g}",
    )


def flags_for(
    fund: FundamentalReport,
    levels: PriceLevels | None,
    beta: float | None,
    max_beta: float | None,
    held: bool,
    sector: str | None,
    sector_weight: float | None,
    max_sector: float,
    p: Profiles,
    *,
    stop_exits: bool = True,
    style_label: str = "",
) -> list[Flag]:
    out: list[Flag] = []
    obs = {o.key: o for o in fund.observations}
    if levels and levels.stop_breached:
        severe = held and stop_exits
        out.append(
            Flag(
                "stop_breached",
                severe,
                f"Closed at {format_inr(levels.close)}, below the ATR trailing stop "
                f"{format_inr(levels.trailing_stop)}"
                + (
                    ""
                    if severe or not held
                    else f" (a warning only: the {style_label} style doesn't exit on stops)"
                ),
            )
        )
    if "pledge_severe" in obs:
        out.append(Flag("pledge_severe", True, obs["pledge_severe"].text))
    elif "pledge_high" in obs:
        out.append(Flag("pledge_high", False, obs["pledge_high"].text))
    losses = fund.metrics.get("consecutive_loss_years")
    debt_chg = fund.metrics.get("debt_change")
    n_loss = p.signals.severe_flags.consecutive_loss_years
    if (
        losses is not None
        and losses.value is not None
        and losses.value >= n_loss
        and debt_chg is not None
        and (debt_chg.value or 0) > 0
    ):
        out.append(
            Flag(
                "losses_rising_debt",
                True,
                f"Net loss for {losses.value:.0f} years in a row while debt rose",
            )
        )
    if "debt_above_limit" in obs:
        out.append(Flag("debt_above_limit", False, obs["debt_above_limit"].text))
    if beta is not None and max_beta is not None and beta > max_beta:
        out.append(
            Flag(
                "beta_high", False, f"Beta {beta:.2f} vs Nifty 50, above your limit of {max_beta:g}"
            )
        )
    if sector and sector_weight is not None and sector_weight > max_sector:
        out.append(
            Flag(
                "sector_concentration",
                False,
                f"{sector} is {sector_weight * 100:.1f}% of your portfolio, above your "
                f"{max_sector * 100:g}% sector limit",
            )
        )
    return out


# ---------------------------------------------------------------------------- entry point


def resolve_style(style: StyleKey | None) -> tuple[StyleKey, list[str]]:
    if style is not None:
        return style, []
    return FALLBACK_STYLE, [
        "No investing style chosen yet, so the Positional style is used. Pick yours in Settings."
    ]


def analyse_stock(
    session: Session,
    provider: DataProvider,
    ticker: str,
    *,
    style: StyleKey | None,
    risk_key: RiskKey,
    custom_technical_weight: float = 0.5,
    portfolio: Portfolio | None = None,
    label: str | None = None,
    fetch: bool = True,
    now: datetime | None = None,
) -> StockSignal:
    p = get_profiles()
    now = now or now_ist()
    style_key, notes = resolve_style(style)
    st = p.styles[style_key]
    risk = p.risk_levels[risk_key]
    tw = custom_technical_weight if style_key == "custom" else st.technical_weight
    position = portfolio.positions.get(ticker) if portfolio else None
    label = label or (position.label if position else None)
    tech = analyse(provider, ticker, label=label, style=style_key, fetch=fetch)
    fund = analyse_fundamentals(
        session,
        provider,
        ticker,
        label=label,
        risk=risk,
        risk_label=risk.label,
        fetch=fetch,
        now=now,
    )
    comp = composite(tech, fund, tw, p.scoring, p.confidence)
    notes += comp.notes + tech.notes

    # Stops on the style's main timeframe (daily when it has too little data), complete bars only.
    levels = None
    cfg_t = p.technical
    for tf in [tech.timeframes[0].interval, "1d"] if tech.timeframes else ["1d"]:
        tfi: Interval = tf  # type: ignore[assignment]
        bars = provider.intraday(ticker, tfi) if tfi in INTRADAY else provider.daily(ticker, tfi)  # type: ignore[arg-type]
        df = bars.frame if bars.last_complete else bars.frame.iloc[:-1]
        rep = next((t for t in tech.timeframes if t.interval == tf), None)
        res = rep.analysis.values.get("resistance") if rep else None
        levels = price_levels(
            df,
            tf,
            atr_period=cfg_t.periods.atr,
            multiple=risk.stop_loss_atr_multiple,
            lookback=p.signals.stop_loss_lookback_bars,
            r_multiples=p.signals.target_r_multiples,
            resistance=res,
        )
        if levels is not None:
            break

    bench = p.data.benchmarks["nifty50"]
    beta, n = beta_vs(
        provider.daily(ticker).frame,
        provider.daily(bench).frame if bench != ticker else None,
        p.scoring.beta_lookback_sessions,
        p.scoring.beta_min_sessions,
    )
    beta_basis = (
        f"daily returns vs Nifty 50 over {n} sessions"
        if beta is not None
        else f"needs {p.scoring.beta_min_sessions} sessions of prices alongside Nifty 50, have {n}"
    )
    sector = position.sector if position else stock_sector(provider, ticker)
    weight = portfolio.weight(ticker) if portfolio else None
    sector_w = portfolio.sector_weight(sector) if portfolio and sector else None
    flags = flags_for(
        fund,
        levels,
        beta,
        risk.max_beta,
        position is not None,
        sector,
        sector_w,
        risk.max_weight_per_sector,
        p,
        stop_exits=st.stop_breach_exits,
        style_label=st.label,
    )
    signal, rule = decide(
        comp.score, flags, weight, risk.max_weight_per_stock, risk.buy_threshold, p, risk.label
    )
    if position is None and signal in ("reduce", "sell"):
        rule += ". You don't hold it: read this as 'avoid'."
    price = levels.close if levels else (position.price if position else None)
    score_reduce = (
        signal == "reduce" and comp.score is not None and comp.score < p.signals.hold_floor
    )
    reb = suggest(
        signal,
        position,
        price,
        portfolio,
        risk,
        p.rebalance,
        sector_weight=sector_w,
        sector=sector,
        score_reduce=score_reduce,
    )
    sell_qty = reb.quantity if reb.action in ("trim", "exit") else 0
    tax = tax_note(position, sell_qty, price, p.tax, now.date())
    bull, bear = top_reasons(comp.readings)
    return StockSignal(
        ticker=ticker,
        label=label or fund.label or tech.label,
        style=style_key,
        style_label=st.label,
        risk=risk_key,
        risk_label=risk.label,
        signal=signal,
        rule=rule,
        score=comp,
        bullish=bull,
        bearish=bear,
        flags=flags,
        levels=levels,
        beta=None if beta is None else round(beta, 2),
        beta_basis=beta_basis,
        position=position,
        weight=weight,
        max_weight=risk.max_weight_per_stock,
        sector=sector,
        sector_weight=sector_w,
        max_sector_weight=risk.max_weight_per_sector,
        rebalance=reb,
        tax=tax,
        technical=tech,
        fundamental=fund,
        notes=notes,
    )


def record(session: Session, s: StockSignal, day: datetime | None = None) -> None:
    """Upsert today's signal into the history (one row per ticker, day, style and risk)."""
    d = (day or now_ist()).date()
    row = session.get(SignalRecord, (s.ticker, d, s.style, s.risk)) or SignalRecord(
        ticker=s.ticker, day=d, style=s.style, risk=s.risk, signal=s.signal
    )
    row.signal = s.signal
    row.composite = s.score.score
    row.technical = s.score.technical.score
    row.fundamental = s.score.fundamental.score
    row.confidence = s.score.confidence
    row.recorded_at = utcnow()
    session.add(row)


def history(
    session: Session, ticker: str, style: str | None = None, limit: int = 365
) -> list[SignalRecord]:
    q = select(SignalRecord).where(SignalRecord.ticker == ticker)
    if style:
        q = q.where(SignalRecord.style == style)
    return list(session.exec(q.order_by(col(SignalRecord.day).desc()).limit(limit)).all())


def active_profile(
    session: Session, style: StyleKey | None = None, risk: RiskKey | None = None
) -> tuple[StyleKey | None, RiskKey, float]:
    """(style, risk, custom technical weight): the arguments, else your saved profile's."""
    p = session.get(UserProfile, 1)
    profiles = get_profiles()
    saved_style: StyleKey | None = p.style if p and p.style in profiles.styles else None
    saved_risk: RiskKey = p.risk if p and p.risk in profiles.risk_levels else profiles.defaults.risk
    return style or saved_style, risk or saved_risk, p.custom_technical_weight if p else 0.5


def evaluate_holdings(
    session: Session,
    provider: DataProvider,
    style: StyleKey | None,
    risk: RiskKey,
    custom_technical_weight: float,
    *,
    save: bool = True,
) -> tuple[Portfolio, list[StockSignal]]:
    """Signals for every current holding from cached data; saved to the history by default."""
    pf = load_portfolio(session, provider, get_profiles().rebalance)
    out = []
    for ticker, pos in pf.positions.items():
        s = analyse_stock(
            session,
            provider,
            ticker,
            style=style,
            risk_key=risk,
            custom_technical_weight=custom_technical_weight,
            portfolio=pf,
            label=pos.label,
            fetch=False,
        )
        if save:
            record(session, s)
            from app.analysis.checks import record_shape  # checks builds on this module

            record_shape(session, s, provider.daily(ticker).frame)
        out.append(s)
    if save:
        session.commit()
    return pf, out


def record_holdings_step(session: Session) -> RefreshResult:
    """Job step: today's signals for your holdings under your saved style and risk."""
    style, risk, ctw = active_profile(session)
    _, sigs = evaluate_holdings(session, CachedProvider(session), style, risk, ctw)
    return RefreshResult("signals", "Signal history", "updated", f"{len(sigs)} signals saved")
