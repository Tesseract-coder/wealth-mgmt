"""NSE securities master (equities + ETFs), used to resolve ISIN / company name → symbol.

Phase 2 reads the bundled copies in data/fallback/. Phase 3 adds a live refresh with caching.
"""

import csv
import io
import logging
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from app.core.settings import get_settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Security:
    symbol: str
    name: str
    isin: str
    series: str  # "EQ", "BE", … or "ETF"
    kind: str  # "equity" | "etf"


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


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


@lru_cache
def load_securities() -> tuple[Security, ...]:
    d = get_settings().fallback_data_dir
    securities = parse_equity_list(_read(d / "EQUITY_L.csv"))
    try:
        securities += parse_etf_list(_read(d / "eq_etfseclist.csv"))
    except FileNotFoundError:
        logger.warning("ETF list missing from %s; ETFs will not resolve by ISIN", d)
    logger.info("Loaded %d NSE securities from bundled lists", len(securities))
    return tuple(securities)
