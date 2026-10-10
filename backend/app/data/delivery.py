"""Delivery % from NSE's daily full bhavcopy (one CSV per session covering every stock).

https://nsearchives.nseindia.com/products/content/sec_bhavdata_full_DDMMYYYY.csv
Only EQ-series rows are kept: BE/BZ series are trade-for-trade (100% delivery by rule), so
their delivery % says nothing about conviction.
"""

import csv
import io
import logging
from datetime import date, datetime, timedelta

import pandas as pd
from sqlalchemy import func
from sqlalchemy import select as sa_select
from sqlmodel import Session, col, select

from app.core.formatting import now_ist
from app.core.profiles import get_profiles
from app.data import store
from app.data.freshness import expected_session
from app.data.http import FetchError, get_bytes
from app.data.store import RefreshResult
from app.models.tables import BhavcopyDay, DeliveryStat

logger = logging.getLogger(__name__)

URL = "https://nsearchives.nseindia.com/products/content/sec_bhavdata_full_{d:%d%m%Y}.csv"
STATUS_KEY = "ref:nse_delivery"


def _num(s: str | None) -> float | None:
    s = (s or "").strip().replace(",", "")
    if s in ("", "-"):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def parse_bhavcopy(text: str, day: date) -> list[dict[str, object]]:
    rows = []
    reader = csv.DictReader(io.StringIO(text.lstrip("﻿")))
    for raw in reader:
        r = {(k or "").strip(): (v or "").strip() for k, v in raw.items()}
        if r.get("SERIES") != "EQ" or not r.get("SYMBOL"):
            continue
        rows.append(
            {
                "symbol": r["SYMBOL"],
                "date": day,
                "close": _num(r.get("CLOSE_PRICE")),
                "traded_qty": _num(r.get("TTL_TRD_QNTY")),
                "turnover_lacs": _num(r.get("TURNOVER_LACS")),
                "deliv_qty": _num(r.get("DELIV_QTY")),
                "deliv_pct": _num(r.get("DELIV_PER")),
            }
        )
    return rows


def wanted_sessions(now: datetime, n: int) -> list[date]:
    """The last n weekdays up to the latest completed session, newest first."""
    d = expected_session(now, get_profiles().data.price_ready)
    out: list[date] = []
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d)
        d -= timedelta(days=1)
    return out


def refresh_delivery(
    session: Session, *, force: bool = False, now: datetime | None = None
) -> RefreshResult:
    """Fetch bhavcopies for recent sessions we don't have yet (holidays are remembered)."""
    now = now or now_ist()
    n = get_profiles().technical.delivery_lookback_sessions
    wanted = wanted_sessions(now, n)
    have = {
        d.date: d.status
        for d in session.exec(select(BhavcopyDay).where(col(BhavcopyDay.date).in_(wanted)))
    }
    todo = [d for d in wanted if force or d not in have]
    st = store.status_row(session, STATUS_KEY, "reference", "nse", "NSE delivery data")
    if not todo:
        return RefreshResult(STATUS_KEY, st.label or "", "skipped", "Already up to date")
    st.last_attempt_at = store.to_utc(now)
    fetched, missing, errors = 0, 0, []
    for d in todo:
        try:
            text = get_bytes("nse", URL.format(d=d)).decode("utf-8", errors="replace")
        except FetchError as e:
            if "HTTP 404" in str(e):  # no file for that weekday: an exchange holiday
                session.merge(BhavcopyDay(date=d, status="missing"))
                missing += 1
            else:
                errors.append(f"{d:%d %b %Y}: {e}")
            continue
        rows = parse_bhavcopy(text, d)
        if not rows:
            errors.append(f"{d:%d %b %Y}: bhavcopy had no EQ rows")
            continue
        store._upsert(session, DeliveryStat, rows, ["symbol", "date"])
        session.merge(BhavcopyDay(date=d, status="ok", rows=len(rows)))
        fetched += 1
        session.commit()
    latest = session.execute(
        sa_select(func.max(BhavcopyDay.date)).where(col(BhavcopyDay.status) == "ok")
    ).scalar()
    st.last_date = latest
    st.rows = fetched
    if errors:
        st.last_error = "; ".join(errors[:3])
    else:
        st.last_success_at, st.last_error = store.to_utc(now), None
    session.commit()
    msg = f"{fetched} session(s) fetched, {missing} holiday(s)"
    if errors:
        return RefreshResult(STATUS_KEY, st.label or "", "failed", f"{msg}; {st.last_error}")
    return RefreshResult(STATUS_KEY, st.label or "", "updated", msg, fetched)


def delivery_history(session: Session, symbol: str, sessions: int) -> pd.DataFrame:
    """Most recent `sessions` rows for a symbol, oldest first (date index)."""
    rows = session.exec(
        select(DeliveryStat)
        .where(DeliveryStat.symbol == symbol)
        .order_by(col(DeliveryStat.date).desc())
        .limit(sessions)
    ).all()
    rows = list(reversed(rows))
    return pd.DataFrame(
        {
            "deliv_pct": [r.deliv_pct for r in rows],
            "turnover_lacs": [r.turnover_lacs for r in rows],
            "close": [r.close for r in rows],
        },
        index=pd.Index([r.date for r in rows], name="date"),
        dtype="float64",
    )
