"""BSE equity list, built from BSE's daily bhavcopy.

BSE's scrip-list API refuses scripted downloads, but the bhavcopy (every share traded that day,
with its BSE code, symbol, name and ISIN) is a public file. Each refresh merges the latest
bhavcopy into the stored list; a share that hasn't traded for `BSE_KEEP_DAYS` drops out.

Shares also listed on NSE are used through NSE (better Yahoo data, delivery figures); the rest
become "SYMBOL.BO" tickers.
"""

import csv
import io
import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from functools import lru_cache

from app.data.files import read_text
from app.data.http import FetchError, get_bytes
from app.data.nse import Security, load_securities

logger = logging.getLogger(__name__)

BHAVCOPY_URL = (
    "https://www.bseindia.com/download/BhavCopy/Equity/BhavCopy_BSE_CM_0_0_0_{d:%Y%m%d}_F_0000.CSV"
)
# Days back to look for the latest bhavcopy (weekends, holidays, not yet published today).
LOOKBACK_DAYS = 7
BSE_KEEP_DAYS = 30
# BSE groups that aren't company shares: debt (F), government securities and gold bonds (G),
# REITs and InvITs (IF), ETFs (E) and rights entitlements (R).
NOT_SHARES = frozenset({"F", "G", "IF", "E", "R"})
LIST_COLUMNS = ["code", "symbol", "name", "isin", "group", "last_seen"]


@dataclass(frozen=True)
class BseScrip:
    code: str  # "500325"
    symbol: str  # "RELIANCE"; Yahoo's ticker is this plus ".BO"
    name: str
    isin: str
    group: str  # "A", "B", "X", "M" (SME) …
    last_seen: date


def is_share(group: str, isin: str) -> bool:
    return group not in NOT_SHARES and isin.startswith("INE")


def parse_bhavcopy(text: str) -> list[BseScrip]:
    """Shares in one day's bhavcopy (columns TradDt, FinInstrmId, ISIN, TckrSymb, SctySrs, …)."""
    reader = csv.DictReader(io.StringIO(text.lstrip("﻿")))
    if not reader.fieldnames or "FinInstrmId" not in reader.fieldnames:
        raise ValueError("not a BSE bhavcopy (no FinInstrmId column)")
    out = []
    for r in reader:
        code, sym, isin = (r.get(k, "").strip() for k in ("FinInstrmId", "TckrSymb", "ISIN"))
        group = r.get("SctySrs", "").strip()
        if not (code and sym and isin) or not is_share(group, isin):
            continue
        day = date.fromisoformat(r.get("TradDt", "").strip()[:10])
        out.append(BseScrip(code, sym, r.get("FinInstrmNm", "").strip(), isin.upper(), group, day))
    return out


def parse_list(text: str) -> list[BseScrip]:
    """The stored list (LIST_COLUMNS)."""
    reader = csv.DictReader(io.StringIO(text.lstrip("﻿")))
    return [
        BseScrip(
            r["code"],
            r["symbol"],
            r["name"],
            r["isin"],
            r["group"],
            date.fromisoformat(r["last_seen"]),
        )
        for r in reader
        if r.get("code") and r.get("symbol") and r.get("isin")
    ]


def write_list(scrips: list[BseScrip]) -> str:
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(LIST_COLUMNS)
    for s in sorted(scrips, key=lambda s: s.code):
        w.writerow([s.code, s.symbol, s.name, s.isin, s.group, s.last_seen.isoformat()])
    return buf.getvalue()


def merge(old: list[BseScrip], new: list[BseScrip], today: date) -> list[BseScrip]:
    """The newest entry per BSE code, dropping codes unseen for BSE_KEEP_DAYS."""
    by_code = {s.code: s for s in old}
    for s in new:
        prev = by_code.get(s.code)
        if prev is None or s.last_seen >= prev.last_seen:
            by_code[s.code] = s
    cutoff = today - timedelta(days=BSE_KEEP_DAYS)
    return [s for s in by_code.values() if s.last_seen >= cutoff]


def download_list(now: datetime) -> bytes:
    """The stored list with the latest published bhavcopy merged in, as the file's bytes."""
    latest: list[BseScrip] | None = None
    tried = []
    for back in range(LOOKBACK_DAYS):
        d = now.date() - timedelta(days=back)
        if d.weekday() >= 5:
            continue
        try:
            raw = get_bytes("bse", BHAVCOPY_URL.format(d=d))
            latest = parse_bhavcopy(raw.decode("utf-8-sig", errors="replace"))
            break
        except (FetchError, ValueError) as e:  # not published yet: BSE answers with a web page
            tried.append(f"{d:%d %b}: {e}")
    if latest is None:
        raise FetchError("No BSE bhavcopy in the last week (" + "; ".join(tried) + ")")
    try:
        old = parse_list(read_text("bse_equity"))
    except (FileNotFoundError, KeyError, ValueError):
        old = []
    return write_list(merge(old, latest, now.date())).encode()


@lru_cache
def load_bse() -> tuple[BseScrip, ...]:
    try:
        scrips = parse_list(read_text("bse_equity"))
    except FileNotFoundError:
        logger.warning("BSE list missing; only NSE stocks are known")
        return ()
    logger.info("Loaded %d BSE shares", len(scrips))
    return tuple(scrips)


@lru_cache
def bse_only() -> tuple[Security, ...]:
    """BSE shares with no NSE listing, as securities on exchange "BSE"."""
    on_nse = {s.isin for s in load_securities()}
    seen: set[str] = set()
    out = []
    for s in load_bse():
        if s.isin in on_nse or s.isin in seen:
            continue
        seen.add(s.isin)
        out.append(Security(s.symbol, s.name, s.isin, s.group, "equity", "BSE", s.code))
    return tuple(out)
