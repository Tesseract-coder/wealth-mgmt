"""Market data: freshness overview, price/NAV series, and manual refresh."""

from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, Path, Query
from sqlmodel import Session, col, select

from app.api.jobs import job_out
from app.core.db import get_session
from app.core.formatting import IST, now_ist
from app.core.profiles import get_profiles
from app.core.settings import get_settings
from app.data import store
from app.data.freshness import Freshness
from app.data.navs import nav_freshness, nav_key, refresh_nav
from app.data.prices import (
    get_daily,
    get_intraday,
    price_key,
    refresh_daily,
    refresh_intraday,
)
from app.data.quotes import quotes
from app.data.reference_refresh import reference_status
from app.importers.reference import scheme_resolver
from app.jobs.runner import get_runner
from app.jobs.scheduler import scheduled_jobs
from app.jobs.tasks import FUND_JOB_KIND, JOB_KIND, fundamentals_refresh, market_refresh
from app.models.schemas import (
    BarOut,
    FreshnessOut,
    JobOut,
    MarketStatusOut,
    NavPointOut,
    NavSeriesOut,
    PriceSeriesOut,
    QuoteOut,
    ReferenceStatusOut,
    RefreshIn,
    ScheduledJobOut,
    ScheduleOut,
)
from app.models.tables import Job, SheetSettings

router = APIRouter(prefix="/market", tags=["market"])

TICKER = r"^[A-Za-z0-9^&._\-]{1,30}$"
Interval = Literal["1d", "1wk", "1mo", "15m", "1h"]


def fr_out(f: Freshness) -> FreshnessOut:
    return FreshnessOut(status=f.status, reason=f.reason)


@router.get("/status", response_model=MarketStatusOut)
def status(session: Session = Depends(get_session)) -> MarketStatusOut:
    now = now_ist()
    cfg = get_profiles().data
    qs = [
        QuoteOut(
            kind=q.kind,
            code=q.code,
            label=q.label,
            price=q.price,
            previous=q.previous,
            change_pct=q.change_pct,
            as_of=q.as_of,
            source=q.source,
            freshness=fr_out(q.freshness),
        )
        for q in quotes(session, now)
    ]
    refs = [
        ReferenceStatusOut(
            key=r.key,
            label=r.label,
            source=r.source,
            origin=r.origin,
            as_of=r.as_of,
            rows=r.rows,
            freshness=fr_out(r.freshness),
        )
        for r in reference_status(session, now)
    ]
    summary = {"fresh": 0, "stale": 0, "unavailable": 0}
    for q in qs:
        summary[q.freshness.status] += 1
    last = session.exec(
        select(Job).where(Job.kind == JOB_KIND).order_by(col(Job.id).desc())
    ).first()
    last_fund = session.exec(
        select(Job).where(Job.kind == FUND_JOB_KIND).order_by(col(Job.id).desc())
    ).first()
    fcfg = get_profiles().fundamental
    return MarketStatusOut(
        generated_at=now,
        summary=summary,
        references=refs,
        quotes=qs,
        schedule=ScheduleOut(
            enabled=get_settings().scheduler_enabled,
            prices=f"Mon–Fri {cfg.refresh_time_ist} IST",
            navs=f"Daily {cfg.nav_refresh_time_ist} IST",
            fundamentals=f"Weekly, {fcfg.refresh_day.capitalize()} {fcfg.refresh_time_ist} IST",
            jobs=[
                ScheduledJobOut(id=j.id, name=j.name, next_run=j.next_run) for j in scheduled_jobs()
            ],
            sheets_auto_export=bool((sh := session.get(SheetSettings, 1)) and sh.auto_export),
            note=(
                "Scheduled refreshes run only while the app is running. A run missed by up to "
                "an hour still happens; anything older is caught up on the next start, which "
                "refreshes whatever is stale."
            ),
        ),
        last_job=job_out(last) if last else None,
        last_fundamentals_job=job_out(last_fund) if last_fund else None,
        notes=[
            "Prices are end-of-day closes from Yahoo Finance (free, unofficial, delayed). "
            "A day's bar is stored only once the session is over.",
            "NAVs come from mfapi.in and AMFI's daily NAV list.",
        ],
    )


@router.post("/refresh", response_model=JobOut, status_code=202)
def refresh(body: RefreshIn) -> JobOut:
    """scope=fundamentals runs as its own job (holdings + sector peers; can take a while)."""
    if body.scope == "fundamentals":
        job = get_runner().submit(
            FUND_JOB_KIND, fundamentals_refresh(body.force), params={"force": body.force}
        )
        return job_out(job)
    job = get_runner().submit(
        JOB_KIND,
        market_refresh(body.scope, body.force),
        params={"scope": body.scope, "force": body.force},
    )
    return job_out(job)


@router.get("/prices/{ticker}", response_model=PriceSeriesOut)
def prices(
    ticker: str = Path(pattern=TICKER, description="Yahoo ticker, e.g. RELIANCE.NS, ^NSEI"),
    interval: Interval = "1d",
    start: date | None = None,
    refresh: bool = Query(False, description="Fetch now if the cached series is stale"),
    session: Session = Depends(get_session),
) -> PriceSeriesOut:
    """Cached bars. With no cached data (or refresh=true) the series is fetched first.
    Intraday intervals are always fetched on demand when stale."""
    ticker = ticker.upper()
    fetch_error = None
    if interval in ("15m", "1h"):
        res = refresh_intraday(session, ticker, interval)
        fetch_error = res.message if res.outcome == "failed" else None
        bars = get_intraday(session, ticker, interval)
        out = [
            BarOut(
                t=ts.tz_convert(IST).isoformat(),
                open=r.open,
                high=r.high,
                low=r.low,
                close=r.close,
                volume=r.volume,
            )
            for ts, r in bars.frame.iterrows()
        ]
    else:
        st = store.get_status(session, price_key(ticker))
        if refresh or st is None or st.last_date is None:
            res = refresh_daily(session, ticker)
            fetch_error = res.message if res.outcome == "failed" else None
        bars = get_daily(session, ticker, interval, start)  # type: ignore[arg-type]
        out = [
            BarOut(
                t=d.isoformat(),
                open=_nan(r.open),
                high=_nan(r.high),
                low=_nan(r.low),
                close=float(r.close),
                adj_close=_nan(r.adj_close),
                volume=_nan(r.volume),
            )
            for d, r in bars.frame.iterrows()
        ]
    return PriceSeriesOut(
        ticker=ticker,
        interval=interval,
        source="yahoo",
        delayed=True,
        last_complete=bars.last_complete,
        freshness=fr_out(bars.freshness),
        fetch_error=fetch_error,
        bars=out,
    )


def _nan(v: object) -> float | None:
    if v is None:
        return None
    f = float(v)  # type: ignore[arg-type]
    return None if f != f else f


@router.get("/nav/{code}", response_model=NavSeriesOut)
def nav(
    code: str = Path(pattern=r"^\d{1,8}$"),
    start: date | None = None,
    refresh: bool = False,
    session: Session = Depends(get_session),
) -> NavSeriesOut:
    scheme = scheme_resolver().by_code.get(code)
    name = scheme.name if scheme else None
    st = store.get_status(session, nav_key(code))
    fetch_error = None
    if refresh or st is None or st.last_date is None:
        res = refresh_nav(session, code, name or code)
        fetch_error = res.message if res.outcome == "failed" else None
        st = store.get_status(session, nav_key(code))
    points = store.read_navs(session, code, start)
    last_date = points[-1].date if points else None
    return NavSeriesOut(
        code=code,
        scheme_name=name,
        freshness=fr_out(nav_freshness(last_date, st, now_ist())),
        fetch_error=fetch_error,
        points=[NavPointOut(date=p.date, nav=p.nav) for p in points],
    )
