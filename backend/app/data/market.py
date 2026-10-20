"""Every listed share: NSE's equities plus the shares listed only on BSE.

Used by the screener's whole-market universes and the All stocks page. ETFs are left out (the
screener and the directory are about companies).
"""

from dataclasses import dataclass
from functools import lru_cache
from typing import Literal

from app.data.bse import bse_only
from app.data.indices import INDEX_KEYS, IndexKey, load_index
from app.data.nse import load_securities

MarketKey = Literal["nse_all", "bse_only", "all_listed"]
MARKET_LABELS: dict[MarketKey, str] = {
    "nse_all": "All NSE stocks",
    "bse_only": "BSE-only stocks",
    "all_listed": "Every listed stock (NSE + BSE-only)",
}


@dataclass(frozen=True)
class Listing:
    ticker: str  # Yahoo form: "TCS.NS" or "ANDHRAPET.BO"
    symbol: str
    name: str
    exchange: str  # "NSE" | "BSE" (BSE only)
    isin: str
    index: IndexKey | None  # the smallest Nifty index it belongs to
    industry: str | None  # NSE's industry for Nifty 500 members


@lru_cache
def all_listings() -> tuple[Listing, ...]:
    member: dict[str, IndexKey] = {}
    industry: dict[str, str] = {}
    for key in reversed(INDEX_KEYS):  # Nifty 500 first, so smaller indices overwrite
        for c in load_index(key):
            member[c.symbol] = key
            if c.industry:
                industry[c.symbol] = c.industry
    out: list[Listing] = []
    seen: set[str] = set()
    for s in (*load_securities(), *bse_only()):
        if s.kind != "equity" or s.ticker in seen:
            continue
        seen.add(s.ticker)
        nse = s.exchange == "NSE"
        out.append(
            Listing(
                s.ticker,
                s.symbol,
                s.name,
                s.exchange,
                s.isin,
                member.get(s.symbol) if nse else None,
                industry.get(s.symbol) if nse else None,
            )
        )
    return tuple(out)


def market_listings(key: MarketKey) -> list[Listing]:
    every = all_listings()
    if key == "nse_all":
        return [x for x in every if x.exchange == "NSE"]
    if key == "bse_only":
        return [x for x in every if x.exchange == "BSE"]
    return list(every)
