"""Where reference lists live: a refreshed copy in var/reference/ wins over the bundled fallback."""

import gzip
import json
import logging
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Literal

from app.core.profiles import ReferenceKey, SourceKey
from app.core.settings import get_settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ReferenceFile:
    key: ReferenceKey
    label: str
    source: SourceKey
    url: str
    filename: str  # same name in var/reference/ and data/fallback/
    gzipped: bool = False


REFERENCE_FILES: dict[ReferenceKey, ReferenceFile] = {
    f.key: f
    for f in (
        ReferenceFile(
            "nse_equity",
            "NSE equity list",
            "nse",
            "https://nsearchives.nseindia.com/content/equities/EQUITY_L.csv",
            "EQUITY_L.csv",
        ),
        ReferenceFile(
            "nse_etf",
            "NSE ETF list",
            "nse",
            "https://nsearchives.nseindia.com/content/equities/eq_etfseclist.csv",
            "eq_etfseclist.csv",
        ),
        ReferenceFile(
            "nifty500",
            "Nifty 500 constituents",
            "nse",
            "https://nsearchives.nseindia.com/content/indices/ind_nifty500list.csv",
            "ind_nifty500list.csv",
        ),
        ReferenceFile(
            "amfi_navall",
            "AMFI scheme list & latest NAVs",
            "amfi",
            "https://portal.amfiindia.com/spages/NAVAll.txt",
            "NAVAll.txt.gz",
            gzipped=True,
        ),
    )
}

Origin = Literal["refreshed", "bundled"]


def locate(key: ReferenceKey) -> tuple[Path, Origin]:
    f = REFERENCE_FILES[key]
    s = get_settings()
    refreshed = s.reference_data_dir / f.filename
    if refreshed.exists():
        return refreshed, "refreshed"
    return s.fallback_data_dir / f.filename, "bundled"


def read_text(key: ReferenceKey) -> str:
    path, origin = locate(key)
    raw = path.read_bytes()
    if REFERENCE_FILES[key].gzipped:
        raw = gzip.decompress(raw)
    logger.debug("Reading %s from %s copy %s", key, origin, path)
    return raw.decode("utf-8", errors="replace")


def bundled_as_of(key: ReferenceKey) -> date | None:
    """Download date of the bundled copy, from data/fallback/MANIFEST.json."""
    manifest = get_settings().fallback_data_dir / "MANIFEST.json"
    try:
        stamp = json.loads(manifest.read_text())["downloaded_on"][REFERENCE_FILES[key].filename]
        return date.fromisoformat(stamp)
    except (OSError, KeyError, ValueError):
        return None
