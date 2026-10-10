"""Mutual fund NAVs: full history from mfapi.in, cross-checked with AMFI's daily NAVAll list."""

from dataclasses import dataclass
from datetime import date, datetime

from sqlmodel import Session

from app.core.formatting import now_ist
from app.core.profiles import get_profiles
from app.data import store
from app.data.freshness import Freshness, assess_series, missing_sessions
from app.data.http import FetchError
from app.data.mfapi import fetch_nav_history
from app.data.store import RefreshResult
from app.importers.reference import scheme_resolver
from app.models.tables import SeriesStatus


def nav_key(code: str) -> str:
    return f"nav:{code}"


def nav_freshness(last_date: date | None, st: SeriesStatus | None, now: datetime) -> Freshness:
    cfg = get_profiles().data
    return assess_series(
        last_date=last_date,
        last_success_at=st.last_success_at if st else None,
        last_error=st.last_error if st else None,
        now=now,
        ready=cfg.nav_ready,
        stale_after_hours=cfg.stale_after_hours,
        max_missing=cfg.max_missing_sessions,
    )


def refresh_nav(
    session: Session, code: str, label: str, *, force: bool = False, now: datetime | None = None
) -> RefreshResult:
    now = now or now_ist()
    key = nav_key(code)
    st = store.status_row(session, key, "nav", "mfapi", label)
    if not force and nav_freshness(st.last_date, st, now).status == "fresh":
        return RefreshResult(key, label, "skipped", "Already up to date")
    st.last_attempt_at = store.to_utc(now)
    try:
        history = fetch_nav_history(code)
    except FetchError as e:
        st.last_error = str(e)
        session.commit()
        return RefreshResult(key, label, "failed", str(e))
    store.upsert_navs(session, code, history.points)
    st.first_date, st.last_date, st.rows = store.nav_extent(session, code)
    st.last_success_at, st.last_error = store.to_utc(now), None
    session.commit()
    return RefreshResult(key, label, "updated", f"{len(history.points)} NAVs", len(history.points))


@dataclass(frozen=True)
class LatestNav:
    code: str
    nav: float | None
    nav_date: date | None
    previous_nav: float | None
    source: str | None  # "mfapi" | "amfi" | None
    freshness: Freshness


def latest_nav(session: Session, code: str, now: datetime | None = None) -> LatestNav:
    """Newest NAV from the mfapi history or the AMFI daily list, whichever is more recent."""
    now = now or now_ist()
    st = store.get_status(session, nav_key(code))
    points = store.read_navs(session, code)[-2:]
    nav, nav_d, prev, source = None, None, None, None
    if points:
        nav, nav_d, source = points[-1].nav, points[-1].date, "mfapi"
        prev = points[-2].nav if len(points) > 1 else None
    scheme = scheme_resolver().by_code.get(code)
    if scheme and scheme.nav and scheme.nav_date and (nav_d is None or scheme.nav_date > nav_d):
        # AMFI's list is newer. Our latest stored NAV is the "previous" one only if it's from the
        # session right before; otherwise a day-change figure would span several days.
        prev = nav if nav_d and missing_sessions(nav_d, scheme.nav_date) == 1 else None
        nav, nav_d, source = scheme.nav, scheme.nav_date, "amfi"
        ref = store.get_status(session, "ref:amfi_navall")
        return LatestNav(code, nav, nav_d, prev, source, nav_freshness(nav_d, ref, now))
    return LatestNav(code, nav, nav_d, prev, source, nav_freshness(nav_d, st, now))
