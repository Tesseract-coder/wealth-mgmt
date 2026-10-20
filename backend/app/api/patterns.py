"""Chart-pattern endpoints: the pattern guide, one stock's patterns, and a scan of your holdings."""

from dataclasses import asdict
from datetime import timedelta
from typing import Literal

import pandas as pd
from fastapi import APIRouter, Depends, Path, Query
from sqlmodel import Session

from app.analysis.patterns import LIBRARY, PatternMatch, detect
from app.analysis.technical import INTRADAY, UNIT, Interval, _iso, timeframes_for
from app.api.market import TICKER
from app.core.db import get_session
from app.core.formatting import format_inr
from app.core.memo import Memo
from app.core.profiles import StyleKey, get_profiles
from app.data.provider import CachedProvider, DataProvider
from app.data.quotes import stock_targets
from app.models.schemas import (
    PatternHoldingOut,
    PatternInfoOut,
    PatternLineOut,
    PatternOut,
    PatternPointOut,
    PatternReportOut,
    PatternWindowOut,
)
from app.models.tables import UserProfile

router = APIRouter(prefix="/analysis", tags=["patterns"])

LEAD_IN = 20  # bars drawn before the earliest pattern starts


def _strength(confidence: int) -> Literal["strong", "moderate", "weak"]:
    return "strong" if confidence >= 70 else "moderate" if confidence >= 55 else "weak"


def _pct(v: float | None, close: float | None) -> float | None:
    return None if v is None or not close else round((v / close - 1) * 100, 2)


def _pattern_out(m: PatternMatch, df: pd.DataFrame) -> PatternOut:
    t = [_iso(i) or "" for i in df.index]
    close = float(df["close"].iloc[-1])
    info = LIBRARY[m.key]
    return PatternOut(
        key=m.key,
        name=info.name,
        family=info.family,
        direction=m.direction,
        status=m.status,
        confidence=m.confidence,
        strength=_strength(m.confidence),
        start=t[m.start],
        end=t[m.end],
        bars=m.end - m.start + 1,
        breakout=m.breakout,
        target=m.target,
        invalidation=m.invalidation,
        target_pct=_pct(m.target, close),
        invalidation_pct=_pct(m.invalidation, close),
        bars_since_breakout=m.bars_since_breakout,
        volume_confirmed=m.volume_confirmed,
        text=m.text,
        points=[PatternPointOut(t=t[p.i], price=p.price, label=p.label) for p in m.points],
        lines=[
            PatternLineOut(
                label=ln.label,
                kind=ln.kind,
                points=[PatternPointOut(t=t[i], price=v) for i, v in ln.points],
            )
            for ln in m.lines
        ],
    )


def _frame(provider: DataProvider, ticker: str, interval: Interval, fetch: bool) -> pd.DataFrame:
    if interval in INTRADAY:
        if fetch:
            provider.ensure_intraday(ticker, interval)  # type: ignore[arg-type]
        return provider.intraday(ticker, interval).frame  # type: ignore[arg-type]
    if fetch:
        provider.ensure_daily(ticker, None)
    return provider.daily(ticker, interval).frame  # type: ignore[arg-type]


def _matches(df: pd.DataFrame, ticker: str, interval: Interval) -> list[PatternMatch]:
    tech = get_profiles().technical
    is_index = ticker.startswith("^")
    return detect(
        df,
        tech.patterns,
        volume_surge=tech.thresholds.volume_surge,
        unit=UNIT[interval],
        px=(lambda v: f"{v:,.2f}") if is_index else format_inr,
    )


@router.get("/patterns/library", response_model=list[PatternInfoOut])
def pattern_library() -> list[PatternInfoOut]:
    """Every pattern the scanner looks for: what it means and how it's traded."""
    return [PatternInfoOut(**asdict(p)) for p in LIBRARY.values()]


@router.get("/technical/{ticker}/patterns", response_model=PatternReportOut)
def stock_patterns(
    ticker: str = Path(pattern=TICKER, description="Yahoo ticker, e.g. RELIANCE.NS"),
    interval: Interval = "1d",
    fetch: bool = Query(True, description="Fetch missing or stale data first"),
    session: Session = Depends(get_session),
) -> PatternReportOut:
    """Chart patterns in play on one stock's chart: forming, or confirmed in the last few bars."""
    ticker = ticker.upper()
    df = _frame(CachedProvider(session), ticker, interval, fetch).dropna(subset=["close"])
    notes = ["Patterns are a guide, not a promise: many fail. Wait for the confirming close."]
    if interval in INTRADAY:
        notes.append("Intraday bars from Yahoo Finance are delayed, so patterns lag the market.")
    if df.empty:
        return PatternReportOut(
            ticker=ticker,
            interval=interval,
            unit=UNIT[interval],
            bars=0,
            as_of=None,
            last_close=None,
            patterns=[],
            window=PatternWindowOut(t=[], open=[], high=[], low=[], close=[]),
            notes=notes,
        )
    found = _matches(df, ticker, interval)
    first = min((m.start for m in found), default=max(0, len(df) - 120))
    w = df.iloc[max(0, first - LEAD_IN) :]
    c = w["close"]
    return PatternReportOut(
        ticker=ticker,
        interval=interval,
        unit=UNIT[interval],
        bars=len(df),
        as_of=_iso(df.index[-1]),
        last_close=round(float(c.iloc[-1]), 2),
        patterns=[_pattern_out(m, df) for m in found],
        window=PatternWindowOut(
            t=[_iso(i) or "" for i in w.index],
            open=[round(float(v), 2) for v in w["open"].fillna(c)],
            high=[round(float(v), 2) for v in w["high"].fillna(c)],
            low=[round(float(v), 2) for v in w["low"].fillna(c)],
            close=[round(float(v), 2) for v in c],
        ),
        notes=notes,
    )


@router.get("/patterns/holdings", response_model=list[PatternHoldingOut])
def holdings_patterns(
    style: StyleKey | None = None,
    interval: Interval | None = Query(None, description="Defaults to your style's chart"),
    session: Session = Depends(get_session),
) -> list[PatternHoldingOut]:
    """Patterns on every current stock holding. Cached prices only: no network calls."""
    if style is None:
        p = session.get(UserProfile, 1)
        style = p.style if p and p.style else None  # type: ignore[assignment]
    # Intraday styles still scan the daily chart by default: patterns there are more reliable.
    main: Interval = next((t for t in timeframes_for(style) if t not in INTRADAY), "1d")
    iv = interval or main
    return _holdings_patterns.get(session, iv, lambda s: _patterns_for_holdings(s, iv))


_holdings_patterns: Memo[list[PatternHoldingOut]] = Memo(
    "holdings patterns", timedelta(minutes=5), size=4
)


def _patterns_for_holdings(session: Session, iv: Interval) -> list[PatternHoldingOut]:
    provider = CachedProvider(session)
    out = []
    for t in stock_targets(session):
        df = _frame(provider, t.code, iv, fetch=False).dropna(subset=["close"])
        found = _matches(df, t.code, iv) if len(df) else []
        out.append(
            PatternHoldingOut(
                ticker=t.code,
                label=t.label,
                interval=iv,
                as_of=_iso(df.index[-1]) if len(df) else None,
                bars=len(df),
                patterns=[_pattern_out(m, df) for m in found],
            )
        )
    return out
