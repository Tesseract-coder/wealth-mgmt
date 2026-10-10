import json

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session, col, select

from app.analysis.positions import load_portfolio
from app.analysis.signals import active_profile, resolve_style
from app.api.jobs import job_out
from app.core.db import get_session
from app.core.profiles import ScreenFilter, get_profiles
from app.data.indices import INDEX_KEYS, load_index
from app.data.provider import CachedProvider
from app.data.yahoo import STATEMENTS
from app.jobs.runner import get_runner
from app.models.schemas import (
    CandidateOut,
    EntryLevelsOut,
    FlagOut,
    NearMissOut,
    PresetOut,
    SavedScreenIn,
    SavedScreenOut,
    ScanIn,
    ScanOut,
    ScreenerConfigOut,
    ScreenerJobOut,
    ScreenFieldOut,
    ScreenFilterIO,
    ScreenIn,
    ScreenResultOut,
    SectorImpactOut,
    TargetOut,
    UniverseOut,
)
from app.models.tables import Job, SavedScreen, ScreenerScan, WatchItem, utcnow
from app.screener.fields import FIELDS, OPS
from app.screener.scan import (
    JOB_KIND,
    ScanParams,
    load_rows,
    parse_symbols,
    screener_job,
    universe_label,
)
from app.screener.screens import ScreenResult, screen

router = APIRouter(prefix="/screener", tags=["screener"])


def scan_out(s: ScreenerScan) -> ScanOut:
    p = get_profiles()
    assert s.id is not None
    return ScanOut(
        id=s.id,
        job_id=s.job_id,
        universe=s.universe,
        universe_label=s.universe_label,
        style=s.style,
        style_label=p.styles[s.style].label if s.style in p.styles else s.style,
        risk=s.risk,
        risk_label=p.risk_levels[s.risk].label if s.risk in p.risk_levels else s.risk,
        fetch=s.fetch,
        status=s.status,
        created_at=s.created_at,
        finished_at=s.finished_at,
        total=s.total,
        scored=s.scored,
        notes=json.loads(s.notes_json),
    )


def saved_out(s: SavedScreen) -> SavedScreenOut:
    assert s.id is not None
    return SavedScreenOut(
        id=s.id,
        name=s.name,
        filters=[ScreenFilterIO(**f) for f in json.loads(s.filters_json)],
        updated_at=s.updated_at,
    )


def latest_scan(session: Session) -> ScreenerScan | None:
    return session.exec(
        select(ScreenerScan)
        .where(col(ScreenerScan.status).in_(("complete", "partial")))
        .order_by(col(ScreenerScan.id).desc())
    ).first()


def validate_filters(fs: list[ScreenFilterIO]) -> list[ScreenFilter]:
    try:
        return [ScreenFilter(**f.model_dump()) for f in fs]
    except ValueError as e:  # pydantic's ValidationError is a ValueError
        msg = "; ".join(str(x["msg"]).removeprefix("Value error, ") for x in e.errors())  # type: ignore[attr-defined]
        raise HTTPException(422, msg) from e


@router.get("/config", response_model=ScreenerConfigOut)
def screener_config(session: Session = Depends(get_session)) -> ScreenerConfigOut:
    """Universes, presets (from profiles.yaml), filter fields, your saved screens, last scan."""
    p = get_profiles()
    cfg = p.screener
    screens = session.exec(select(SavedScreen).order_by(col(SavedScreen.name))).all()
    latest = latest_scan(session)
    return ScreenerConfigOut(
        universes=[
            UniverseOut(key=k, label=universe_label(k), size=len(load_index(k))) for k in INDEX_KEYS
        ]
        + [UniverseOut(key="custom", label="Custom list", size=None)],
        default_universe=cfg.default_universe,
        custom_universe_max=cfg.custom_universe_max,
        # 1 price request + the fundamentals requests (info and 4 statements) per stock
        seconds_per_stock=round(
            (1 + len(STATEMENTS) + 1) * 60 / p.data.rate_limits_per_minute["yahoo"]
            + cfg.request_delay_seconds,
            1,
        ),
        presets=[
            PresetOut(
                key=k,
                label=v.label,
                description=v.description,
                filters=[ScreenFilterIO(**f.model_dump()) for f in v.filters],
            )
            for k, v in cfg.presets.items()
        ],
        fields=[ScreenFieldOut(**f.__dict__) for f in FIELDS],
        ops=OPS,
        screens=[saved_out(s) for s in screens],
        top_n=cfg.top_n,
        latest_scan=scan_out(latest) if latest else None,
        disclaimer=p.disclaimer,
    )


@router.post("/run", response_model=ScreenerJobOut, status_code=202)
def run_screener(body: ScanIn, session: Session = Depends(get_session)) -> ScreenerJobOut:
    """Start a scan as a background job. Poll GET /screener/jobs/{id} for progress.

    `fetch: "missing"` downloads prices and fundamentals that aren't cached or are stale
    (a first full Nifty 500 scan can take most of an hour at the free sources' rate limits);
    `"cached"` uses only what is already downloaded and finishes in a couple of minutes."""
    p = get_profiles()
    universe = body.universe or p.screener.default_universe
    symbols: list[str] = []
    if universe == "custom":
        symbols = parse_symbols(body.symbols or "")
        if not symbols:
            raise HTTPException(422, "A custom universe needs at least one NSE symbol")
        if len(symbols) > p.screener.custom_universe_max:
            raise HTTPException(
                422, f"At most {p.screener.custom_universe_max} symbols in a custom list"
            )
    saved_style, saved_risk, ctw = active_profile(session)
    style, _ = resolve_style(body.style or saved_style)
    params = ScanParams(
        universe=universe,
        style=style,
        risk=body.risk or saved_risk,
        custom_technical_weight=ctw,
        fetch=body.fetch,
        symbols=symbols,
    )
    job = get_runner().submit(
        JOB_KIND,
        screener_job(params),
        params={
            "universe": universe,
            "fetch": body.fetch,
            "style": style,
            "risk": params.risk,
            "symbols": len(symbols),
        },
    )
    return screener_job_out(session, job)


def screener_job_out(session: Session, job: Job) -> ScreenerJobOut:
    scan = session.exec(select(ScreenerScan).where(ScreenerScan.job_id == job.id)).first()
    return ScreenerJobOut(job=job_out(job), scan=scan_out(scan) if scan else None)


@router.get("/jobs/{job_id}", response_model=ScreenerJobOut)
def screener_job_status(job_id: int, session: Session = Depends(get_session)) -> ScreenerJobOut:
    job = session.get(Job, job_id)
    if job is None or job.kind != JOB_KIND:
        raise HTTPException(404, "No such screener job")
    session.refresh(job)
    return screener_job_out(session, job)


@router.get("/active", response_model=ScreenerJobOut | None)
def active_job(session: Session = Depends(get_session)) -> ScreenerJobOut | None:
    """The scan that is queued or running, if any (so a reloaded page can show its progress)."""
    job = session.exec(
        select(Job)
        .where(Job.kind == JOB_KIND, col(Job.status).in_(("queued", "running")))
        .order_by(col(Job.id).desc())
    ).first()
    return screener_job_out(session, job) if job else None


@router.get("/scans", response_model=list[ScanOut])
def list_scans(session: Session = Depends(get_session)) -> list[ScanOut]:
    rows = session.exec(select(ScreenerScan).order_by(col(ScreenerScan.id).desc())).all()
    return [scan_out(s) for s in rows]


def resolve_screen(session: Session, body: ScreenIn) -> tuple[str, list[ScreenFilter]]:
    p = get_profiles()
    if body.filters is not None:
        return "Custom filters", validate_filters(body.filters)
    if body.screen_id is not None:
        saved = session.get(SavedScreen, body.screen_id)
        if saved is None:
            raise HTTPException(404, "No such saved screen")
        fs = [ScreenFilterIO(**f) for f in json.loads(saved.filters_json)]
        return saved.name, validate_filters(fs)
    key = body.preset or next(iter(p.screener.presets))
    preset = p.screener.presets.get(key)
    if preset is None:
        raise HTTPException(404, f"No preset '{key}'")
    return preset.label, list(preset.filters)


def run_screen(session: Session, body: ScreenIn) -> tuple[ScreenerScan, str, ScreenResult]:
    scan = session.get(ScreenerScan, body.scan_id) if body.scan_id else latest_scan(session)
    if scan is None:
        raise HTTPException(404, "No scan yet. Run a scan first.")
    if scan.status in ("running", "failed"):
        raise HTTPException(409, f"Scan {scan.id} is {scan.status}")
    title, filters = resolve_screen(session, body)
    p = get_profiles()
    risk = p.risk_levels[scan.risk]  # type: ignore[index]
    pf = load_portfolio(session, CachedProvider(session), p.rebalance)
    result = screen(
        load_rows(scan),
        filters,
        p,
        risk,
        pf if pf.total > 0 else None,
        include_held=body.include_held,
        top_n=body.top_n,
    )
    return scan, title, result


@router.post("/screen", response_model=ScreenResultOut)
def screen_scan(body: ScreenIn, session: Session = Depends(get_session)) -> ScreenResultOut:
    """Apply a preset, a saved screen or ad-hoc filters to a stored scan (instant: no
    downloads). Returns the top candidates with entry zone, stop, targets and sector effect."""
    scan, title, res = run_screen(session, body)
    watched = {w.ticker for w in session.exec(select(WatchItem))}
    style, risk, _ = active_profile(session)
    stale = None
    if (style and style != scan.style) or risk != scan.risk:
        stale = (
            "This scan was scored with a different style or risk level than your current "
            "profile. Run a new scan to use your current settings."
        )
    p = get_profiles()
    return ScreenResultOut(
        scan=scan_out(scan),
        title=title,
        filters=res.filters,
        prefilters=res.prefilters,
        counts=res.counts,
        candidates=[
            CandidateOut(
                rank=c.rank,
                ticker=c.row.ticker,
                symbol=c.row.symbol,
                label=c.row.label,
                sector=c.row.sector,
                held=c.row.held,
                watched=c.row.ticker in watched,
                signal=c.row.signal,
                signal_label=c.row.signal_label or "",
                rule=c.row.rule or "",
                confidence=c.row.confidence,
                composite=c.row.composite,
                technical=c.row.technical,
                fundamental=c.row.fundamental,
                bullish=c.row.bullish,
                bearish=c.row.bearish,
                flags=[FlagOut(**f) for f in c.row.flags],
                passed=c.passed,
                levels=(
                    EntryLevelsOut(
                        **{
                            **c.row.levels.__dict__,
                            "targets": [TargetOut(**t) for t in c.row.levels.targets],
                        }
                    )
                    if c.row.levels
                    else None
                ),
                impact=SectorImpactOut(**c.impact.__dict__),
                facts=c.row.facts,
                price_as_of=c.row.price_as_of,
            )
            for c in res.candidates
        ],
        near_misses=[
            NearMissOut(ticker=r.ticker, label=r.label, composite=r.composite, failed=failed)
            for r, failed in res.near_misses
        ],
        stale_note=stale,
        disclaimer=p.disclaimer,
    )


# ---------------------------------------------------------------------------- saved screens


@router.get("/screens", response_model=list[SavedScreenOut])
def list_screens(session: Session = Depends(get_session)) -> list[SavedScreenOut]:
    return [saved_out(s) for s in session.exec(select(SavedScreen).order_by(col(SavedScreen.name)))]


def _unique_name(session: Session, name: str, own_id: int | None = None) -> str:
    name = name.strip()
    other = session.exec(select(SavedScreen).where(SavedScreen.name == name)).first()
    if other and other.id != own_id:
        raise HTTPException(409, f"A screen called '{name}' already exists")
    if name in {v.label for v in get_profiles().screener.presets.values()}:
        raise HTTPException(409, f"'{name}' is a built-in preset name")
    return name


@router.post("/screens", response_model=SavedScreenOut, status_code=201)
def create_screen(body: SavedScreenIn, session: Session = Depends(get_session)) -> SavedScreenOut:
    validate_filters(body.filters)
    s = SavedScreen(
        name=_unique_name(session, body.name),
        filters_json=json.dumps([f.model_dump() for f in body.filters]),
    )
    session.add(s)
    session.commit()
    session.refresh(s)
    return saved_out(s)


@router.put("/screens/{screen_id}", response_model=SavedScreenOut)
def update_screen(
    screen_id: int, body: SavedScreenIn, session: Session = Depends(get_session)
) -> SavedScreenOut:
    s = session.get(SavedScreen, screen_id)
    if s is None:
        raise HTTPException(404, "No such saved screen")
    validate_filters(body.filters)
    s.name = _unique_name(session, body.name, screen_id)
    s.filters_json = json.dumps([f.model_dump() for f in body.filters])
    s.updated_at = utcnow()
    session.add(s)
    session.commit()
    session.refresh(s)
    return saved_out(s)


@router.delete("/screens/{screen_id}", status_code=204)
def delete_screen(screen_id: int, session: Session = Depends(get_session)) -> None:
    s = session.get(SavedScreen, screen_id)
    if s is None:
        raise HTTPException(404, "No such saved screen")
    session.delete(s)
    session.commit()


@router.get("/scans/{scan_id}/stocks", response_model=list[dict[str, object]])
def scan_stocks(
    scan_id: int,
    status: str | None = Query(None, description="scored | illiquid | no_prices | …"),
    session: Session = Depends(get_session),
) -> list[dict[str, object]]:
    """Every stock in a scan with its status (why it was or wasn't scored)."""
    scan = session.get(ScreenerScan, scan_id)
    if scan is None:
        raise HTTPException(404, "No such scan")
    rows = load_rows(scan)
    return [
        {"ticker": r.ticker, "label": r.label, "status": r.status, "status_text": r.status_text,
         "composite": r.composite, "signal": r.signal}
        for r in rows
        if status is None or r.status == status
    ]  # fmt: skip
