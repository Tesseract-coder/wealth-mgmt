"""Two transparent valuation figures for the stock page: a fair-value estimate and the stock's own
P/E history. Both are labelled "Estimate" in the app; see docs/SCORING_METHOD.md.

Fair value is the average of what the company would be worth at its sector's median multiples:

* **Earnings**: sector-median P/E × the company's trailing profit.
* **Cash profit** (non-financials): sector-median EV/EBITDA × EBITDA, minus debt, plus cash.
* **Book value** (lenders and insurers, where EBITDA means little): sector-median P/B × equity.

Each method needs a sector median, which needs `fundamental.sector_min_peers` cached peers. The
estimate says what peers are priced at, not what the company is "really" worth: a company that
deserves a premium (faster growth, better returns) will look expensive on it.
"""

from dataclasses import dataclass
from datetime import date
from statistics import mean, median

import pandas as pd

from app.analysis.fundamental import Metric, _fy, _val
from app.core.formatting import format_inr


@dataclass(frozen=True)
class FairValueMethod:
    name: str
    value: float  # ₹ per share
    basis: str


@dataclass(frozen=True)
class FairValue:
    value: float  # ₹ per share: the average of the methods
    price: float
    gap_pct: float  # price vs fair value: negative = below (cheaper), positive = above
    methods: list[FairValueMethod]
    caveat: str


CAVEAT = (
    "Estimate: what the company would be worth at its sector's median multiples. It doesn't "
    "allow for faster growth or better returns than peers, which can justify a higher price."
)


def fair_value(
    metrics: dict[str, Metric],
    annual: pd.DataFrame | None,
    price: float | None,
    financial: bool,
) -> tuple[FairValue | None, str]:
    """(estimate, "") or (None, why it can't be made)."""
    mc = metrics.get("market_cap")
    if price is None or price <= 0 or mc is None or not mc.value or mc.value <= 0:
        return None, "needs a price and market cap"
    mcap = float(mc.value)

    def per_share(fair_mcap: float) -> float:
        return max(fair_mcap, 0.0) / mcap * price

    methods: list[FairValueMethod] = []
    pe = metrics.get("pe")
    if pe and pe.value and pe.value > 0 and pe.sector_median:
        methods.append(
            FairValueMethod(
                "Earnings",
                round(per_share(mcap * pe.sector_median / pe.value), 2),
                f"Sector median P/E {pe.sector_median:.1f}× applied to trailing profit "
                f"(P/E today {pe.value:.1f}×)",
            )
        )
    if financial:
        pb = metrics.get("pb")
        if pb and pb.value and pb.value > 0 and pb.sector_median:
            methods.append(
                FairValueMethod(
                    "Book value",
                    round(per_share(mcap * pb.sector_median / pb.value), 2),
                    f"Sector median P/B {pb.sector_median:.2f}× applied to equity "
                    f"(P/B today {pb.value:.2f}×)",
                )
            )
    else:
        ev = metrics.get("ev_ebitda")
        if ev and ev.value and ev.value > 0 and ev.sector_median and annual is not None:
            # Same debt and cash figures as the EV/EBITDA metric itself.
            debt, cash = _val(annual, "total_debt") or 0.0, _val(annual, "cash") or 0.0
            ebitda = (mcap + debt - cash) / ev.value
            methods.append(
                FairValueMethod(
                    "Cash profit",
                    round(per_share(ev.sector_median * ebitda - debt + cash), 2),
                    f"Sector median EV/EBITDA {ev.sector_median:.1f}× applied to EBITDA, "
                    f"less debt plus cash (EV/EBITDA today {ev.value:.1f}×)",
                )
            )
    if not methods:
        multiple = "P/E or P/B" if financial else "P/E or EV/EBITDA"
        return None, f"needs a sector median {multiple} (too few peers cached)"
    value = round(mean(m.value for m in methods), 2)
    gap = round((price / value - 1) * 100, 1) if value > 0 else float("inf")
    return FairValue(value, round(price, 2), gap, methods, CAVEAT), ""


@dataclass(frozen=True)
class YearPE:
    fy: str
    year_end: date
    price: float
    pe: float


def close_on(closes: pd.Series, d: date) -> float | None:
    """The last close on or before `d` (a year-end can fall on a holiday or weekend)."""
    before = closes[closes.index <= d]
    if before.empty:
        return None
    # Allow a week for holidays; earlier than that means the price history starts later.
    last = before.index[-1]
    return float(before.iloc[-1]) if (d - last).days <= 7 else None


def pe_history(
    annual: pd.DataFrame | None,
    closes: pd.Series,
    metrics: dict[str, Metric],
    price: float | None,
) -> list[YearPE]:
    """P/E at each financial year-end: that day's close × shares ÷ that year's profit.

    Uses the year's share count when the statements have one, else today's (market cap ÷
    price). Loss years are skipped: a P/E there means nothing."""
    if annual is None or annual.empty or closes.empty:
        return []
    mc = metrics.get("market_cap")
    shares_now = mc.value * 1e7 / price if mc and mc.value and price else None
    out: list[YearPE] = []
    for d in annual.index:
        ni = _val(annual.loc[[d]], "net_income")
        close = close_on(closes, d)
        shares = _val(annual.loc[[d]], "shares") or shares_now
        if ni is None or ni <= 0 or close is None or not shares:
            continue
        out.append(YearPE(_fy(d), d, round(close, 2), round(close * shares / 1e7 / ni, 2)))
    return out


def pe_history_median(points: list[YearPE]) -> float | None:
    return round(median(p.pe for p in points), 2) if len(points) >= 3 else None


def describe(fv: FairValue) -> str:
    if fv.value <= 0:  # debt outweighs what peers' multiples put on the business
        return (
            f"Price {format_inr(fv.price)} is far above the estimated fair value of "
            f"{format_inr(fv.value)}: at its sector's multiples the business is worth less than "
            "its debt."
        )
    side = "below" if fv.gap_pct < 0 else "above"
    return (
        f"Price {format_inr(fv.price)} is {abs(fv.gap_pct):.1f}% {side} the estimated fair value "
        f"of {format_inr(fv.value)}."
    )
