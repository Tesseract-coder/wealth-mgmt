"""India-specific formatting and time helpers."""

from datetime import UTC, datetime
from typing import Annotated
from zoneinfo import ZoneInfo

from pydantic import AfterValidator

IST = ZoneInfo("Asia/Kolkata")


def now_ist() -> datetime:
    return datetime.now(IST)


def format_inr(amount: float | None, decimals: int = 2) -> str:
    """Format with Indian digit grouping: 1234567.8 -> '₹12,34,567.80'."""
    if amount is None:
        return "—"
    sign = "-" if amount < 0 else ""
    whole, _, frac = f"{abs(amount):.{decimals}f}".partition(".")
    if len(whole) > 3:
        head, tail = whole[:-3], whole[-3:]
        groups: list[str] = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        if head:
            groups.insert(0, head)
        whole = ",".join(groups) + "," + tail
    return f"{sign}₹{whole}" + (f".{frac}" if decimals else "")


def format_freshness(ts: datetime) -> str:
    """'09 Oct 2026, 3:30 PM IST'."""
    local = ts.astimezone(IST)
    hour = local.strftime("%I").lstrip("0")
    return f"{local:%d %b %Y}, {hour}:{local:%M %p} IST"


def to_ist(ts: datetime) -> datetime:
    """Convert to IST. Naive datetimes are assumed to be UTC (how SQLite returns them)."""
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=UTC)
    return ts.astimezone(IST)


# Use for every datetime field in API responses so clients always see +05:30.
ISTDatetime = Annotated[datetime, AfterValidator(to_ist)]
