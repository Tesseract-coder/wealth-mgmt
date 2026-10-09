from datetime import date
from typing import Literal

from pydantic import BaseModel, Field

from app.core.formatting import ISTDatetime
from app.core.profiles import RiskKey, StyleKey


class HealthOut(BaseModel):
    status: str
    database: str
    config_version: int
    server_time_ist: str


class MetaOut(BaseModel):
    disclaimer: str
    timezone: str
    currency: str


class ProfileOut(BaseModel):
    style: StyleKey | None
    risk: RiskKey
    custom_technical_weight: float
    gsheet_url: str | None
    onboarded: bool
    updated_at: ISTDatetime


class ProfileIn(BaseModel):
    style: StyleKey
    risk: RiskKey = "medium"
    custom_technical_weight: float = Field(default=0.5, ge=0, le=1)
    gsheet_url: str | None = None


# --------------------------------------------------------------------------- import / portfolio


class SnapshotOut(BaseModel):
    id: int
    kind: Literal["stocks", "mf"]
    source: str
    filename: str | None
    created_at: ISTDatetime
    row_count: int
    total_invested: float | None
    total_value: float | None
    note: str | None


class Suggestion(BaseModel):
    symbol: str | None = None
    amfi_code: str | None = None
    name: str
    score: float


class StockHoldingOut(BaseModel):
    id: int
    snapshot_id: int
    name: str
    isin: str | None
    symbol: str | None
    exchange: str | None
    resolution: str
    resolution_score: float | None
    suggestions: list[Suggestion]
    quantity: float
    avg_price: float
    close_price: float | None
    invested: float
    current_value: float | None
    unrealised_pnl: float | None
    purchase_date: date | None


class MFHoldingOut(BaseModel):
    id: int
    snapshot_id: int
    scheme_name: str
    amc: str | None
    category: str | None
    folio: str | None
    isin: str | None
    amfi_code: str | None
    plan: str | None
    option: str | None
    resolution: str
    resolution_score: float | None
    suggestions: list[Suggestion]
    units: float
    invested: float | None
    current_value: float | None
    nav: float | None
    nav_date: date | None
    first_purchase_date: date | None
    origin: str
    transaction_count: int = 0


class SkippedRowOut(BaseModel):
    row: int
    reason: str
    text: str


class ImportedOut(BaseModel):
    status: Literal["imported"] = "imported"
    snapshot: SnapshotOut
    skipped: list[SkippedRowOut]
    warnings: list[str]
    unresolved: int


class FieldSpecOut(BaseModel):
    key: str
    label: str
    required: bool


class NeedsMappingOut(BaseModel):
    status: Literal["needs_mapping"] = "needs_mapping"
    kind: Literal["stocks", "mf"]
    header_row: int  # 0-based
    headers: list[str]
    detected: dict[str, int]
    missing_required: list[str]
    fields: list[FieldSpecOut]
    preview: list[list[str]]


class ColumnMappingIn(BaseModel):
    """Sent as a JSON string in the 'mapping' form field alongside the file."""

    header_row: int = Field(ge=0)
    columns: dict[str, int]
    remember: bool = True


class ManualMFIn(BaseModel):
    scheme: str = Field(min_length=1, description="AMFI scheme code or scheme name")
    units: float = Field(gt=0)
    invested: float = Field(ge=0)
    folio: str | None = None
    purchase_date: date | None = None


class TickerFixIn(BaseModel):
    symbol: str = Field(min_length=1)
    exchange: Literal["NSE", "BSE"] = "NSE"
    remember: bool = True


class SchemeFixIn(BaseModel):
    amfi_code: str = Field(min_length=1)
    remember: bool = True


class HoldingsOut(BaseModel):
    stocks_snapshot: SnapshotOut | None
    stocks: list[StockHoldingOut]
    mf_snapshot: SnapshotOut | None
    mf: list[MFHoldingOut]
