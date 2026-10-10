"""Technical analysis endpoints. Signals and scores come in Phase 6; these show the readings."""

import math
from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, Path, Query
from sqlmodel import Session

from app.analysis.fundamental import FundamentalReport, analyse_fundamentals
from app.analysis.technical import (
    FrameAnalysis,
    Interval,
    TechnicalReport,
    analyse,
    indicator_series,
)
from app.api.market import TICKER, fr_out
from app.core.db import get_session
from app.core.profiles import RiskLevel, StyleKey, get_profiles
from app.data.prices import get_daily, get_intraday
from app.data.provider import CachedProvider
from app.data.quotes import stock_targets
from app.models.schemas import (
    FrameAnalysisOut,
    FScoreOut,
    FTestOut,
    FundamentalReportOut,
    FundamentalSummaryOut,
    IndicatorSeriesOut,
    LevelOut,
    MetricOut,
    ObservationOut,
    TechnicalReportOut,
    TechnicalSummaryOut,
    TimeframeOut,
)
from app.models.tables import UserProfile

router = APIRouter(prefix="/analysis", tags=["analysis"])


def _frame_out(a: FrameAnalysis) -> FrameAnalysisOut:
    return FrameAnalysisOut(
        values=a.values,
        observations=[ObservationOut(**o.__dict__) for o in a.observations],
        unavailable=a.unavailable,
        levels=[LevelOut(price=lv.price, touches=lv.touches, kind=lv.kind) for lv in a.levels],
    )


def report_out(r: TechnicalReport) -> TechnicalReportOut:
    return TechnicalReportOut(
        ticker=r.ticker,
        label=r.label,
        style=r.style,
        timeframes=[
            TimeframeOut(
                interval=tf.interval,
                bars=tf.bars,
                as_of=tf.as_of,
                last_close=tf.last_close,
                last_complete=tf.last_complete,
                freshness=fr_out(tf.freshness),
                analysis=_frame_out(tf.analysis),
                notes=tf.notes,
            )
            for tf in r.timeframes
        ],
        context=_frame_out(r.context),
        fetch_errors=r.fetch_errors,
        notes=r.notes,
        disclaimer=get_profiles().disclaimer,
    )


def _active_risk(session: Session) -> tuple[RiskLevel, str]:
    profiles = get_profiles()
    p = session.get(UserProfile, 1)
    key = p.risk if p and p.risk in profiles.risk_levels else profiles.defaults.risk
    level = profiles.risk_levels[key]
    return level, level.label


def fundamental_out(r: FundamentalReport) -> FundamentalReportOut:
    return FundamentalReportOut(
        ticker=r.ticker,
        label=r.label,
        sector=r.sector,
        is_financial=r.is_financial,
        source=r.source,
        latest_year=r.latest_year,
        freshness=fr_out(r.freshness),
        metrics=[MetricOut(**m.__dict__) for m in r.metrics.values()],
        fscore=(
            FScoreOut(
                score=r.fscore.score,
                computable=r.fscore.computable,
                tests=[FTestOut(**t.__dict__) for t in r.fscore.tests],
            )
            if r.fscore
            else None
        ),
        observations=[ObservationOut(**o.__dict__) for o in r.observations],
        unavailable=r.unavailable,
        notes=r.notes,
        fetch_errors=r.fetch_errors,
        disclaimer=get_profiles().disclaimer,
    )


@router.get("/fundamental/holdings", response_model=list[FundamentalSummaryOut])
def holdings_fundamental(session: Session = Depends(get_session)) -> list[FundamentalSummaryOut]:
    """Fundamentals for every current stock holding, from cached data only (no network)."""
    risk, risk_label = _active_risk(session)
    provider = CachedProvider(session)
    out = []
    for t in stock_targets(session):
        r = analyse_fundamentals(
            session, provider, t.code, label=t.label, risk=risk, risk_label=risk_label, fetch=False
        )
        major = [o for o in r.observations if not o.minor]

        def val(k: str, rep: FundamentalReport = r) -> float | None:
            return rep.metrics[k].value if k in rep.metrics else None

        out.append(
            FundamentalSummaryOut(
                ticker=t.code,
                label=t.label,
                sector=r.sector,
                source=r.source,
                freshness=fr_out(r.freshness),
                pe=val("pe"),
                roe=val("roe"),
                debt_equity=val("debt_equity"),
                fscore=r.fscore.score if r.fscore else None,
                bullish=sum(o.direction == "bullish" for o in major),
                bearish=sum(o.direction == "bearish" for o in major),
                top_bullish=[o.text for o in major if o.direction == "bullish"][:3],
                top_bearish=[o.text for o in major if o.direction == "bearish"][:3],
            )
        )
    return out


@router.get("/fundamental/{ticker}", response_model=FundamentalReportOut)
def fundamental(
    ticker: str = Path(pattern=TICKER, description="Yahoo ticker, e.g. RELIANCE.NS"),
    fetch: bool = Query(True, description="Fetch Yahoo fundamentals if missing or stale"),
    session: Session = Depends(get_session),
) -> FundamentalReportOut:
    risk, risk_label = _active_risk(session)
    r = analyse_fundamentals(
        session,
        CachedProvider(session),
        ticker.upper(),
        risk=risk,
        risk_label=risk_label,
        fetch=fetch,
    )
    return fundamental_out(r)


def _active_style(session: Session) -> StyleKey | None:
    p = session.get(UserProfile, 1)
    return p.style if p and p.style else None  # type: ignore[return-value]


@router.get("/technical/holdings", response_model=list[TechnicalSummaryOut])
def holdings_technical(
    style: StyleKey | None = None, session: Session = Depends(get_session)
) -> list[TechnicalSummaryOut]:
    """Readings for every current stock holding on the style's main timeframe.

    Uses cached prices only (run a market-data refresh first); no network calls."""
    style = style or _active_style(session)
    provider = CachedProvider(session)
    out = []
    for t in stock_targets(session):
        r = analyse(provider, t.code, label=t.label, style=style, fetch=False)
        tf = r.timeframes[0]
        obs = tf.analysis.observations + r.context.observations
        major = [o for o in obs if not o.minor]
        out.append(
            TechnicalSummaryOut(
                ticker=t.code,
                label=t.label,
                interval=tf.interval,
                as_of=tf.as_of,
                freshness=fr_out(tf.freshness),
                bullish=sum(o.direction == "bullish" for o in major),
                bearish=sum(o.direction == "bearish" for o in major),
                neutral=sum(o.direction == "neutral" for o in major),
                top_bullish=[o.text for o in major if o.direction == "bullish"][:3],
                top_bearish=[o.text for o in major if o.direction == "bearish"][:3],
            )
        )
    return out


@router.get("/technical/{ticker}", response_model=TechnicalReportOut)
def technical(
    ticker: str = Path(pattern=TICKER, description="Yahoo ticker, e.g. RELIANCE.NS"),
    style: StyleKey | None = Query(None, description="Defaults to your saved style"),
    timeframes: list[Interval] | None = Query(None, description="Overrides the style"),
    fetch: bool = Query(True, description="Fetch missing or stale data first"),
    session: Session = Depends(get_session),
) -> TechnicalReportOut:
    style = style or _active_style(session)
    r = analyse(
        CachedProvider(session),
        ticker.upper(),
        style=style,
        timeframes=list(timeframes) if timeframes else None,
        fetch=fetch,
    )
    return report_out(r)


def _clean(v: object) -> float | None:
    f = float(v)  # type: ignore[arg-type]
    return None if math.isnan(f) else round(f, 4)


@router.get("/technical/{ticker}/series", response_model=IndicatorSeriesOut)
def technical_series(
    ticker: str = Path(pattern=TICKER),
    interval: Literal["1d", "1wk", "1mo", "15m", "1h"] = "1d",
    start: date | None = None,
    session: Session = Depends(get_session),
) -> IndicatorSeriesOut:
    """Indicator lines for charts, computed on the full cached history then cut to `start`."""
    ticker = ticker.upper()
    if interval in ("15m", "1h"):
        df = get_intraday(session, ticker, interval).frame
    else:
        df = get_daily(session, ticker, interval).frame  # type: ignore[arg-type]
    if df.empty:
        return IndicatorSeriesOut(ticker=ticker, interval=interval, t=[], columns={})
    series = indicator_series(df, get_profiles().technical)
    if start is not None:
        keep = [
            (i.date() if hasattr(i, "date") and callable(i.date) else i) >= start
            for i in series.index
        ]
        series = series[keep]
    return IndicatorSeriesOut(
        ticker=ticker,
        interval=interval,
        t=[i.isoformat() for i in series.index],
        columns={c: [_clean(v) for v in series[c]] for c in series.columns},
    )
