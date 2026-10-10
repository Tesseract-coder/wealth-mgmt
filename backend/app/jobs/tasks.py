"""Refresh jobs. Market data: reference lists → prices → delivery → NAVs → holdings' fundamentals
→ today's signals (saved to the signal history). Watchlist stocks are refreshed and recorded
alongside your holdings.
Fundamentals (weekly): holdings plus Nifty 500 peers in the same NSE industry, for medians.

Each step skips anything that is already fresh unless `force` is set, so the job is cheap to
run often. A failure on one item is recorded and the job moves on; old data is kept.
"""

from collections.abc import Callable
from functools import partial
from typing import Literal, get_args

from sqlmodel import Session, select

from app.core.db import get_engine
from app.core.profiles import ReferenceKey
from app.data.delivery import refresh_delivery
from app.data.files import REFERENCE_FILES
from app.data.fundamentals import refresh_fundamentals
from app.data.navs import refresh_nav
from app.data.prices import refresh_daily
from app.data.quotes import Target, benchmark_targets, fund_targets, stock_targets
from app.data.reference_refresh import refresh_reference
from app.data.store import RefreshResult
from app.jobs.runner import JobFn, Progress

Scope = Literal["all", "reference", "prices", "navs"]
SCOPES: tuple[Scope, ...] = get_args(Scope)
JOB_KIND = "market_refresh"


def market_refresh(scope: Scope = "all", force: bool = False, sheets: bool = False) -> JobFn:
    """`sheets`: end with a Google Sheets export when auto-export is on (the scheduled run)."""

    def run(progress: Progress) -> str:
        with Session(get_engine()) as s:
            steps: list[tuple[str, Callable[[], RefreshResult]]] = []
            # The AMFI list carries the day's NAVs, so the NAV refresh updates it too.
            ref_keys: list[ReferenceKey] = []
            if scope in ("all", "reference"):
                ref_keys = list(REFERENCE_FILES)
            elif scope == "navs":
                ref_keys = ["amfi_navall"]
            for key in ref_keys:
                steps.append(
                    (REFERENCE_FILES[key].label, partial(refresh_reference, s, key, force=force))
                )
            twins, fund_benches = _mf_extras(s) if scope in ("all", "prices", "navs") else ([], [])
            stocks = _stocks_and_watchlist(s)
            if scope in ("all", "prices"):
                for t in benchmark_targets() + stocks:
                    steps.append((t.label, partial(refresh_daily, s, t.code, t.label, force=force)))
                known = {t.code for t in benchmark_targets() + stocks}
                for ticker, label in fund_benches:
                    if ticker not in known:
                        steps.append((label, partial(refresh_daily, s, ticker, label, force=force)))
            if scope in ("all", "prices"):
                steps.append(("NSE delivery data", partial(refresh_delivery, s, force=force)))
            if scope in ("all", "navs"):
                for t in fund_targets(s):
                    steps.append((t.label, partial(refresh_nav, s, t.code, t.label, force=force)))
                for code, label in twins:  # Direct plans of your Regular funds, for the cost gap
                    steps.append((label, partial(refresh_nav, s, code, label, force=force)))

            if scope == "all":
                for t in stocks:
                    steps.append(
                        (
                            f"fundamentals {t.label}",
                            partial(fundamentals_step, s, t.code, t.label, force),
                        )
                    )
            if scope in ("all", "prices") and stocks:
                steps.append(("signal history", partial(signals_step, s)))
            if sheets:
                steps.append(("Google Sheets export", partial(sheets_step, s)))
            return _run_steps(s, steps, progress)

    return run


def _stocks_and_watchlist(s: Session) -> list[Target]:
    from app.screener.watchlist import watch_targets

    out = {t.code: t for t in stock_targets(s)}
    for t in watch_targets(s):
        out.setdefault(t.code, t)
    return list(out.values())


def _mf_extras(s: Session) -> tuple[list[tuple[str, str]], list[tuple[str, str]]]:
    from app.analysis.mf import mf_refresh_targets

    return mf_refresh_targets(s)


def _run_steps(
    s: Session, steps: list[tuple[str, Callable[[], RefreshResult]]], progress: Progress
) -> str:
    counts = {"updated": 0, "skipped": 0, "failed": 0}
    total = len(steps)
    progress.update(0, total, "Starting")
    for i, (label, step) in enumerate(steps):
        progress.update(i, total, f"Refreshing {label}")
        try:
            result = step()
            # Never leave a transaction open between steps: progress updates use their
            # own connection, and SQLite allows one writer at a time.
            s.commit()
        except Exception as e:  # unexpected bug: record it, keep going
            s.rollback()
            result = RefreshResult("?", label, "failed", f"{e.__class__.__name__}: {e}")
        counts[result.outcome] += 1
        if result.outcome == "failed":
            progress.error(f"{label}: {result.message}")
    progress.update(total, total)
    return (
        f"{counts['updated']} updated, {counts['skipped']} already fresh, {counts['failed']} failed"
    )


def sheets_step(session: Session) -> RefreshResult:
    from app.sheets.sync import sheets_refresh_step

    outcome, message = sheets_refresh_step(session)
    return RefreshResult("gsheet", "Google Sheets export", outcome, message)  # type: ignore[arg-type]


FUND_JOB_KIND = "fundamentals_refresh"


def signals_step(session: Session) -> RefreshResult:
    """Today's signals for your holdings and watchlist (holdings only if no stocks are held)."""
    from app.analysis.signals import record_holdings_step
    from app.data.provider import CachedProvider
    from app.screener.watchlist import record_watchlist

    res = record_holdings_step(session) if stock_targets(session) else None
    n = record_watchlist(session, CachedProvider(session))
    msg = (
        "; ".join(x for x in (res.message if res else "", f"{n} watchlist" if n else "") if x)
        or "nothing to record"
    )
    return RefreshResult("signals", "Signal history", "updated", msg)


def fundamentals_step(
    session: Session, ticker: str, label: str | None, force: bool = False
) -> RefreshResult:
    """Refresh one stock's Yahoo fundamentals, then recompute its stored metrics for medians."""
    from app.analysis.fundamental import analyse_fundamentals
    from app.data.provider import CachedProvider

    res = refresh_fundamentals(session, ticker, label, force=force)
    if res.outcome != "failed":
        analyse_fundamentals(session, CachedProvider(session), ticker, label=label, fetch=False)
    return res


def peer_targets(session: Session, holdings: list[tuple[str, str]], max_peers: int) -> list[str]:
    """Nifty 500 stocks sharing an NSE industry with a holding: already-cached peers first."""
    from app.data.indices import load_nifty500, nifty500_by_symbol
    from app.models.tables import FundamentalsRaw

    held = {t for t, _ in holdings}
    by_sym = nifty500_by_symbol()
    industries = {
        by_sym[t.removesuffix(".NS")].industry
        for t, _ in holdings
        if t.removesuffix(".NS") in by_sym
    }
    cached = {r.ticker for r in session.exec(select(FundamentalsRaw))}
    out: list[str] = []
    for ind in sorted(industries):
        peers = [f"{c.symbol}.NS" for c in load_nifty500() if c.industry == ind]
        peers = [p for p in peers if p not in held]
        peers.sort(key=lambda p: (p not in cached, p))
        out.extend(peers[:max_peers])
    return out


def fundamentals_refresh(force: bool = False, peers: bool = True) -> JobFn:
    def run(progress: Progress) -> str:
        from app.core.profiles import get_profiles

        with Session(get_engine()) as s:
            holdings = [(t.code, t.label) for t in _stocks_and_watchlist(s)]
            steps: list[tuple[str, Callable[[], RefreshResult]]] = [
                (label, partial(fundamentals_step, s, code, label, force))
                for code, label in holdings
            ]
            if peers:
                max_peers = get_profiles().fundamental.sector_max_peers
                for code in peer_targets(s, holdings, max_peers):
                    steps.append((f"peer {code}", partial(fundamentals_step, s, code, None, force)))
            return _run_steps(s, steps, progress)

    return run
