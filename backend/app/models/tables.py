"""SQLModel tables.

Timestamps are stored in UTC and converted to IST at the API boundary (see ISTDatetime).
"""

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
    date: date
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
