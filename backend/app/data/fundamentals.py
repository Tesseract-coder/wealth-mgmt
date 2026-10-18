"""Yahoo Finance fundamentals cache: fetch, store raw, track freshness."""

import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from sqlmodel import Session

from app.core.formatting import now_ist
from app.core.profiles import get_profiles
from app.data import store, yahoo
from app.data.freshness import Freshness, assess_age
from app.data.http import FetchError
from app.data.store import RefreshResult
from app.models.tables import FundamentalsRaw, SeriesStatus


def fund_key(ticker: str) -> str:
    return f"fund:{ticker}"


@dataclass(frozen=True)
class RawFundamentals:
    ticker: str
    fetched_at: datetime
    info: dict[str, Any]
    statements: dict[str, Any]


def fundamentals_freshness(st: SeriesStatus | None, now: datetime) -> Freshness:
    return assess_age(
        last_success_at=st.last_success_at if st else None,
        last_error=st.last_error if st else None,
        now=now,
        max_age=timedelta(days=get_profiles().data.fundamentals_stale_after_days),
        what="fundamentals",
    )


def refresh_fundamentals(
    session: Session,
    ticker: str,
    label: str | None = None,
    *,
    force: bool = False,
    now: datetime | None = None,
) -> RefreshResult:
    now = now or now_ist()
    key = fund_key(ticker)
    st = store.status_row(session, key, "fundamentals", "yahoo", label)
    label = st.label or ticker
    row = session.get(FundamentalsRaw, ticker)
    # Rows cached before analyst estimates were fetched lack the key; fetch those once more.
    has_estimates = row is not None and "eps_estimates" in json.loads(row.info_json)
    if not force and has_estimates and fundamentals_freshness(st, now).status == "fresh":
        return RefreshResult(key, label, "skipped", "Already up to date")
    st.last_attempt_at = store.to_utc(now)
    try:
        info, statements = yahoo.fetch_fundamentals(ticker)
    except FetchError as e:
        st.last_error = str(e)
        session.commit()
        return RefreshResult(key, label, "failed", str(e))
    row = row or FundamentalsRaw(ticker=ticker)
    row.fetched_at = store.to_utc(now)
    row.info_json = json.dumps(info)
    row.statements_json = json.dumps(statements)
    session.add(row)
    years = sorted({d for v in statements.get("income", {}).values() for d in v})
    st.rows = len(years)
    st.last_date = datetime.fromisoformat(years[-1]).date() if years else None
    st.last_success_at, st.last_error = store.to_utc(now), None
    session.commit()
    return RefreshResult(key, label, "updated", f"{len(years)} annual periods", len(years))


def load_raw(session: Session, ticker: str) -> RawFundamentals | None:
    row = session.get(FundamentalsRaw, ticker)
    if row is None:
        return None
    return RawFundamentals(
        ticker, row.fetched_at, json.loads(row.info_json), json.loads(row.statements_json)
    )
