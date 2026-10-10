from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, col, select

from app.analysis.signals import SIGNAL_LABEL, active_profile, resolve_style
from app.core.db import get_session
from app.core.profiles import get_profiles
from app.data.provider import CachedProvider
from app.jobs.runner import ACTIVE, get_runner
from app.models.schemas import (
    FlagOut,
    FreshnessOut,
    SignalChangeOut,
    WatchIn,
    WatchItemOut,
    WatchlistOut,
    WatchNoteIn,
)
from app.models.tables import Job, WatchItem
from app.screener import watchlist as wl

router = APIRouter(prefix="/watchlist", tags=["watchlist"])


def item_out(v: wl.WatchView) -> WatchItemOut:
    w, s = v.item, v.signal
    price = s.levels.close if s and s.levels else None
    chg = v.change
    tf = s.technical.timeframes[0] if s and s.technical.timeframes else None
    return WatchItemOut(
        ticker=w.ticker,
        label=w.label,
        note=w.note,
        source=w.source,
        added_at=w.added_at,
        added_price=w.added_price,
        added_signal=w.added_signal,
        added_signal_label=SIGNAL_LABEL.get(w.added_signal) if w.added_signal else None,
        added_score=w.added_score,
        held=v.held,
        status="ok" if s else "no_data",
        signal=s.signal if s else None,
        signal_label=s.signal_label if s else None,
        rule=s.rule if s else None,
        confidence=s.score.confidence if s else None,
        composite=s.score.score if s else None,
        score_change=(
            round(s.score.score - w.added_score, 1)
            if s and s.score.score is not None and w.added_score is not None
            else None
        ),
        price=price,
        price_as_of=s.levels.as_of[:10] if s and s.levels else None,
        price_change_pct=(
            round((price / w.added_price - 1) * 100, 2) if price and w.added_price else None
        ),
        signal_changed_since_added=bool(s and w.added_signal and s.signal != w.added_signal),
        last_change=(
            SignalChangeOut(
                previous=chg.previous,
                previous_label=SIGNAL_LABEL[chg.previous],
                current=chg.current,
                current_label=SIGNAL_LABEL[chg.current],
                day=chg.day,
            )
            if chg
            else None
        ),
        stop=s.levels.entry_stop if s and s.levels else None,
        stop_breached=bool(s and s.levels and s.levels.stop_breached),
        bullish=[r.text for r in s.bullish] if s else [],
        bearish=[r.text for r in s.bearish] if s else [],
        flags=[FlagOut(key=f.key, severe=f.severe, text=f.text) for f in s.flags] if s else [],
        sector=s.sector if s else None,
        price_freshness=(
            FreshnessOut(status=tf.freshness.status, reason=tf.freshness.reason) if tf else None
        ),
    )


def fetching_job(session: Session) -> int | None:
    job = session.exec(
        select(Job)
        .where(Job.kind == wl.FETCH_JOB_KIND, col(Job.status).in_(ACTIVE))
        .order_by(col(Job.id).desc())
    ).first()
    return job.id if job else None


@router.get("", response_model=WatchlistOut)
def get_watchlist(session: Session = Depends(get_session)) -> WatchlistOut:
    """Each watched stock scored now (cached data, your style and risk) and what changed."""
    p = get_profiles()
    style, risk, _ = active_profile(session)
    style_key, _ = resolve_style(style)
    views = wl.view(session, CachedProvider(session))
    return WatchlistOut(
        style_label=p.styles[style_key].label,
        risk_label=p.risk_levels[risk].label,
        items=[item_out(v) for v in views],
        fetching_job_id=fetching_job(session),
        disclaimer=p.disclaimer,
    )


@router.get("/tickers", response_model=list[str])
def watched_tickers(session: Session = Depends(get_session)) -> list[str]:
    """Just the tickers (cheap): for Watch buttons elsewhere in the app."""
    return [w.ticker for w in wl.items(session)]


@router.post("", response_model=WatchItemOut, status_code=201)
def add_to_watchlist(body: WatchIn, session: Session = Depends(get_session)) -> WatchItemOut:
    """Watch an NSE stock. If nothing is cached for it yet, a background download starts."""
    provider = CachedProvider(session)
    try:
        w, _ = wl.add(session, provider, body.ticker, note=body.note, source=body.source)
    except wl.WatchError as e:
        raise HTTPException(422, str(e)) from e
    if provider.daily(w.ticker).frame.empty:
        get_runner().submit(wl.FETCH_JOB_KIND, wl.fetch_job())
    v = next(x for x in wl.view(session, provider) if x.item.ticker == w.ticker)
    return item_out(v)


@router.patch("/{ticker}", response_model=WatchItemOut)
def edit_note(
    ticker: str, body: WatchNoteIn, session: Session = Depends(get_session)
) -> WatchItemOut:
    w = session.get(WatchItem, ticker)
    if w is None:
        raise HTTPException(404, f"{ticker} is not on your watchlist")
    w.note = (body.note or "").strip() or None
    session.add(w)
    session.commit()
    v = next(x for x in wl.view(session, CachedProvider(session)) if x.item.ticker == ticker)
    return item_out(v)


@router.delete("/{ticker}", status_code=204)
def remove(ticker: str, session: Session = Depends(get_session)) -> None:
    w = session.get(WatchItem, ticker)
    if w is None:
        raise HTTPException(404, f"{ticker} is not on your watchlist")
    session.delete(w)
    session.commit()
