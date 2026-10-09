"""AMFI scheme master (NAVAll.txt): scheme code, ISINs, name, plan, option, latest NAV.

Handles both layouts AMFI has used:
  6 columns: Scheme Code;ISIN Div Payout/ISIN Growth;ISIN Div Reinvestment;Scheme Name;NAV;Date
  8 columns: Scheme Code;ISIN …;ISIN …;Scheme Name;Plan;Option;NAV;Date
Lines without ';' are section headers: either a category ("Open Ended Schemes(Equity Scheme - …)")
or an AMC name ("Axis Mutual Fund").

Phase 2 reads the bundled copy; Phase 3 adds a daily live refresh.
"""

import gzip
import logging
import re
from dataclasses import dataclass
from datetime import date, datetime
from functools import lru_cache

from app.core.settings import get_settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Scheme:
    code: str
    name: str  # full name as AMFI prints it (plan/option appended for the 8-column layout)
    isin_growth: str | None
    isin_reinvest: str | None
    plan: str | None  # "direct" | "regular"
    option: str | None  # "growth" | "idcw"
    nav: float | None
    nav_date: date | None
    category: str | None
    amc: str | None


def detect_plan(text: str) -> str | None:
    t = text.lower()
    if "direct" in t:
        return "direct"
    if "regular" in t:
        return "regular"
    return None


def detect_option(text: str) -> str | None:
    t = text.lower()
    if re.search(r"idcw|dividend|income distribution|\bdiv\b|bonus|payout|reinvest", t):
        return "idcw"
    if "growth" in t or "cumulative" in t:
        return "growth"
    return None


def _num(s: str) -> float | None:
    try:
        return float(s.replace(",", ""))
    except ValueError:
        return None


def _date(s: str) -> date | None:
    for fmt in ("%d-%b-%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(s.strip(), fmt).date()
        except ValueError:
            continue
    return None


def _isin(s: str) -> str | None:
    s = s.strip().upper()
    return s if re.fullmatch(r"IN[A-Z0-9]{10}", s) else None


_CATEGORY = re.compile(r"^(Open|Close|Closed|Interval) Ended Schemes?\s*\((.*)\)\s*$", re.I)


def parse_navall(text: str) -> list[Scheme]:
    schemes: list[Scheme] = []
    category: str | None = None
    amc: str | None = None
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if ";" not in line:
            m = _CATEGORY.match(line)
            if m:
                category = m.group(2).strip()
            else:
                amc = line
            continue
        parts = [p.strip() for p in line.split(";")]
        if not parts[0].isdigit():
            continue  # column header row
        if len(parts) >= 8:
            code, isin_g, isin_r, name, plan_s, option_s, nav, d = parts[:8]
            full = " - ".join(x for x in (name, plan_s, option_s) if x)
            plan, option = detect_plan(plan_s) or detect_plan(name), detect_option(option_s)
        elif len(parts) >= 6:
            code, isin_g, isin_r, name, nav, d = parts[:6]
            full, plan, option = name, detect_plan(name), detect_option(name)
        else:
            continue
        schemes.append(
            Scheme(
                code=code,
                name=full,
                isin_growth=_isin(isin_g),
                isin_reinvest=_isin(isin_r),
                plan=plan,
                option=option,
                nav=_num(nav),
                nav_date=_date(d),
                category=category,
                amc=amc,
            )
        )
    return schemes


@lru_cache
def load_schemes() -> tuple[Scheme, ...]:
    path = get_settings().fallback_data_dir / "NAVAll.txt.gz"
    text = gzip.decompress(path.read_bytes()).decode("utf-8", errors="replace")
    schemes = parse_navall(text)
    logger.info("Loaded %d AMFI schemes from bundled NAVAll", len(schemes))
    return tuple(schemes)
