"""The All stocks directory: every NSE and BSE-only share, with what is already cached about it.

Nothing is downloaded here. A stock's data loads the first time you open it (or when a scan
or the nightly top-up reaches it); until then it is listed as not loaded yet.
"""

import json
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import text
from sqlmodel import Session, select

from app.core.db import get_session
from app.core.memo import Memo
from app.data.indices import INDEX_KEYS, IndexKey
from app.data.market import all_listings
from app.data.quotes import stock_targets
from app.data.sectors import nse_sector
from app.models.tables import FundamentalsRaw, WatchItem

router = APIRouter(prefix="/stocks", tags=["stocks"])


class StockRowOut(BaseModel):
    ticker: str
    symbol: str
    name: str
    exchange: Literal["NSE", "BSE"]
    index: IndexKey | None
    sector: str | None
    mcap_cr: float | None
    close: float | None
    as_of: date | None
    loaded: bool  # prices downloaded
    held: bool
    watched: bool


class CountOut(BaseModel):
    name: str
    count: int


class StocksOut(BaseModel):
    total: int  # matching the filters
    all: int  # every listed stock
    loaded: int
    rows: list[StockRowOut]
    sectors: list[CountOut]  # among the stocks matching everything but the sector filter


@dataclass(frozen=True)
class _Row:
    out: StockRowOut
    haystack: str  # lower-case symbol and name, for search


def _text(info: dict[str, object], key: str) -> str | None:
    v = info.get(key)
    return v if isinstance(v, str) else None


def _directory(session: Session) -> list[_Row]:
    infos: dict[str, dict[str, object]] = {}
    for ticker, raw in session.exec(select(FundamentalsRaw.ticker, FundamentalsRaw.info_json)):
        try:
            infos[ticker] = json.loads(raw)
        except ValueError:
            continue
    # The last stored close of every downloaded series, in one query.
    closes = {
        t: (c, d)
        for t, d, c in session.exec(  # type: ignore[call-overload]
            text(
                "SELECT d.ticker, d.date, d.close FROM dailybar d JOIN seriesstatus s "
                "ON s.key = 'price:' || d.ticker AND d.date = s.last_date"
            )
        )
    }
    held = {t.code for t in stock_targets(session)}
    watched = set(session.exec(select(WatchItem.ticker)))
    out = []
    for x in all_listings():
        info = infos.get(x.ticker, {})
        sector = x.industry or nse_sector(_text(info, "sector"), _text(info, "industry"))
        mcap = info.get("marketCap")
        close, as_of = closes.get(x.ticker, (None, None))
        row = StockRowOut(
            ticker=x.ticker,
            symbol=x.symbol,
            name=x.name,
            exchange="BSE" if x.exchange == "BSE" else "NSE",
            index=x.index,
            sector=sector,
            mcap_cr=round(mcap / 1e7, 1) if isinstance(mcap, int | float) and mcap > 0 else None,
            close=None if close is None else round(float(close), 2),
            as_of=date.fromisoformat(str(as_of)[:10]) if as_of else None,
            loaded=close is not None,
            held=x.ticker in held,
            watched=x.ticker in watched,
        )
        out.append(_Row(row, f"{x.symbol} {x.name}".lower()))
    return out


# Built once and reused until any data changes (a download, an import, the watchlist).
_rows: Memo[list[_Row]] = Memo("stock directory", timedelta(minutes=10), size=2)

IndexFilter = Literal["nifty50", "nifty100", "nifty200", "nifty500", "outside"]


def _in_index(row: StockRowOut, want: IndexFilter) -> bool:
    if want == "outside":
        return row.index is None
    return row.index is not None and INDEX_KEYS.index(row.index) <= INDEX_KEYS.index(want)


@router.get("", response_model=StocksOut)
def list_stocks(
    q: str = Query("", description="Symbol or company name"),
    exchange: Literal["all", "NSE", "BSE"] = Query("all", description="BSE = listed only on BSE"),
    index: IndexFilter | None = Query(None, description="Members of a Nifty index, or outside"),
    sector: str | None = None,
    loaded: bool = Query(False, description="Only stocks whose data is downloaded"),
    held: bool = Query(False, description="Only your holdings"),
    sort: Literal["name", "mcap"] = "name",
    offset: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    session: Session = Depends(get_session),
) -> StocksOut:
    """Every NSE stock and every share listed only on BSE, from cached data only."""
    rows = _rows.get(session, "all", _directory)
    needle = q.strip().lower()
    base = [
        r.out
        for r in rows
        if (not needle or needle in r.haystack)
        and (exchange == "all" or r.out.exchange == exchange)
        and (index is None or _in_index(r.out, index))
        and (not loaded or r.out.loaded)
        and (not held or r.out.held)
    ]
    counts: dict[str, int] = {}
    for r in base:
        if r.sector:
            counts[r.sector] = counts.get(r.sector, 0) + 1
    match = [r for r in base if not sector or r.sector == sector]
    if sort == "mcap":
        match.sort(key=lambda r: (r.mcap_cr is None, -(r.mcap_cr or 0), r.name))
    else:
        match.sort(key=lambda r: r.name.lower())
    return StocksOut(
        total=len(match),
        all=len(rows),
        loaded=sum(r.out.loaded for r in rows),
        rows=match[offset : offset + limit],
        sectors=[CountOut(name=k, count=v) for k, v in sorted(counts.items(), key=lambda x: -x[1])],
    )
