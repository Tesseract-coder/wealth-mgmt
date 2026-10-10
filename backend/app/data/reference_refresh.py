"""Download fresh NSE / AMFI reference lists, validate them, and swap them in atomically.

A download that fails to parse or is suspiciously small is rejected and the previous copy
(refreshed or bundled) stays in use.
"""

import gzip
import logging
from collections.abc import Callable, Sized
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta

from sqlmodel import Session

from app.core.formatting import IST, now_ist
from app.core.profiles import ReferenceKey, get_profiles
from app.core.settings import get_settings
from app.data import amfi, indices, nse, store
from app.data.files import REFERENCE_FILES, bundled_as_of, locate
from app.data.freshness import (
    Freshness,
    as_utc,
    assess_age,
    assess_series,
    expected_session,
    ready_at,
)
from app.data.http import FetchError, get_bytes
from app.data.store import RefreshResult
from app.importers import reference as resolvers

logger = logging.getLogger(__name__)

PARSERS: dict[ReferenceKey, Callable[[str], Sized]] = {
    "nse_equity": nse.parse_equity_list,
    "nse_etf": nse.parse_etf_list,
    "nifty50": indices.parse_index_list,
    "nifty100": indices.parse_index_list,
    "nifty200": indices.parse_index_list,
    "nifty500": indices.parse_index_list,
    "amfi_navall": amfi.parse_navall,
}


def ref_key(key: ReferenceKey) -> str:
    return f"ref:{key}"


def clear_reference_caches() -> None:
    nse.load_securities.cache_clear()
    amfi.load_schemes.cache_clear()
    indices.load_index.cache_clear()
    indices.nifty500_by_symbol.cache_clear()
    resolvers.ticker_resolver.cache_clear()
    resolvers.scheme_resolver.cache_clear()


def is_due(session: Session, key: ReferenceKey, now: datetime) -> bool:
    st = store.get_status(session, ref_key(key))
    if st is None or st.last_success_at is None:
        return True
    cfg = get_profiles().data
    ok_at = as_utc(st.last_success_at)
    if key == "amfi_navall":  # carries the latest NAVs, so it follows the NAV publishing cycle
        return ok_at < ready_at(expected_session(now, cfg.nav_ready), cfg.nav_ready)
    return now - ok_at > timedelta(days=cfg.reference_refresh_days)


def refresh_reference(
    session: Session, key: ReferenceKey, *, force: bool = False, now: datetime | None = None
) -> RefreshResult:
    now = now or now_ist()
    f = REFERENCE_FILES[key]
    st = store.status_row(session, ref_key(key), "reference", f.source, f.label)
    if not force and not is_due(session, key, now):
        return RefreshResult(st.key, f.label, "skipped", "Already up to date")
    st.last_attempt_at = store.to_utc(now)
    try:
        raw = get_bytes(f.source, f.url)
        text = raw.decode("utf-8-sig", errors="replace")
        try:
            n = len(PARSERS[key](text))
        except Exception as e:  # a parser blowing up on garbage is a bad download
            raise FetchError(f"{f.label}: download could not be parsed ({e})") from e
        minimum = get_profiles().data.reference_min_rows[key]
        if n < minimum:
            raise FetchError(
                f"{f.label}: download has only {n} rows (expected at least {minimum}); "
                "kept the old copy"
            )
    except FetchError as e:
        st.last_error = str(e)
        session.commit()
        return RefreshResult(st.key, f.label, "failed", str(e))

    out_dir = get_settings().reference_data_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / f.filename
    tmp = target.with_suffix(target.suffix + ".tmp")
    tmp.write_bytes(gzip.compress(raw) if f.gzipped else raw)
    tmp.replace(target)
    clear_reference_caches()
    st.rows, st.last_date = n, now.date()
    st.last_success_at, st.last_error = store.to_utc(now), None
    session.commit()
    logger.info("Refreshed %s: %d rows", key, n)
    return RefreshResult(st.key, f.label, "updated", f"{n} rows", n)


@dataclass(frozen=True)
class ReferenceStatus:
    key: str
    label: str
    source: str
    origin: str  # "refreshed" | "bundled"
    as_of: date | None
    rows: int | None
    freshness: Freshness


def reference_status(session: Session, now: datetime | None = None) -> list[ReferenceStatus]:
    now = now or now_ist()
    cfg = get_profiles().data
    out = []
    for key, f in REFERENCE_FILES.items():
        st = store.get_status(session, ref_key(key))
        path, origin = locate(key)
        max_age = (
            timedelta(hours=cfg.stale_after_hours)
            if key == "amfi_navall"
            else timedelta(days=cfg.reference_refresh_days)
        )
        when: datetime | None = st.last_success_at if st else None
        if origin == "refreshed" and when is None:
            when = datetime.fromtimestamp(path.stat().st_mtime, UTC)
        elif origin == "bundled":
            bundled = bundled_as_of(key)
            when = datetime.combine(bundled, time(), IST) if bundled else None
        fr = assess_age(
            last_success_at=when,
            last_error=st.last_error if st else None,
            now=now,
            max_age=max_age,
            what="bundled list" if origin == "bundled" else "list",
        )
        as_of = as_utc(when).astimezone(IST).date() if when else None
        rows = st.rows if st and origin == "refreshed" else None
        out.append(ReferenceStatus(key, f.label, f.source, origin, as_of, rows, fr))
    st = store.get_status(session, "ref:nse_delivery")
    fr = assess_series(
        last_date=st.last_date if st else None,
        last_success_at=st.last_success_at if st else None,
        last_error=st.last_error if st else None,
        now=now,
        ready=cfg.price_ready,
        stale_after_hours=cfg.stale_after_hours,
        max_missing=cfg.max_missing_sessions,
    )
    out.append(
        ReferenceStatus(
            "nse_delivery",
            "NSE delivery data (bhavcopy)",
            "nse",
            "refreshed",
            st.last_date if st else None,
            None,
            fr,
        )
    )
    return out
