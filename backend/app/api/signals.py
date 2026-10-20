"""Scores and Buy / Hold / Sell signals, with the readings, flags and rules behind them."""

from dataclasses import replace
from datetime import timedelta

from fastapi import APIRouter, Depends, Path, Query
from sqlmodel import Session

from app.analysis.backtest import BacktestResult, run_backtest
from app.analysis.positions import load_portfolio
from app.analysis.scoring import Reading, SideScore
from app.analysis.signals import (
    SIGNAL_LABEL,
    StockSignal,
    active_profile,
    analyse_stock,
    evaluate_holdings,
    history,
    resolve_style,
)
from app.api.market import TICKER, fr_out
from app.core.db import get_session
from app.core.memo import Memo
from app.core.profiles import RiskKey, StyleKey, get_profiles
from app.data.freshness import Freshness
from app.data.provider import CachedProvider
from app.models.schemas import (
    FlagOut,
    HoldingSignalOut,
    HoldingSignalsOut,
    LotOut,
    PositionOut,
    PriceLevelsOut,
    ReadingOut,
    RebalanceOut,
    ScoresOut,
    SectorWeightOut,
    SideScoreOut,
    SignalHistoryOut,
    StockSignalOut,
    SubScoreOut,
    TargetOut,
    TaxNoteOut,
    TimeframeScoreOut,
)

router = APIRouter(prefix="/analysis", tags=["signals"])


def _reading(r: Reading) -> ReadingOut:
    return ReadingOut(**r.__dict__)


def _side(s: SideScore) -> SideScoreOut:
    return SideScoreOut(
        score=s.score,
        coverage=s.coverage,
        applicable=s.applicable,
        subscores=[SubScoreOut(**x.__dict__) for x in s.subscores],
        timeframes=[
            TimeframeScoreOut(
                interval=t.interval,
                score=t.score,
                coverage=t.coverage,
                weight=t.weight,
                subscores=[SubScoreOut(**x.__dict__) for x in t.subscores],
            )
            for t in s.timeframes
        ],
        notes=s.notes,
    )


def _price_freshness(s: StockSignal) -> Freshness:
    tfs = s.technical.timeframes
    return tfs[0].freshness if tfs else Freshness("unavailable", "No price data")


def signal_out(s: StockSignal) -> StockSignalOut:
    c = s.score
    pos = s.position
    lv = s.levels
    return StockSignalOut(
        ticker=s.ticker,
        label=s.label,
        style=s.style,
        style_label=s.style_label,
        risk=s.risk,
        risk_label=s.risk_label,
        signal=s.signal,
        signal_label=s.signal_label,
        rule=s.rule,
        scores=ScoresOut(
            composite=c.score,
            technical=_side(c.technical),
            fundamental=_side(c.fundamental),
            technical_weight=c.technical_weight,
            fundamental_weight=c.fundamental_weight,
            coverage=c.coverage,
            confidence=c.confidence,
            confidence_reason=c.confidence_reason,
        ),
        bullish=[_reading(r) for r in s.bullish],
        bearish=[_reading(r) for r in s.bearish],
        readings=[_reading(r) for r in sorted(c.readings, key=lambda r: -abs(r.points))],
        flags=[FlagOut(**f.__dict__) for f in s.flags],
        levels=(
            PriceLevelsOut(
                **{k: v for k, v in lv.__dict__.items() if k != "targets"},
                targets=[
                    TargetOut(label=t.label, price=t.price, pct=round(t.pct, 2)) for t in lv.targets
                ],
            )
            if lv
            else None
        ),
        beta=s.beta,
        beta_basis=s.beta_basis,
        position=(
            PositionOut(
                quantity=pos.quantity,
                avg_price=round(pos.avg_price, 2),
                invested=round(pos.invested, 2),
                price=pos.price,
                price_source=pos.price_source,
                value=None if pos.value is None else round(pos.value, 2),
                pnl=None if pos.pnl is None else round(pos.pnl, 2),
                pnl_pct=(
                    round(pos.pnl / pos.invested * 100, 2)
                    if pos.pnl is not None and pos.invested
                    else None
                ),
                lots=[LotOut(**lot.__dict__) for lot in pos.lots],
            )
            if pos
            else None
        ),
        weight=None if s.weight is None else round(s.weight, 4),
        max_weight=s.max_weight,
        sector=s.sector,
        sector_weight=None if s.sector_weight is None else round(s.sector_weight, 4),
        max_sector_weight=s.max_sector_weight,
        rebalance=RebalanceOut(**s.rebalance.__dict__),
        tax=TaxNoteOut(**s.tax.__dict__) if s.tax else None,
        price_freshness=fr_out(_price_freshness(s)),
        fundamental_freshness=fr_out(s.fundamental.freshness),
        notes=s.notes,
        disclaimer=get_profiles().disclaimer,
    )


@router.get("/signals/holdings", response_model=HoldingSignalsOut)
def holdings_signals(
    style: StyleKey | None = Query(None, description="Defaults to your saved style"),
    risk: RiskKey | None = Query(None, description="Defaults to your saved risk level"),
    session: Session = Depends(get_session),
) -> HoldingSignalsOut:
    """A signal for every current stock holding, from cached data only (no network).

    Each result is saved to the signal history for that style and risk level."""
    st, rk, ctw = active_profile(session, style, risk)
    profiles = get_profiles()
    style_key, notes = resolve_style(st)
    pf, sigs = evaluate_holdings(session, CachedProvider(session), style_key, rk, ctw)
    out: list[HoldingSignalOut] = []
    for s in sigs:
        pos = s.position
        peg = s.fundamental.metrics.get("peg")
        out.append(
            HoldingSignalOut(
                ticker=s.ticker,
                label=s.label,
                signal=s.signal,
                signal_label=s.signal_label,
                rule=s.rule,
                composite=s.score.score,
                technical=s.score.technical.score,
                fundamental=s.score.fundamental.score,
                confidence=s.score.confidence,
                weight=None if s.weight is None else round(s.weight, 4),
                max_weight=s.max_weight,
                quantity=pos.quantity if pos else None,
                avg_price=round(pos.avg_price, 2) if pos else None,
                price=None if pos is None or pos.price is None else round(pos.price, 2),
                invested=round(pos.invested, 2) if pos else None,
                value=None if pos is None or pos.value is None else round(pos.value, 2),
                pnl=None if pos is None or pos.pnl is None else round(pos.pnl, 2),
                pnl_pct=None
                if pos is None or pos.pnl is None or not pos.invested
                else round(pos.pnl / pos.invested * 100, 2),
                day_change=None
                if pos is None or pos.day_change is None
                else round(pos.day_change, 2),
                day_change_pct=None
                if pos is None or pos.day_change_pct is None
                else round(pos.day_change_pct, 2),
                peg=peg.value if peg else None,
                peg_basis=peg.basis if peg else None,
                sector=s.sector,
                flags=[FlagOut(**f.__dict__) for f in s.flags],
                top_bullish=[r.text for r in s.bullish],
                top_bearish=[r.text for r in s.bearish],
                rebalance=RebalanceOut(**s.rebalance.__dict__),
                stop=s.levels.trailing_stop if s.levels else None,
                stop_breached=bool(s.levels and s.levels.stop_breached),
                price_freshness=fr_out(_price_freshness(s)),
            )
        )
    risk_level = profiles.risk_levels[rk]
    style_cfg = profiles.styles[style_key]
    sectors = sorted(
        (
            SectorWeightOut(
                sector=name,
                weight=round(v / pf.total, 4),
                limit=risk_level.max_weight_per_sector,
                over=v / pf.total > risk_level.max_weight_per_sector,
            )
            for name, v in pf.sector_values.items()
            if pf.total > 0
        ),
        key=lambda x: -x.weight,
    )
    return HoldingSignalsOut(
        style=style_key,
        style_label=style_cfg.label,
        risk=rk,
        risk_label=risk_level.label,
        technical_weight=ctw if style_key == "custom" else style_cfg.technical_weight,
        weight_base=pf.base,
        total_value=round(pf.total, 2),
        stock_value=round(pf.stock_value, 2),
        fund_value=round(pf.fund_value, 2),
        sectors=sectors,
        holdings=out,
        notes=notes + pf.notes,
        disclaimer=profiles.disclaimer,
    )


@router.get("/stock/{ticker}", response_model=StockSignalOut)
def stock_signal(
    ticker: str = Path(pattern=TICKER, description="Yahoo ticker, e.g. RELIANCE.NS"),
    style: StyleKey | None = Query(None, description="Defaults to your saved style"),
    risk: RiskKey | None = Query(None, description="Defaults to your saved risk level"),
    fetch: bool = Query(True, description="Fetch missing or stale data first"),
    session: Session = Depends(get_session),
) -> StockSignalOut:
    """Signal, scores, reasons, stop-loss, targets, position size and tax note for one stock."""
    st, rk, ctw = active_profile(session, style, risk)
    provider = CachedProvider(session)
    pf = load_portfolio(session, provider, get_profiles().rebalance)
    s = analyse_stock(
        session,
        provider,
        ticker.upper(),
        style=st,
        risk_key=rk,
        custom_technical_weight=ctw,
        portfolio=pf,
        fetch=fetch,
    )
    return signal_out(s)


@router.get("/stock/{ticker}/history", response_model=list[SignalHistoryOut])
def stock_history(
    ticker: str = Path(pattern=TICKER),
    style: StyleKey | None = None,
    session: Session = Depends(get_session),
) -> list[SignalHistoryOut]:
    """Past daily signals (recorded whenever holdings' signals are computed)."""
    return [
        SignalHistoryOut(
            day=r.day,
            style=r.style,
            risk=r.risk,
            signal=r.signal,
            signal_label=SIGNAL_LABEL.get(r.signal, r.signal),
            composite=r.composite,
            technical=r.technical,
            fundamental=r.fundamental,
            confidence=r.confidence,
        )
        for r in history(session, ticker.upper(), style)
    ]


@router.get("/backtest/{ticker}", response_model=BacktestResult)
def backtest(
    ticker: str = Path(pattern=TICKER, description="Yahoo ticker, e.g. RELIANCE.NS"),
    style: StyleKey | None = Query(None, description="Defaults to your saved style"),
    risk: RiskKey | None = Query(None, description="Defaults to your saved risk level"),
    fetch: bool = Query(True, description="Fetch missing or stale prices first"),
    session: Session = Depends(get_session),
) -> BacktestResult:
    """Replay the technical signal rules over the last few years (`backtest:` in profiles.yaml).

    A historical test only: it reports how often past signals were followed by the expected
    move, and a rule-following strategy vs buy-and-hold. It does not predict the future."""
    st, rk, _ = active_profile(session, style, risk)
    style_key, notes = resolve_style(st)
    res = _backtests.get(
        session,
        (ticker.upper(), style_key, rk, fetch),
        lambda s: run_backtest(
            CachedProvider(s), ticker, style=style_key, risk_key=rk, fetch=fetch
        ),
    )
    return replace(res, notes=notes + res.notes)  # the cached result stays as is


# A replay takes a few seconds; opening the same stock's backtest again reuses it.
_backtests: Memo[BacktestResult] = Memo("backtest", timedelta(minutes=30), size=32)
