"""SQLModel tables.

Timestamps are stored in UTC and converted to IST at the API boundary (see ISTDatetime).
"""

import datetime as dt
from datetime import UTC, date, datetime

from sqlmodel import Field, SQLModel


def utcnow() -> datetime:
    return datetime.now(UTC)


class UserProfile(SQLModel, table=True):
    """Single-row table (id=1) holding the investor's chosen style and risk."""

    id: int = Field(default=1, primary_key=True)
    style: str | None = None  # None until onboarding is complete
    risk: str = "medium"
    custom_technical_weight: float = 0.5
    gsheet_url: str | None = None
    updated_at: datetime = Field(default_factory=utcnow)


class Snapshot(SQLModel, table=True):
    """One import = one dated snapshot. The latest snapshot of each kind is the live portfolio."""

    id: int | None = Field(default=None, primary_key=True)
    kind: str = Field(index=True)  # "stocks" | "mf"
    source: (
        str  # "groww_xlsx" | "groww_csv" | "cas_cams" | "cas_kfintech" | "cas_nsdl" | "manual" …
    )
    filename: str | None = None
    created_at: datetime = Field(default_factory=utcnow, index=True)
    row_count: int = 0
    total_invested: float | None = None
    total_value: float | None = None
    note: str | None = None


class StockHolding(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    snapshot_id: int = Field(foreign_key="snapshot.id", index=True)
    name: str
    isin: str | None = None
    symbol: str | None = None  # exchange symbol without suffix, e.g. "RELIANCE"
    exchange: str | None = None  # "NSE" | "BSE"
    resolution: str = (
        "unresolved"  # "isin" | "name" | "symbol" | "override" | "manual" | "unresolved"
    )
    resolution_score: float | None = None
    suggestions: str | None = None  # JSON list of {symbol, name, score}
    quantity: float
    avg_price: float
    close_price: float | None = None
    invested: float
    current_value: float | None = None
    unrealised_pnl: float | None = None
    purchase_date: date | None = None


class MFHolding(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    snapshot_id: int = Field(foreign_key="snapshot.id", index=True)
    scheme_name: str
    amc: str | None = None
    category: str | None = None
    folio: str | None = None
    isin: str | None = None
    amfi_code: str | None = None
    plan: str | None = None  # "direct" | "regular"
    option: str | None = None  # "growth" | "idcw"
    resolution: str = "unresolved"  # "amfi_code" | "isin" | "name" | "override" | "manual" | …
    resolution_score: float | None = None
    suggestions: str | None = None  # JSON list of {amfi_code, name, score}
    units: float
    invested: float | None = None
    current_value: float | None = None
    nav: float | None = None
    nav_date: date | None = None
    first_purchase_date: date | None = None
    origin: str = "import"  # "import" | "manual"


class MFTransaction(SQLModel, table=True):
    """Cash flows from a detailed CAS; used for XIRR and holding periods in Phase 7."""

    id: int | None = Field(default=None, primary_key=True)
    holding_id: int = Field(foreign_key="mfholding.id", index=True)
    date: dt.date
    type: str
    description: str | None = None
    amount: float | None = None
    units: float | None = None
    nav: float | None = None


class ColumnMapping(SQLModel, table=True):
    """A user-confirmed column mapping, reused when a file with the same headers is imported."""

    id: int | None = Field(default=None, primary_key=True)
    kind: str  # "stocks" | "mf"
    signature: str = Field(index=True, unique=True)
    mapping_json: str  # {"field": column_index}
    created_at: datetime = Field(default_factory=utcnow)


class TickerOverride(SQLModel, table=True):
    """Manual ticker fix, applied automatically on future imports. key = 'isin:…' or 'name:…'."""

    id: int | None = Field(default=None, primary_key=True)
    key: str = Field(index=True, unique=True)
    symbol: str
    exchange: str = "NSE"
    created_at: datetime = Field(default_factory=utcnow)


class SchemeOverride(SQLModel, table=True):
    """Manual MF scheme fix. key = 'name:…' (normalised scheme name)."""

    id: int | None = Field(default=None, primary_key=True)
    key: str = Field(index=True, unique=True)
    amfi_code: str
    created_at: datetime = Field(default_factory=utcnow)


# --------------------------------------------------------------------------- market data cache


class DailyBar(SQLModel, table=True):
    """One completed trading session from Yahoo Finance. `close` is split-adjusted;
    `adj_close` is also dividend-adjusted."""

    ticker: str = Field(primary_key=True)  # Yahoo form: "RELIANCE.NS", "500325.BO", "^NSEI"
    date: dt.date = Field(primary_key=True)
    open: float | None = None
    high: float | None = None
    low: float | None = None
    close: float
    adj_close: float | None = None
    volume: float | None = None


class IntradayBar(SQLModel, table=True):
    """Delayed intraday bars (15m / 1h), fetched on demand for the intraday style."""

    ticker: str = Field(primary_key=True)
    interval: str = Field(primary_key=True)  # "15m" | "1h"
    ts: datetime = Field(primary_key=True)  # bar start, UTC
    open: float | None = None
    high: float | None = None
    low: float | None = None
    close: float
    volume: float | None = None


class NavPoint(SQLModel, table=True):
    amfi_code: str = Field(primary_key=True)
    date: dt.date = Field(primary_key=True)
    nav: float


class SeriesStatus(SQLModel, table=True):
    """Freshness bookkeeping for every cached series and reference list.

    key: "price:RELIANCE.NS" | "intraday:RELIANCE.NS:15m" | "nav:118989" | "ref:nse_equity" …
    """

    key: str = Field(primary_key=True)
    kind: str = Field(index=True)  # "price" | "intraday" | "nav" | "reference"
    source: str  # "yahoo" | "mfapi" | "nse" | "amfi"
    label: str | None = None
    last_attempt_at: datetime | None = None
    last_success_at: datetime | None = None
    last_error: str | None = None
    first_date: date | None = None
    last_date: date | None = None
    rows: int = 0
    history_from: date | None = None  # earliest date we've asked the source for


class Job(SQLModel, table=True):
    """A background job (data refresh, later screener runs) and its progress."""

    id: int | None = Field(default=None, primary_key=True)
    kind: str = Field(index=True)
    params: str | None = None  # JSON
    status: str = "queued"  # "queued" | "running" | "done" | "failed"
    trigger: str = "manual"  # "manual" | "schedule" | "startup"
    created_at: datetime = Field(default_factory=utcnow, index=True)
    started_at: datetime | None = None
    finished_at: datetime | None = None
    done: int = 0
    total: int = 0
    message: str | None = None
    errors: str | None = None  # JSON list of strings


class DeliveryStat(SQLModel, table=True):
    """Per-symbol delivery data from NSE's daily full bhavcopy (EQ series only)."""

    symbol: str = Field(primary_key=True)
    date: dt.date = Field(primary_key=True)
    close: float | None = None
    traded_qty: float | None = None
    turnover_lacs: float | None = None  # ₹ lakh
    deliv_qty: float | None = None
    deliv_pct: float | None = None


class BhavcopyDay(SQLModel, table=True):
    """Which bhavcopy files we have fetched; 'missing' = NSE has no file (holiday)."""

    date: dt.date = Field(primary_key=True)
    status: str  # "ok" | "missing"
    rows: int = 0
    fetched_at: datetime = Field(default_factory=utcnow)
