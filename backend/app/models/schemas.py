import datetime as dt
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
    kind: Literal["stocks", "mf", "screener", "fund_portfolio"]
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


# --------------------------------------------------------------------------- market data

FreshnessStatus = Literal["fresh", "stale", "unavailable"]


class FreshnessOut(BaseModel):
    status: FreshnessStatus
    reason: str


class ReferenceStatusOut(BaseModel):
    key: str
    label: str
    source: str
    origin: Literal["refreshed", "bundled"]
    as_of: date | None
    rows: int | None
    freshness: FreshnessOut


class QuoteOut(BaseModel):
    kind: Literal["stock", "benchmark", "mf"]
    code: str
    label: str
    price: float | None
    previous: float | None
    change_pct: float | None
    as_of: date | None
    source: str | None
    freshness: FreshnessOut


class ScheduleOut(BaseModel):
    enabled: bool
    prices: str
    navs: str
    fundamentals: str


class JobOut(BaseModel):
    id: int
    kind: str
    status: Literal["queued", "running", "done", "failed"]
    trigger: str
    params: dict[str, object]
    created_at: ISTDatetime
    started_at: ISTDatetime | None
    finished_at: ISTDatetime | None
    done: int
    total: int
    message: str | None
    errors: list[str]


class MarketStatusOut(BaseModel):
    generated_at: ISTDatetime
    summary: dict[FreshnessStatus, int]
    references: list[ReferenceStatusOut]
    quotes: list[QuoteOut]
    schedule: ScheduleOut
    last_job: JobOut | None
    last_fundamentals_job: JobOut | None
    notes: list[str]


class BarOut(BaseModel):
    t: str  # ISO date for daily bars, ISO datetime (IST) for intraday
    open: float | None
    high: float | None
    low: float | None
    close: float
    adj_close: float | None = None
    volume: float | None


class PriceSeriesOut(BaseModel):
    ticker: str
    interval: str
    source: str
    delayed: bool
    last_complete: bool
    freshness: FreshnessOut
    fetch_error: str | None
    bars: list[BarOut]


class NavPointOut(BaseModel):
    date: dt.date
    nav: float


class NavSeriesOut(BaseModel):
    code: str
    scheme_name: str | None
    freshness: FreshnessOut
    fetch_error: str | None
    points: list[NavPointOut]


class RefreshIn(BaseModel):
    scope: Literal["all", "reference", "prices", "navs", "fundamentals"] = "all"
    force: bool = False


# --------------------------------------------------------------------------- technical analysis


class ObservationOut(BaseModel):
    key: str
    category: str
    direction: Literal["bullish", "bearish", "neutral"]
    text: str
    value: float | None
    minor: bool


class LevelOut(BaseModel):
    price: float
    touches: int
    kind: Literal["support", "resistance"]


class FrameAnalysisOut(BaseModel):
    values: dict[str, float | None]
    observations: list[ObservationOut]
    unavailable: list[str]
    levels: list[LevelOut]


class TimeframeOut(BaseModel):
    interval: str
    bars: int
    as_of: str | None
    last_close: float | None
    last_complete: bool
    freshness: FreshnessOut
    analysis: FrameAnalysisOut
    notes: list[str]


class TechnicalReportOut(BaseModel):
    ticker: str
    label: str
    style: StyleKey | None
    timeframes: list[TimeframeOut]
    context: FrameAnalysisOut
    fetch_errors: list[str]
    notes: list[str]
    disclaimer: str


class TechnicalSummaryOut(BaseModel):
    """One row per holding: a tally of the latest readings (scoring comes in Phase 6)."""

    ticker: str
    label: str
    interval: str
    as_of: str | None
    freshness: FreshnessOut
    bullish: int
    bearish: int
    neutral: int
    top_bullish: list[str]
    top_bearish: list[str]


class IndicatorSeriesOut(BaseModel):
    ticker: str
    interval: str
    t: list[str]
    columns: dict[str, list[float | None]]


# --------------------------------------------------------------------------- fundamentals


class ScreenerImportedOut(BaseModel):
    status: Literal["imported"] = "imported"
    kind: Literal["screen", "company"]
    upload_id: int
    matched: list[dict[str, str]]  # {"symbol", "name"}
    unmatched: list[str]
    warnings: list[str]


class MetricOut(BaseModel):
    key: str
    label: str
    value: float | None
    unit: str
    basis: str
    sector_median: float | None
    peers: int


class FTestOut(BaseModel):
    name: str
    passed: bool | None
    detail: str


class FScoreOut(BaseModel):
    score: int | None
    computable: int
    tests: list[FTestOut]


class FundamentalReportOut(BaseModel):
    ticker: str
    label: str
    sector: str | None
    is_financial: bool
    source: str | None
    latest_year: date | None
    freshness: FreshnessOut
    metrics: list[MetricOut]
    fscore: FScoreOut | None
    observations: list[ObservationOut]
    unavailable: list[str]
    notes: list[str]
    fetch_errors: list[str]
    disclaimer: str


class FundamentalSummaryOut(BaseModel):
    ticker: str
    label: str
    sector: str | None
    source: str | None
    freshness: FreshnessOut
    pe: float | None
    roe: float | None
    debt_equity: float | None
    fscore: int | None
    bullish: int
    bearish: int
    top_bullish: list[str]
    top_bearish: list[str]


# --------------------------------------------------------------------------- scores & signals

SignalKey = Literal["strong_buy", "buy", "hold", "reduce", "sell", "no_signal"]
ConfidenceOut = Literal["high", "medium", "low"]


class ReadingOut(BaseModel):
    source: Literal["technical", "fundamental"]
    key: str
    category: str
    direction: Literal["bullish", "bearish", "neutral"]
    text: str
    minor: bool
    weight: float
    points: float = Field(description="Points this reading adds to the composite score")
    timeframes: list[str]


class SubScoreOut(BaseModel):
    category: str
    score: float | None
    weight: float
    bullish: int
    bearish: int
    neutral: int


class TimeframeScoreOut(BaseModel):
    interval: str
    score: float | None
    coverage: float
    weight: float
    subscores: list[SubScoreOut]


class SideScoreOut(BaseModel):
    score: float | None
    coverage: float
    applicable: bool
    subscores: list[SubScoreOut]
    timeframes: list[TimeframeScoreOut]
    notes: list[str]


class ScoresOut(BaseModel):
    composite: float | None
    technical: SideScoreOut
    fundamental: SideScoreOut
    technical_weight: float
    fundamental_weight: float
    coverage: float
    confidence: ConfidenceOut | None
    confidence_reason: str


class FlagOut(BaseModel):
    key: str
    severe: bool
    text: str


class TargetOut(BaseModel):
    label: str
    price: float
    pct: float


class PriceLevelsOut(BaseModel):
    interval: str
    close: float
    as_of: str
    atr: float
    multiple: float
    trailing_stop: float
    entry_stop: float
    stop_breached: bool
    risk_per_share: float
    targets: list[TargetOut]
    basis: str


class LotOut(BaseModel):
    quantity: float
    avg_price: float
    purchase_date: date | None


class PositionOut(BaseModel):
    quantity: float
    avg_price: float
    invested: float
    price: float | None
    price_source: str
    value: float | None
    pnl: float | None
    pnl_pct: float | None
    lots: list[LotOut]


class RebalanceOut(BaseModel):
    action: Literal["add", "trim", "exit", "none"]
    quantity: int
    value: float | None
    target_weight: float | None
    text: str


class TaxNoteOut(BaseModel):
    holding_days: int | None
    term: Literal["short", "long", "mixed", "unknown"]
    long_term_from: date | None
    text: list[str]
    verify_note: str


class StockSignalOut(BaseModel):
    ticker: str
    label: str
    style: StyleKey
    style_label: str
    risk: RiskKey
    risk_label: str
    signal: SignalKey
    signal_label: str
    rule: str
    scores: ScoresOut
    bullish: list[ReadingOut]
    bearish: list[ReadingOut]
    readings: list[ReadingOut]
    flags: list[FlagOut]
    levels: PriceLevelsOut | None
    beta: float | None
    beta_basis: str
    position: PositionOut | None
    weight: float | None
    max_weight: float
    sector: str | None
    sector_weight: float | None
    max_sector_weight: float
    rebalance: RebalanceOut
    tax: TaxNoteOut | None
    price_freshness: FreshnessOut
    fundamental_freshness: FreshnessOut
    notes: list[str]
    disclaimer: str


class HoldingSignalOut(BaseModel):
    ticker: str
    label: str
    signal: SignalKey
    signal_label: str
    rule: str
    composite: float | None
    technical: float | None
    fundamental: float | None
    confidence: ConfidenceOut | None
    weight: float | None
    max_weight: float
    value: float | None
    pnl: float | None
    sector: str | None
    flags: list[FlagOut]
    top_bullish: list[str]
    top_bearish: list[str]
    rebalance: RebalanceOut
    stop: float | None
    stop_breached: bool
    price_freshness: FreshnessOut


class SectorWeightOut(BaseModel):
    sector: str
    weight: float
    limit: float
    over: bool


class HoldingSignalsOut(BaseModel):
    style: StyleKey
    style_label: str
    risk: RiskKey
    risk_label: str
    technical_weight: float
    weight_base: Literal["portfolio", "stocks"]
    total_value: float
    stock_value: float
    fund_value: float
    sectors: list[SectorWeightOut]
    holdings: list[HoldingSignalOut]
    notes: list[str]
    disclaimer: str


class SignalHistoryOut(BaseModel):
    day: date
    style: str
    risk: str
    signal: SignalKey
    signal_label: str
    composite: float | None
    technical: float | None
    fundamental: float | None
    confidence: ConfidenceOut | None


# --------------------------------------------------------------------------- mutual funds

FundSignalKey = Literal["continue", "review", "switch", "no_signal"]


class RiskStatsOut(BaseModel):
    start: date
    end: date
    years: float
    cagr: float | None
    volatility: float
    sharpe: float | None
    sortino: float | None
    max_drawdown: float
    drawdown_peak: date
    drawdown_trough: date


class RollingOut(BaseModel):
    years: int
    windows: int
    fund_avg: float
    bench_avg: float
    avg_excess: float
    beat_share: float
    worst_excess: float
    best_excess: float
    first_start: date
    last_start: date


class FundReasonOut(BaseModel):
    direction: Literal["bullish", "bearish", "neutral"]
    text: str


class OverlapOut(BaseModel):
    code: str
    name: str
    pct: float
    common: int
    approximate: bool
    note: str


class MyFundHoldingOut(BaseModel):
    units: float
    invested: float | None
    value: float | None
    pnl: float | None
    folios: list[str]
    first_purchase: date | None
    xirr: float | None
    xirr_basis: str
    xirr_approximate: bool


class BenchmarkOut(BaseModel):
    ticker: str
    label: str


class SchemeRefOut(BaseModel):
    code: str
    name: str


class PeriodReturnOut(BaseModel):
    years: int
    fund: float | None
    benchmark: float | None


class FundReportOut(BaseModel):
    code: str
    name: str
    amc: str | None
    category: str | None
    asset_class: Literal["equity", "debt", "hybrid", "other"]
    plan: str | None
    option: str | None
    nav: float | None
    nav_date: date | None
    previous_nav: float | None
    nav_freshness: FreshnessOut
    history_start: date | None
    holding: MyFundHoldingOut | None
    returns: list[PeriodReturnOut]
    benchmark: BenchmarkOut | None
    risk: RiskStatsOut | None
    benchmark_risk: RiskStatsOut | None
    rolling: list[RollingOut]
    direct_twin: SchemeRefOut | None
    direct_gap_pp: float | None
    direct_gap_basis: str
    expense_ratio_pct: float | None
    overlaps: list[OverlapOut]
    segment_peers: list[str]
    signal: FundSignalKey
    signal_label: str
    rule: str
    reasons: list[FundReasonOut]
    notes: list[str]
    unavailable: list[str]
    fetch_errors: list[str]
    disclaimer: str


class OverlapMatrixOut(BaseModel):
    codes: list[str]
    names: list[str]
    pct: list[list[float | None]]  # None: no holdings uploaded for one of the pair
    approximate: bool


class MFHoldingsAnalysisOut(BaseModel):
    funds: list[FundReportOut]
    overlap: OverlapMatrixOut
    warnings: list[str]
    disclaimer: str


class ExpenseRatioIn(BaseModel):
    expense_ratio_pct: float | None = Field(None, ge=0, le=5)


class FundPortfolioImportedOut(BaseModel):
    status: Literal["imported"] = "imported"
    upload_id: int
    amfi_code: str
    scheme_name: str
    rows: int
    total_weight_pct: float
    warnings: list[str]


# --------------------------------------------------------------------------- portfolio


class SliceOut(BaseModel):
    key: str
    label: str
    value: float
    weight: float


class SnapshotPointOut(BaseModel):
    created_at: ISTDatetime
    kind: str
    total_value: float | None


class PortfolioSummaryOut(BaseModel):
    as_of: date | None
    total_value: float
    stock_value: float
    fund_value: float
    invested: float | None
    invested_note: str | None
    pnl: float | None
    pnl_pct: float | None
    day_change: float | None
    day_change_pct: float | None
    day_change_note: str | None
    xirr: float | None
    xirr_coverage: float
    xirr_basis: str
    by_holding: list[SliceOut]
    by_sector: list[SliceOut]
    by_mcap: list[SliceOut]
    by_asset_class: list[SliceOut]
    warnings: list[str]
    beta: float | None
    beta_coverage: float
    beta_basis: str
    correlation_labels: list[str]
    correlation: list[list[float | None]]
    correlation_basis: str
    performance_dates: list[date]
    performance_portfolio: list[float]
    performance_nifty: list[float]
    performance_basis: str
    snapshots: list[SnapshotPointOut]
    notes: list[str]
    disclaimer: str
