"""Watchlist: stocks you track, scored live from cached data with what changed since you added them.

The daily price refresh downloads watchlist stocks along with your holdings, and their signals
go into the same signal history, so a change (e.g. Hold → Buy) shows with its date.
"""

from dataclasses import dataclass
from datetime import date

from sqlmodel import Session, col, select

from app.analysis.positions import Portfolio, load_portfolio
from app.analysis.signals import (
    SIGNAL_LABEL,
    StockSignal,
    active_profile,
    analyse_stock,
    record,
)
from app.core.profiles import RiskKey, StyleKey, get_profiles
from app.data.provider import DataProvider
from app.data.quotes import Target
from app.data.store import RefreshResult
from app.importers.reference import ticker_resolver
from app.jobs.runner import JobFn, Progress
from app.models.tables import SignalRecord, WatchItem

FETCH_JOB_KIND = "watchlist_fetch"


class WatchError(ValueError):
    pass


def normalise_ticker(raw: str) -> tuple[str, str]:
    """'tcs' / 'TCS.NS' → ('TCS.NS', company name). NSE equities only."""
    sym = raw.strip().upper().removesuffix(".NS")
    sec = ticker_resolver().by_symbol.get(sym)
    if sec is None:
        raise WatchError(f"'{raw}' is not on the NSE equity list")
    if sec.kind != "equity":
        raise WatchError(f"{sym} is an ETF; the watchlist tracks stocks")
    return f"{sym}.NS", sec.name


def items(session: Session) -> list[WatchItem]:
    return list(session.exec(select(WatchItem).order_by(col(WatchItem.added_at))).all())


def watch_targets(session: Session) -> list[Target]:
    return [Target("stock", w.ticker, w.label) for w in items(session)]


def baseline(w: WatchItem, s: StockSignal) -> None:
    """What the stock looked like when added (first time data is available)."""
    w.added_price = s.levels.close if s.levels else None
    w.added_signal = s.signal
    w.added_score = s.score.score
    w.added_style, w.added_risk = s.style, s.risk


def evaluate(
    session: Session,
    provider: DataProvider,
    ticker: str,
    label: str,
    style: StyleKey | None,
    risk: RiskKey,
    ctw: float,
    pf: Portfolio | None,
) -> StockSignal | None:
    if provider.daily(ticker).frame.empty:
        return None
    return analyse_stock(
        session,
        provider,
        ticker,
        style=style,
        risk_key=risk,
        custom_technical_weight=ctw,
        portfolio=pf,
        label=label,
        fetch=False,
    )


@dataclass
class SignalChange:
    previous: str
    current: str
    day: date


def last_change(session: Session, ticker: str, style: str, risk: str) -> SignalChange | None:
    """The most recent day the recorded signal changed, from the signal history."""
    rows = session.exec(
        select(SignalRecord)
        .where(
            SignalRecord.ticker == ticker,
            SignalRecord.style == style,
            SignalRecord.risk == risk,
        )
        .order_by(col(SignalRecord.day).desc())
        .limit(365)
    ).all()
    for newer, older in zip(rows, rows[1:], strict=False):
        if newer.signal != older.signal:
            return SignalChange(older.signal, newer.signal, newer.day)
    return None


@dataclass
class WatchView:
    item: WatchItem
    signal: StockSignal | None
    change: SignalChange | None
    held: bool


def view(session: Session, provider: DataProvider) -> list[WatchView]:
    style, risk, ctw = active_profile(session)
    ws = items(session)
    if not ws:
        return []
    pf = load_portfolio(session, provider, get_profiles().rebalance)
    out = []
    dirty = False
    for w in ws:
        sig = evaluate(session, provider, w.ticker, w.label, style, risk, ctw, pf)
        if sig is not None and w.added_signal is None:
            baseline(w, sig)
            session.add(w)
            dirty = True
        chg = last_change(session, w.ticker, sig.style, sig.risk) if sig else None
        out.append(WatchView(w, sig, chg, w.ticker in pf.positions))
    if dirty:
        session.commit()
    return out


def add(
    session: Session,
    provider: DataProvider,
    ticker: str,
    *,
    note: str | None = None,
    source: str | None = None,
) -> tuple[WatchItem, bool]:
    """(item, created). Adding a stock that is already watched updates nothing but the note."""
    t, name = normalise_ticker(ticker)
    w = session.get(WatchItem, t)
    if w is not None:
        if note:
            w.note = note
            session.add(w)
            session.commit()
        return w, False
    w = WatchItem(ticker=t, label=name, note=note or None, source=source or "Manual")
    style, risk, ctw = active_profile(session)
    # Same portfolio context as the watchlist view, so the baseline is comparable.
    pf = load_portfolio(session, provider, get_profiles().rebalance)
    sig = evaluate(session, provider, t, name, style, risk, ctw, pf)
    if sig is not None:
        baseline(w, sig)
    session.add(w)
    session.commit()
    session.refresh(w)
    return w, True


def record_watchlist(session: Session, provider: DataProvider) -> int:
    """Today's signals for watchlist stocks you don't hold (holdings are recorded already)."""
    style, risk, ctw = active_profile(session)
    pf = load_portfolio(session, provider, get_profiles().rebalance)
    n = 0
    for w in items(session):
        if w.ticker in pf.positions:
            continue
        sig = evaluate(session, provider, w.ticker, w.label, style, risk, ctw, pf)
        if sig is not None:
            record(session, sig)
            n += 1
    session.commit()
    return n


def fetch_job() -> JobFn:
    """Download prices and fundamentals for watchlist stocks that have none cached yet.
    Re-reads the list until nothing new is left, so stocks added mid-run are included."""
    from app.core.db import get_engine
    from app.data.provider import CachedProvider

    def run(progress: Progress) -> str:
        done: set[str] = set()
        results: list[RefreshResult] = []
        with Session(get_engine()) as s:
            provider = CachedProvider(s)
            while True:
                todo = [
                    w for w in items(s)
                    if w.ticker not in done and provider.daily(w.ticker).frame.empty
                ]  # fmt: skip
                if not todo or progress.stop_requested:
                    break
                start = len(done)
                for i, w in enumerate(todo):
                    done.add(w.ticker)
                    progress.update(start + i, start + len(todo), w.label)
                    for res in (
                        provider.ensure_daily(w.ticker, w.label),
                        provider.ensure_fundamentals(w.ticker, w.label),
                    ):
                        results.append(res)
                        if res.outcome == "failed":
                            progress.error(f"{w.label}: {res.message}")
                    s.commit()
        failed = sum(r.outcome == "failed" for r in results)
        return f"{len(done)} watchlist stock(s) downloaded" + (
            f", {failed} failed" if failed else ""
        )

    return run


def signal_text(key: str | None) -> str:
    return SIGNAL_LABEL.get(key or "", "—")
