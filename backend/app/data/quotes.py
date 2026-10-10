"""What to refresh (current holdings + benchmarks) and their latest prices / NAVs with freshness."""

from dataclasses import dataclass
from datetime import date, datetime
from typing import Literal

from sqlmodel import Session, col, select

from app.core.formatting import now_ist
from app.core.profiles import get_profiles
from app.data import store
from app.data.freshness import Freshness
from app.data.navs import latest_nav
from app.data.prices import daily_freshness, price_key
from app.data.yahoo import yahoo_ticker
from app.importers.snapshots import latest_snapshot
from app.models.tables import DailyBar, MFHolding, StockHolding


@dataclass(frozen=True)
class Target:
    kind: Literal["stock", "benchmark", "mf"]
    code: str  # Yahoo ticker for stocks/benchmarks, AMFI code for funds
    label: str


def stock_targets(session: Session) -> list[Target]:
    snap = latest_snapshot(session, "stocks")
    if snap is None:
        return []
    rows = session.exec(select(StockHolding).where(StockHolding.snapshot_id == snap.id)).all()
    seen: dict[str, Target] = {}
    for h in rows:
        if h.symbol:
            t = yahoo_ticker(h.symbol, h.exchange)
            seen.setdefault(t, Target("stock", t, h.name))
    return list(seen.values())


def benchmark_targets() -> list[Target]:
    return [
        Target("benchmark", ticker, name.replace("nifty", "Nifty "))
        for name, ticker in get_profiles().data.benchmarks.items()
    ]


def fund_targets(session: Session) -> list[Target]:
    snap = latest_snapshot(session, "mf")
    if snap is None:
        return []
    rows = session.exec(select(MFHolding).where(MFHolding.snapshot_id == snap.id)).all()
    seen: dict[str, Target] = {}
    for h in rows:
        if h.amfi_code:
            seen.setdefault(h.amfi_code, Target("mf", h.amfi_code, h.scheme_name))
    return list(seen.values())


@dataclass(frozen=True)
class Quote:
    kind: Literal["stock", "benchmark", "mf"]
    code: str
    label: str
    price: float | None
    previous: float | None
    as_of: date | None
    source: str | None
    freshness: Freshness

    @property
    def change_pct(self) -> float | None:
        if self.price is None or not self.previous:
            return None
        return round((self.price / self.previous - 1) * 100, 2)


def _price_quote(session: Session, t: Target, now: datetime) -> Quote:
    bars = session.exec(
        select(DailyBar)
        .where(DailyBar.ticker == t.code)
        .order_by(col(DailyBar.date).desc())
        .limit(2)
    ).all()
    st = store.get_status(session, price_key(t.code))
    fr = daily_freshness(st, now)
    if not bars:
        return Quote(t.kind, t.code, t.label, None, None, None, None, fr)
    prev = bars[1].close if len(bars) > 1 else None
    return Quote(t.kind, t.code, t.label, bars[0].close, prev, bars[0].date, "yahoo", fr)


def quotes(session: Session, now: datetime | None = None) -> list[Quote]:
    now = now or now_ist()
    out = [_price_quote(session, t, now) for t in benchmark_targets() + stock_targets(session)]
    for t in fund_targets(session):
        n = latest_nav(session, t.code, now)
        out.append(
            Quote("mf", t.code, t.label, n.nav, n.previous_nav, n.nav_date, n.source, n.freshness)
        )
    return out
