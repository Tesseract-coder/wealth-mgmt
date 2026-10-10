"""Index constituent lists from NSE (Nifty 50/100/200/500): symbol, company, industry, ISIN.

The industry column is NSE's sector classification, used for sector weights and screener filters.
"""

import csv
import io
import logging
from dataclasses import dataclass
from functools import lru_cache
from typing import Literal, get_args

from app.data.files import read_text

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Constituent:
    symbol: str
    name: str
    industry: str
    isin: str


def parse_index_list(text: str) -> list[Constituent]:
    """Parse ind_nifty*list.csv (Company Name, Industry, Symbol, Series, ISIN Code)."""
    out = []
    for row in csv.DictReader(io.StringIO(text.lstrip("﻿"))):
        r = {(k or "").strip(): (v or "").strip() for k, v in row.items()}
        if r.get("Symbol"):
            out.append(
                Constituent(
                    symbol=r["Symbol"],
                    name=r.get("Company Name", ""),
                    industry=r.get("Industry", ""),
                    isin=r.get("ISIN Code", "").upper(),
                )
            )
    return out


IndexKey = Literal["nifty50", "nifty100", "nifty200", "nifty500"]
INDEX_KEYS: tuple[IndexKey, ...] = get_args(IndexKey)
INDEX_LABELS: dict[IndexKey, str] = {k: f"Nifty {k.removeprefix('nifty')}" for k in INDEX_KEYS}


@lru_cache
def load_index(key: IndexKey) -> tuple[Constituent, ...]:
    items = tuple(parse_index_list(read_text(key)))
    logger.info("Loaded %d %s constituents", len(items), INDEX_LABELS[key])
    return items


def load_nifty500() -> tuple[Constituent, ...]:
    return load_index("nifty500")


@lru_cache
def nifty500_by_symbol() -> dict[str, Constituent]:
    return {c.symbol: c for c in load_nifty500()}


def industry_of(symbol: str) -> str | None:
    """NSE industry for a Nifty 500 stock; None for anything outside the index."""
    c = nifty500_by_symbol().get(symbol)
    return c.industry if c else None
