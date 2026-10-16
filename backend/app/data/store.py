"""SQLite cache for price bars, NAVs and per-series freshness bookkeeping."""

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any, Literal

import pandas as pd
from sqlalchemy import delete, func
from sqlalchemy import select as sa_select
from sqlalchemy.dialects.sqlite import insert
from sqlmodel import Session, SQLModel, col, select

from app.models.tables import DailyBar, IntradayBar, NavPoint, SeriesStatus

_CHUNK = 500

Outcome = Literal["updated", "skipped", "failed"]


@dataclass(frozen=True)
class RefreshResult:
    key: str
    label: str
    outcome: Outcome
    message: str
    rows: int = 0


def _upsert(
    session: Session, model: type[SQLModel], rows: Sequence[dict[str, Any]], keys: list[str]
) -> None:
    table = model.__table__  # type: ignore[attr-defined]
    for i in range(0, len(rows), _CHUNK):
        chunk = rows[i : i + _CHUNK]
        stmt = insert(table).values(list(chunk))
        update = {c: stmt.excluded[c] for c in chunk[0] if c not in keys}
        session.execute(stmt.on_conflict_do_update(index_elements=keys, set_=update))


def _clean(v: Any) -> Any:
    return None if v is None or (isinstance(v, float) and pd.isna(v)) else float(v)


# --------------------------------------------------------------------------- daily bars


def upsert_daily(session: Session, ticker: str, df: pd.DataFrame) -> None:
    rows = [
        {
            "ticker": ticker,
            "date": d,
            **{c: _clean(r.get(c)) for c in ("open", "high", "low", "adj_close", "volume")},
            "close": float(r["close"]),
        }
        for d, r in zip(df.index, df.to_dict("records"), strict=True)
    ]
    if rows:
        _upsert(session, DailyBar, rows, ["ticker", "date"])


def read_daily(session: Session, ticker: str, start: date | None = None) -> pd.DataFrame:
    cols = ["open", "high", "low", "close", "adj_close", "volume"]
    # Plain column tuples, not ORM objects: building one object per bar was most of the cost.
    q = sa_select(col(DailyBar.date), *(col(getattr(DailyBar, c)) for c in cols)).where(
        col(DailyBar.ticker) == ticker
    )
    if start:
        q = q.where(col(DailyBar.date) >= start)
    rows = session.execute(q.order_by(col(DailyBar.date))).all()
    return pd.DataFrame(
        [r[1:] for r in rows],
        index=pd.Index([r[0] for r in rows], name="date"),
        columns=cols,
        dtype="float64",
    )


def delete_daily(session: Session, ticker: str) -> None:
    session.execute(delete(DailyBar).where(col(DailyBar.ticker) == ticker))


def daily_extent(session: Session, ticker: str) -> tuple[date | None, date | None, int]:
    first, last, n = session.execute(
        select(func.min(DailyBar.date), func.max(DailyBar.date), func.count()).where(
            DailyBar.ticker == ticker
        )
    ).one()
    return first, last, int(n)


# --------------------------------------------------------------------------- intraday bars


def replace_intraday(session: Session, ticker: str, interval: str, df: pd.DataFrame) -> None:
    session.execute(
        delete(IntradayBar).where(
            col(IntradayBar.ticker) == ticker, col(IntradayBar.interval) == interval
        )
    )
    rows = [
        {
            "ticker": ticker,
            "interval": interval,
            "ts": ts.to_pydatetime(),
            **{c: _clean(r.get(c)) for c in ("open", "high", "low", "volume")},
            "close": float(r["close"]),
        }
        for ts, r in zip(df.index, df.to_dict("records"), strict=True)
    ]
    if rows:
        _upsert(session, IntradayBar, rows, ["ticker", "interval", "ts"])


def read_intraday(session: Session, ticker: str, interval: str) -> pd.DataFrame:
    bars = session.exec(
        select(IntradayBar)
        .where(IntradayBar.ticker == ticker, IntradayBar.interval == interval)
        .order_by(col(IntradayBar.ts))
    ).all()
    cols = ["open", "high", "low", "close", "volume"]
    # SQLite returns naive datetimes; they were stored as UTC.
    index = pd.DatetimeIndex([b.ts for b in bars], name="ts")
    index = index.tz_localize("UTC") if index.tz is None else index.tz_convert("UTC")
    return pd.DataFrame(
        [[getattr(b, c) for c in cols] for b in bars],
        index=index,
        columns=cols,
        dtype="float64",
    )


# --------------------------------------------------------------------------- NAVs


def upsert_navs(session: Session, code: str, points: Iterable[tuple[date, float]]) -> None:
    rows = [{"amfi_code": code, "date": d, "nav": nav} for d, nav in points]
    if rows:
        _upsert(session, NavPoint, rows, ["amfi_code", "date"])


def read_navs(session: Session, code: str, start: date | None = None) -> list[NavPoint]:
    q = select(NavPoint).where(NavPoint.amfi_code == code)
    if start:
        q = q.where(NavPoint.date >= start)
    return list(session.exec(q.order_by(col(NavPoint.date))).all())


def nav_extent(session: Session, code: str) -> tuple[date | None, date | None, int]:
    first, last, n = session.execute(
        select(func.min(NavPoint.date), func.max(NavPoint.date), func.count()).where(
            NavPoint.amfi_code == code
        )
    ).one()
    return first, last, int(n)


# --------------------------------------------------------------------------- status rows


def get_status(session: Session, key: str) -> SeriesStatus | None:
    return session.get(SeriesStatus, key)


def status_row(
    session: Session, key: str, kind: str, source: str, label: str | None
) -> SeriesStatus:
    """Get or create a status row. label=None keeps the existing label (callers that only know
    the ticker shouldn't overwrite a holding's name)."""
    st = session.get(SeriesStatus, key)
    if st is None:
        st = SeriesStatus(key=key, kind=kind, source=source, label=label or key.split(":", 1)[-1])
        session.add(st)
    elif label is not None and st.label != label:
        st.label = label
    return st


def statuses(session: Session, kind: str) -> list[SeriesStatus]:
    return list(session.exec(select(SeriesStatus).where(SeriesStatus.kind == kind)).all())


def to_utc(now: datetime) -> datetime:
    return now.astimezone(UTC)
