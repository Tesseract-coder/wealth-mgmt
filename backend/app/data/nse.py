"""NSE securities master (equities + ETFs), used to resolve ISIN / company name → symbol.

Reads the refreshed copy in var/reference/ when present, else the bundled one (see files.py).
"""

import csv
import io
import logging
from dataclasses import dataclass
from functools import lru_cache

from app.data.files import read_text

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Security:
    symbol: str
    name: str
    isin: str
    series: str  # "EQ", "BE", … or "ETF" (for BSE-only shares: BSE's group, "A", "X", "M" …)
    kind: str  # "equity" | "etf"
    exchange: str = "NSE"  # "BSE" for shares listed only on BSE (see bse.py)
    bse_code: str | None = None

    @property
    def ticker(self) -> str:
        """Yahoo's ticker: "RELIANCE.NS", or "ANDHRAPET.BO" for a BSE-only share."""
        return f"{self.symbol}.BO" if self.exchange == "BSE" else f"{self.symbol}.NS"


def _rows(text: str) -> list[dict[str, str]]:
    reader = csv.DictReader(io.StringIO(text.lstrip("﻿")))
    return [{(k or "").strip(): (v or "").strip() for k, v in row.items()} for row in reader]


def parse_equity_list(text: str) -> list[Security]:
    """Parse NSE EQUITY_L.csv (columns: SYMBOL, NAME OF COMPANY, SERIES, …, ISIN NUMBER, …)."""
    out = []
    for r in _rows(text):
        if r.get("SYMBOL") and r.get("ISIN NUMBER"):
            out.append(
                Security(
                    symbol=r["SYMBOL"],
                    name=r.get("NAME OF COMPANY", ""),
                    isin=r["ISIN NUMBER"].upper(),
                    series=r.get("SERIES", ""),
                    kind="equity",
                )
            )
    return out


def parse_etf_list(text: str) -> list[Security]:
    """Parse NSE eq_etfseclist.csv (Symbol, Underlying Asset, SecurityName, …, ISINNumber)."""
    out = []
    for r in _rows(text):
        if r.get("Symbol") and r.get("ISINNumber"):
            out.append(
                Security(
                    symbol=r["Symbol"],
                    name=r.get("Underlying Asset") or r.get("SecurityName", ""),
                    isin=r["ISINNumber"].upper(),
                    series="ETF",
                    kind="etf",
                )
            )
    return out


@lru_cache
def load_securities() -> tuple[Security, ...]:
    securities = parse_equity_list(read_text("nse_equity"))
    try:
        securities += parse_etf_list(read_text("nse_etf"))
    except FileNotFoundError:
        logger.warning("ETF list missing; ETFs will not resolve by ISIN")
    logger.info("Loaded %d NSE securities", len(securities))
    return tuple(securities)
