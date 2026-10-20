"""Screener scan: score every stock in a universe and store the result.

Two passes, so sector medians are complete before anything is scored:

1. **Data**: daily prices for each stock (cache first; downloads only what is missing or
   stale), the liquidity pre-filter (average close × volume), then fundamentals for the liquid
   ones, with their metrics stored for sector medians. Requests go through the per-source rate
   limiters, plus `screener.request_delay_seconds` after each stock that needed a download.
2. **Score**: the same engine as your holdings (`analyse_stock`, cached data only), with your
   style and risk, then the screen fields, entry zone, stop and targets.

Filtering is separate (`app.screener.screens`) and runs on the stored scan.
"""

import json
import logging
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from typing import Any, Literal

import pandas as pd
from sqlmodel import Session, col, select

from app.analysis.checks import evaluate_stock
from app.analysis.fundamental import analyse_fundamentals
from app.analysis.positions import Portfolio, load_portfolio
from app.analysis.signals import SIGNAL_LABEL, StockSignal, analyse_stock
from app.analysis.technical import analyse_frame
from app.core.formatting import format_inr
from app.core.profiles import (
    Profiles,
    RiskKey,
    ScreenerConfig,
    StyleKey,
    UniverseKey,
    get_profiles,
)
from app.data.indices import INDEX_LABELS, IndexKey, load_index
from app.data.market import MARKET_LABELS, market_listings
from app.data.provider import CachedProvider, DataProvider
from app.importers.reference import ticker_resolver
from app.jobs.runner import JobFn, Progress
from app.models.tables import ScreenerScan, utcnow

logger = logging.getLogger(__name__)

JOB_KIND = "screener"
FetchMode = Literal["missing", "cached"]
RowStatus = Literal["scored", "no_prices", "short_history", "illiquid", "error"]
STATUS_TEXT: dict[str, str] = {
    "no_prices": "No price history",
    "short_history": "Too little price history (recent listing)",
    "illiquid": "Below the liquidity minimum",
    "error": "Could not be analysed",
}


@dataclass(frozen=True)
class Member:
    ticker: str
    symbol: str
    name: str
    industry: str | None


@dataclass
class Levels:
    interval: str
    close: float
    atr: float
    entry_low: float
    entry_high: float
    entry_basis: str
    stop: float
    stop_pct: float
    targets: list[dict[str, Any]]
    basis: str


@dataclass
class ScanRow:
    ticker: str
    symbol: str
    label: str
    sector: str | None
    status: RowStatus
    status_text: str | None = None
    held: bool = False
    is_financial: bool = False
    facts: dict[str, float | None] = field(default_factory=dict)
    signal: str | None = None
    signal_label: str | None = None
    rule: str | None = None
    confidence: str | None = None
    composite: float | None = None
    technical: float | None = None
    fundamental: float | None = None
    bullish: list[str] = field(default_factory=list)
    bearish: list[str] = field(default_factory=list)
    flags: list[dict[str, Any]] = field(default_factory=list)
    levels: Levels | None = None
    price_as_of: str | None = None
    notes: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------- universes


def universe_label(key: UniverseKey, n: int | None = None) -> str:
    if key == "custom":
        return f"Custom list ({n} stocks)" if n is not None else "Custom list"
    if key in MARKET_LABELS:
        return MARKET_LABELS[key]
    return INDEX_LABELS[key]  # type: ignore[index]


def index_members(key: IndexKey) -> list[Member]:
    return [Member(f"{c.symbol}.NS", c.symbol, c.name, c.industry or None) for c in load_index(key)]


def parse_symbols(text: str | list[str]) -> list[str]:
    """'TCS, infy.ns\nHDFCBANK, andhrapet.bo' → ['TCS', 'INFY', 'HDFCBANK', 'ANDHRAPET.BO']
    (order kept, duplicates dropped)."""
    parts = text if isinstance(text, list) else text.replace(",", "\n").replace(" ", "\n").split()
    out: list[str] = []
    for p in parts:
        s = p.strip().upper().removesuffix(".NS")
        if s and s not in out:
            out.append(s)
    return out


def custom_members(symbols: list[str]) -> tuple[list[Member], list[str]]:
    """Members for NSE symbols (or BSE ones ending .BO); unknown symbols (and ETFs) are
    returned separately."""
    r = ticker_resolver()
    industry = {c.symbol: c.industry for c in load_index("nifty500")}
    out, unknown = [], []
    for s in symbols:
        sec = r.lookup(s) or r.bse_by_symbol.get(s)
        if sec is None or sec.kind != "equity":
            unknown.append(s)
        else:
            nse = sec.exchange == "NSE"
            out.append(Member(sec.ticker, sec.symbol, sec.name, industry.get(s) if nse else None))
    return out, unknown


def members_for(
    key: UniverseKey, symbols: list[str] | None = None
) -> tuple[list[Member], list[str]]:
    if key == "custom":
        return custom_members(symbols or [])
    if key in MARKET_LABELS:
        listings = market_listings(key)
        return [Member(x.ticker, x.symbol, x.name, x.industry) for x in listings], []
    return index_members(key), []  # type: ignore[arg-type]


# ---------------------------------------------------------------------------- facts


def avg_traded_value_cr(df: pd.DataFrame, sessions: int) -> float | None:
    """Average daily close × volume over the last `sessions` bars, in ₹ crore."""
    if df.empty or "volume" not in df:
        return None
    tv = (df["close"] * df["volume"]).dropna().iloc[-sessions:]
    if tv.empty:
        return None
    return round(float(tv.mean()) / 1e7, 2)


def _pct(a: float | None, b: float | None) -> float | None:
    if a is None or b is None or b == 0:
        return None
    return round((a / b - 1) * 100, 2)


def facts_for(sig: StockSignal, daily: pd.DataFrame, p: Profiles) -> dict[str, float | None]:
    """The screen fields for one scored stock. Technical fields come from daily bars."""
    per = p.technical.periods
    frame = next((t for t in sig.technical.timeframes if t.interval == "1d"), None)
    v = (
        frame.analysis.values
        if frame
        else analyse_frame(daily, "1d", p.technical, is_index=False).values
    )
    ctx = sig.technical.context.values
    m = sig.fundamental.metrics

    def mv(k: str) -> float | None:
        x = m.get(k)
        return None if x is None or x.value is None else float(x.value)

    pe = m.get("pe")
    pe_vs = (
        round(pe.value / pe.sector_median, 2)
        if pe and pe.value is not None and pe.sector_median
        else None
    )
    hv = v.get("hist_vol")
    close = v.get("close")
    sma50, sma200 = v.get("sma50"), v.get("sma200")
    fs = sig.fundamental.fscore
    out: dict[str, float | None] = {
        "close": None if close is None else round(close, 2),
        "price_vs_sma50_pct": _pct(close, sma50),
        "price_vs_sma200_pct": _pct(close, sma200),
        "sma50_vs_sma200_pct": _pct(sma50, sma200),
        "rsi": v.get(f"rsi{per.rsi}"),
        "adx": v.get("adx"),
        "roc": v.get(f"roc{per.roc}"),
        "volume_ratio": v.get("volume_ratio"),
        "pct_below_52w_high": ctx.get("pct_below_52w_high"),
        "pct_above_52w_low": ctx.get("pct_above_52w_low"),
        "rs_3m": ctx.get("rs_3m"),
        "rs_6m": ctx.get("rs_6m"),
        "hist_vol": None if hv is None else round(hv * 100, 2),
        "delivery_pct": ctx.get("delivery_pct"),
        "avg_traded_value_cr": avg_traded_value_cr(daily, p.screener.traded_value_sessions),
        "beta": sig.beta,
        "pe_vs_sector": pe_vs,
        "fscore": None if fs is None or fs.score is None else float(fs.score),
        "composite": sig.score.score,
        "technical_score": sig.score.technical.score,
        "fundamental_score": sig.score.fundamental.score,
    }
    for k in (
        "market_cap", "pe", "pb", "ev_ebitda", "peg", "dividend_yield", "roe", "roce",
        "op_margin", "op_margin_change", "net_margin", "net_margin_change", "revenue_cagr_3y",
        "profit_cagr_3y", "revenue_qoq_yoy", "profit_qoq_yoy", "debt_equity",
        "interest_coverage", "current_ratio", "fcf_positive_years",
    ):  # fmt: skip
        out[k] = mv(k)
    shape = evaluate_stock(sig, daily)
    for key, score in shape.axes.items():
        out[f"axis_{key}"] = None if score is None else float(score)
    out["axis_total"] = float(shape.total)
    # numpy floats from pandas would not survive json.dumps
    return {k: None if x is None or pd.isna(x) else round(float(x), 4) for k, x in out.items()}


def entry_levels(sig: StockSignal, cfg: ScreenerConfig) -> Levels | None:
    """Entry zone (close − k × ATR, or the nearest support if higher, up to the close), the
    stop for a new purchase (close − your ATR multiple × ATR) and the targets."""
    lv = sig.levels
    if lv is None:
        return None
    rep = next((t for t in sig.technical.timeframes if t.interval == lv.interval), None)
    support = rep.analysis.values.get("support") if rep else None
    low = lv.close - cfg.entry_zone_atr * lv.atr
    basis = f"close − {cfg.entry_zone_atr:g} × ATR ({format_inr(lv.atr)})"
    if support is not None and low < support < lv.close:
        low, basis = support, f"nearest support {format_inr(support)}"
    return Levels(
        interval=lv.interval,
        close=lv.close,
        atr=lv.atr,
        entry_low=round(low, 2),
        entry_high=lv.close,
        entry_basis=f"Entry zone from {basis} up to the last close {format_inr(lv.close)}.",
        stop=lv.entry_stop,
        stop_pct=round((lv.entry_stop / lv.close - 1) * 100, 2),
        targets=[{"label": t.label, "price": t.price, "pct": round(t.pct, 2)} for t in lv.targets],
        basis=lv.basis,
    )


def scored_row(m: Member, sig: StockSignal, daily: pd.DataFrame, p: Profiles) -> ScanRow:
    return ScanRow(
        ticker=m.ticker,
        symbol=m.symbol,
        label=m.name or sig.label,
        sector=sig.sector or m.industry,
        status="scored",
        held=sig.position is not None,
        is_financial=sig.fundamental.is_financial,
        facts=facts_for(sig, daily, p),
        signal=sig.signal,
        signal_label=SIGNAL_LABEL[sig.signal],
        rule=sig.rule,
        confidence=sig.score.confidence,
        composite=sig.score.score,
        technical=sig.score.technical.score,
        fundamental=sig.score.fundamental.score,
        bullish=[r.text for r in sig.bullish],
        bearish=[r.text for r in sig.bearish],
        flags=[{"key": f.key, "severe": f.severe, "text": f.text} for f in sig.flags],
        levels=entry_levels(sig, p.screener),
        price_as_of=sig.levels.as_of[:10] if sig.levels else None,
        notes=sig.fundamental.notes[:3] if sig.fundamental.source is None else [],
    )


# ---------------------------------------------------------------------------- passes


def fetch_data(
    session: Session,
    provider: DataProvider,
    m: Member,
    mode: FetchMode,
    cfg: ScreenerConfig,
    *,
    min_value_cr: float,
) -> tuple[RowStatus | None, bool, list[str]]:
    """Pass 1 for one stock: (status if it can't be scored, whether it downloaded, errors)."""
    downloaded = False
    errors: list[str] = []
    if mode == "missing":
        res = provider.ensure_daily(m.ticker, m.name)
        downloaded |= res.outcome != "skipped"
        if res.outcome == "failed":
            errors.append(f"{m.symbol} prices: {res.message}")
    df = provider.daily(m.ticker).frame
    if df.empty:
        return "no_prices", downloaded, errors
    if len(df) < cfg.min_history_sessions:
        return "short_history", downloaded, errors
    atv = avg_traded_value_cr(df, cfg.traded_value_sessions)
    if atv is None or atv < min_value_cr:
        return "illiquid", downloaded, errors
    if mode == "missing":
        res = provider.ensure_fundamentals(m.ticker, m.name)
        downloaded |= res.outcome != "skipped"
        if res.outcome == "failed":
            errors.append(f"{m.symbol} fundamentals: {res.message}")
        elif res.outcome == "updated":  # store its metrics so peers' sector medians include it
            analyse_fundamentals(session, provider, m.ticker, label=m.name, fetch=False)
    session.commit()
    return None, downloaded, errors


def unscored_row(m: Member, status: RowStatus, df: pd.DataFrame, cfg: ScreenerConfig) -> ScanRow:
    text = STATUS_TEXT[status]
    atv = avg_traded_value_cr(df, cfg.traded_value_sessions)
    if status == "illiquid":
        text += (
            f": {'no volume data' if atv is None else f'₹{atv:.1f} Cr'} a day"
            f" vs ₹{cfg.min_avg_daily_traded_value_cr:g} Cr"
        )
    elif status == "short_history":
        text += f": {len(df)} sessions, needs {cfg.min_history_sessions}"
    return ScanRow(
        ticker=m.ticker,
        symbol=m.symbol,
        label=m.name,
        sector=m.industry,
        status=status,
        status_text=text,
        facts={"avg_traded_value_cr": atv},
    )


@dataclass
class ScanParams:
    universe: UniverseKey
    style: StyleKey
    risk: RiskKey
    custom_technical_weight: float
    fetch: FetchMode = "missing"
    symbols: list[str] = field(default_factory=list)


def run_scan(
    session: Session,
    provider: DataProvider,
    params: ScanParams,
    progress: Progress,
    scan: ScreenerScan,
    *,
    sleep: Callable[[float], None] = time.sleep,
) -> str:
    p = get_profiles()
    cfg = p.screener
    members, unknown = members_for(params.universe, params.symbols)
    notes = [f"Not on the NSE or BSE lists, skipped: {', '.join(unknown)}"] if unknown else []
    n = len(members)
    scan.total = n
    progress.update(0, 2 * n, "Starting")

    # Pass 1: data
    blocked: dict[str, RowStatus] = {}
    stopped_at: int | None = None
    for i, m in enumerate(members):
        if progress.stop_requested:
            stopped_at = i
            break
        progress.update(i, 2 * n, f"Data {i + 1}/{n}: {m.symbol}")
        try:
            status, downloaded, errors = fetch_data(
                session, provider, m, params.fetch, cfg,
                min_value_cr=cfg.min_avg_daily_traded_value_cr,
            )  # fmt: skip
        except Exception as e:  # one bad stock must not end the scan
            session.rollback()
            logger.exception("Screener: data step failed for %s", m.ticker)
            status, downloaded, errors = "error", False, [f"{m.symbol}: {e}"]
        for err in errors:
            progress.error(err)
        if status:
            blocked[m.ticker] = status
        if downloaded and cfg.request_delay_seconds:
            sleep(cfg.request_delay_seconds)
    todo = members if stopped_at is None else members[:stopped_at]

    # Pass 2: score (cache only, fast)
    pf: Portfolio = load_portfolio(session, provider, p.rebalance)
    rows: list[ScanRow] = []
    for j, m in enumerate(todo):
        if progress.stop_requested and stopped_at is None:
            stopped_at = j
            todo = todo[:j]
            break
        progress.update(n + j, 2 * n, f"Scoring {j + 1}/{len(todo)}: {m.symbol}")
        df = provider.daily(m.ticker).frame
        if m.ticker in blocked:
            rows.append(unscored_row(m, blocked[m.ticker], df, cfg))
            continue
        try:
            sig = analyse_stock(
                session, provider, m.ticker, style=params.style, risk_key=params.risk,
                custom_technical_weight=params.custom_technical_weight, portfolio=pf,
                label=m.name, fetch=False,
            )  # fmt: skip
            rows.append(scored_row(m, sig, df, p))
        except Exception as e:
            session.rollback()
            logger.exception("Screener: scoring failed for %s", m.ticker)
            progress.error(f"{m.symbol}: scoring failed ({e.__class__.__name__}: {e})")
            rows.append(unscored_row(m, "error", df, cfg))
        session.commit()  # analyse_fundamentals refreshes stored metrics

    scored = sum(r.status == "scored" for r in rows)
    if stopped_at is not None:
        notes.append(f"Stopped early: {len(rows)} of {n} stocks covered.")
    save_scan(session, scan, rows, notes, "partial" if stopped_at is not None else "complete")
    progress.update(2 * n, 2 * n)
    skipped = len(rows) - scored
    return f"{scored} of {n} stocks scored, {skipped} not scored" + (
        " (stopped early)" if stopped_at is not None else ""
    )


def save_scan(
    session: Session, scan: ScreenerScan, rows: list[ScanRow], notes: list[str], status: str
) -> None:
    scan.rows_json = json.dumps([asdict(r) for r in rows])
    scan.notes_json = json.dumps(notes)
    scan.scored = sum(r.status == "scored" for r in rows)
    scan.status, scan.finished_at = status, utcnow()
    session.add(scan)
    session.commit()
    prune_scans(session, get_profiles().screener.keep_scans)


def prune_scans(session: Session, keep: int) -> None:
    old = session.exec(
        select(ScreenerScan)
        .where(ScreenerScan.status != "running")
        .order_by(col(ScreenerScan.id).desc())
        .offset(keep)
    ).all()
    for s in old:
        session.delete(s)
    session.commit()


def load_rows(scan: ScreenerScan) -> list[ScanRow]:
    out = []
    for d in json.loads(scan.rows_json):
        lv = d.pop("levels", None)
        out.append(ScanRow(**d, levels=Levels(**lv) if lv else None))
    return out


def screener_job(params: ScanParams) -> JobFn:
    from app.core.db import get_engine

    def run(progress: Progress) -> str:
        with Session(get_engine()) as s:
            n = len(members_for(params.universe, params.symbols)[0])
            scan = ScreenerScan(
                job_id=progress.job_id,
                universe=params.universe,
                universe_label=universe_label(params.universe, n),
                style=params.style,
                risk=params.risk,
                fetch=params.fetch,
                total=n,
            )
            s.add(scan)
            s.commit()
            try:
                return run_scan(s, CachedProvider(s), params, progress, scan)
            except Exception:
                s.rollback()
                scan.status, scan.finished_at = "failed", utcnow()
                scan.notes_json = json.dumps(["The scan failed before finishing; see the job."])
                s.add(scan)
                s.commit()
                raise

    return run
