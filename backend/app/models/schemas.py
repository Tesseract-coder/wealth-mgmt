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


class ThresholdOut(BaseModel):
    path: str
    group: str
    label: str
    unit: Literal["fraction", "score", "x", "cr", "ratio"]
    nullable: bool
    value: float | None
    default: float | None
    edited: bool


class ThresholdsOut(BaseModel):
    items: list[ThresholdOut]
    override_file: str
    edited: int
    note: str


class ThresholdsIn(BaseModel):
    values: dict[str, float | None]


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


class ClearedOut(BaseModel):
    kind: Literal["stocks", "mf"]
    snapshots: int
    holdings: int


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


class ScheduledJobOut(BaseModel):
    id: str
    name: str
    next_run: ISTDatetime | None


class ScheduleOut(BaseModel):
    enabled: bool
    prices: str
    navs: str
    fundamentals: str
    jobs: list[ScheduledJobOut] = []
    sheets_auto_export: bool = False
    note: str = ""


class JobOut(BaseModel):
    id: int
    kind: str
    status: Literal["queued", "running", "done", "failed", "cancelled"]
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


class PatternInfoOut(BaseModel):
    key: str
    family: str
    family_label: str
    name: str
    kind: Literal["reversal", "continuation", "either"]
    bias: Literal["bullish", "bearish", "neutral"]
    action: Literal["buy", "sell", "wait"]
    verdict: str
    meaning: str
    trade: str
    confirm: str
    fails: str
    target_rule: str
    reliability: Literal["high", "medium", "low"]
    duration: str
    intraday: Literal["good", "ok", "poor"]
    swing: Literal["good", "ok", "poor"]
    positional: Literal["good", "ok", "poor"]


class PatternPointOut(BaseModel):
    t: str
    price: float
    label: str = ""


class PatternLineOut(BaseModel):
    label: str
    kind: Literal["neckline", "trend", "rim", "curve"]
    points: list[PatternPointOut]


class PatternOut(BaseModel):
    key: str
    name: str
    family: str
    direction: Literal["bullish", "bearish", "neutral"]
    status: Literal["forming", "confirmed"]
    confidence: int
    strength: Literal["strong", "moderate", "weak"]
    start: str
    end: str
    bars: int
    breakout: float | None
    target: float | None
    invalidation: float | None
    target_pct: float | None = Field(None, description="Target vs the last close, in percent")
    invalidation_pct: float | None = Field(None, description="Cancel level vs the last close, %")
    bars_since_breakout: int | None
    volume_confirmed: bool | None
    text: str
    points: list[PatternPointOut]
    lines: list[PatternLineOut]


class PatternWindowOut(BaseModel):
    """The bars the patterns span (plus a lead-in), for drawing them."""

    t: list[str]
    open: list[float]
    high: list[float]
    low: list[float]
    close: list[float]


class PatternReportOut(BaseModel):
    ticker: str
    interval: str
    unit: str
    bars: int
    as_of: str | None
    last_close: float | None
    patterns: list[PatternOut]
    window: PatternWindowOut
    notes: list[str]


class PatternHoldingOut(BaseModel):
    ticker: str
    label: str
    interval: str
    as_of: str | None
    bars: int
    patterns: list[PatternOut]


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


class GrowthGuidanceIn(BaseModel):
    growth_pct: float | None = Field(
        None, ge=-100, le=500, description="Yearly profit growth you expect (%); null clears it"
    )


class GrowthGuidanceOut(BaseModel):
    ticker: str
    growth_pct: float | None  # yours, when entered
    analyst_pct: float | None
    analyst_basis: str


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
    quantity: float | None
    avg_price: float | None
    price: float | None
    invested: float | None
    value: float | None
    pnl: float | None
    pnl_pct: float | None
    day_change: float | None  # ₹ since the previous close
    day_change_pct: float | None
    peg: float | None
    peg_basis: str | None
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
    limited: bool = True


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


# --------------------------------------------------------------------------- dashboard (Phase 8)


class RollingSeriesOut(BaseModel):
    years: int
    starts: list[date]
    fund: list[float]
    benchmark: list[float]


class FundChartOut(BaseModel):
    code: str
    benchmark: BenchmarkOut | None
    dates: list[date]
    fund: list[float]
    bench: list[float | None]
    rolling: list[RollingSeriesOut]
    notes: list[str]


class ActionOut(BaseModel):
    severity: Literal["high", "medium", "low"]
    kind: Literal["stock", "fund", "portfolio", "data"]
    subject: str
    title: str
    detail: str
    link: str | None


class ActionsOut(BaseModel):
    style_label: str
    risk_label: str
    actions: list[ActionOut]
    disclaimer: str


# ---------------------------------------------------------------------------- screener


class ScreenFieldOut(BaseModel):
    key: str
    label: str
    group: str
    unit: str
    help: str
    financial_exempt: bool


class ScreenFilterIO(BaseModel):
    field: str
    op: Literal["gt", "gte", "lt", "lte", "between"]
    value: float | list[float]


class PresetOut(BaseModel):
    key: str
    label: str
    description: str
    filters: list[ScreenFilterIO]


class SavedScreenOut(BaseModel):
    id: int
    name: str
    filters: list[ScreenFilterIO]
    updated_at: ISTDatetime


class SavedScreenIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    filters: list[ScreenFilterIO] = Field(min_length=1)


class UniverseOut(BaseModel):
    key: str
    label: str
    size: int | None


class ScanOut(BaseModel):
    id: int
    job_id: int | None
    universe: str
    universe_label: str
    style: StyleKey
    style_label: str
    risk: RiskKey
    risk_label: str
    fetch: Literal["missing", "cached"]
    status: Literal["running", "complete", "partial", "failed"]
    created_at: ISTDatetime
    finished_at: ISTDatetime | None
    total: int
    scored: int
    notes: list[str]


class ScreenerConfigOut(BaseModel):
    universes: list[UniverseOut]
    default_universe: str
    custom_universe_max: int
    seconds_per_stock: float = Field(
        description="Rough first-scan time per stock: Yahoo requests at the rate limit, plus pause"
    )
    presets: list[PresetOut]
    fields: list[ScreenFieldOut]
    ops: dict[str, str]
    screens: list[SavedScreenOut]
    top_n: int
    latest_scan: ScanOut | None
    disclaimer: str


class ScanIn(BaseModel):
    universe: Literal["nifty50", "nifty100", "nifty200", "nifty500", "custom"] | None = None
    symbols: str | None = Field(
        None, description="Custom universe: NSE symbols, comma or newline separated"
    )
    fetch: Literal["missing", "cached"] = "missing"
    style: StyleKey | None = None
    risk: RiskKey | None = None


class ScreenerJobOut(BaseModel):
    job: "JobOut"
    scan: ScanOut | None


class ScreenIn(BaseModel):
    scan_id: int | None = Field(None, description="Default: the latest finished scan")
    preset: str | None = None
    screen_id: int | None = None
    filters: list[ScreenFilterIO] | None = Field(None, description="Ad-hoc filters (the builder)")
    include_held: bool = False
    top_n: int | None = Field(None, ge=1, le=200)


class EntryLevelsOut(BaseModel):
    interval: str
    close: float
    atr: float
    entry_low: float
    entry_high: float
    entry_basis: str
    stop: float
    stop_pct: float
    targets: list[TargetOut]
    basis: str


class SectorImpactOut(BaseModel):
    sector: str | None
    amount: float | None
    quantity: int | None
    before: float | None
    after: float | None
    over_limit: bool
    text: str


class CandidateOut(BaseModel):
    rank: int
    ticker: str
    symbol: str
    label: str
    sector: str | None
    held: bool
    watched: bool
    signal: SignalKey
    signal_label: str
    rule: str
    confidence: Literal["high", "medium", "low"] | None
    composite: float | None
    technical: float | None
    fundamental: float | None
    bullish: list[str]
    bearish: list[str]
    flags: list[FlagOut]
    passed: list[str]
    levels: EntryLevelsOut | None
    impact: SectorImpactOut
    facts: dict[str, float | None]
    price_as_of: str | None


class NearMissOut(BaseModel):
    ticker: str
    label: str
    composite: float | None
    failed: list[str]


class ScreenResultOut(BaseModel):
    scan: ScanOut
    title: str
    filters: list[str]
    prefilters: list[str]
    counts: dict[str, int]
    candidates: list[CandidateOut]
    near_misses: list[NearMissOut]
    stale_note: str | None
    disclaimer: str


class WatchIn(BaseModel):
    ticker: str = Field(min_length=1, max_length=30)
    note: str | None = Field(None, max_length=500)
    source: str | None = Field(None, max_length=120)


class WatchNoteIn(BaseModel):
    note: str | None = Field(None, max_length=500)


class SignalChangeOut(BaseModel):
    previous: SignalKey
    previous_label: str
    current: SignalKey
    current_label: str
    day: date


class WatchItemOut(BaseModel):
    ticker: str
    label: str
    note: str | None
    source: str | None
    added_at: ISTDatetime
    added_price: float | None
    added_signal: SignalKey | None
    added_signal_label: str | None
    added_score: float | None
    held: bool
    status: Literal["ok", "no_data"]
    signal: SignalKey | None
    signal_label: str | None
    rule: str | None
    confidence: Literal["high", "medium", "low"] | None
    composite: float | None
    score_change: float | None
    price: float | None
    price_as_of: str | None
    price_change_pct: float | None
    signal_changed_since_added: bool
    last_change: SignalChangeOut | None
    stop: float | None
    stop_breached: bool
    bullish: list[str]
    bearish: list[str]
    flags: list[FlagOut]
    sector: str | None
    price_freshness: FreshnessOut | None
    # Score Shape (added with the redesign; None when the stock has no prices yet)
    axes: dict[str, int | None] | None = None
    shape_total: int | None = None
    shape_max: int | None = None
    shape_step: int | None = None
    week_change: "WeekChangeOut | None" = None


class WatchlistOut(BaseModel):
    style_label: str
    risk_label: str
    items: list[WatchItemOut]
    fetching_job_id: int | None
    disclaimer: str


# ---------------------------------------------------------------------------- Google Sheets


class ServiceAccountOut(BaseModel):
    """Never includes the private key: only where the file is and which robot e-mail it is."""

    configured: bool
    path: str
    client_email: str | None
    project_id: str | None
    error: str | None


class SheetSyncOut(BaseModel):
    at: ISTDatetime
    direction: Literal["export", "import", "test"]
    detail: str | None
    ok: bool
    message: str


class SheetSettingsOut(BaseModel):
    stocks_tab: str
    mf_tab: str
    stocks_csv_url: str | None
    mf_csv_url: str | None
    screener_screen: str | None
    auto_export: bool


class SheetsStatusOut(BaseModel):
    service_account: ServiceAccountOut
    sheet_url: str | None
    spreadsheet_url: str | None  # normalised …/edit link, when the saved link is usable
    link_error: str | None
    settings: SheetSettingsOut
    export_tabs: dict[str, str]
    default_import_tabs: dict[str, str]
    history: list[SheetSyncOut]
    refresh_time_ist: str  # when the scheduled refresh (and auto-export) runs


class SheetSettingsIn(BaseModel):
    sheet_url: str | None = Field(None, max_length=500)
    stocks_tab: str | None = Field(None, max_length=100)
    mf_tab: str | None = Field(None, max_length=100)
    stocks_csv_url: str | None = Field(None, max_length=500)
    mf_csv_url: str | None = Field(None, max_length=500)
    screener_screen: str | None = Field(None, pattern=r"^(preset:[a-z0-9_]+|saved:\d+)$")
    auto_export: bool = False


class SheetCheckOut(BaseModel):
    name: str
    ok: bool | None
    detail: str


class SheetTestOut(BaseModel):
    ok: bool
    checks: list[SheetCheckOut]


class SheetExportIn(BaseModel):
    overwrite: list[str] = Field(default_factory=list, max_length=10)


class SheetTabOut(BaseModel):
    name: str
    rows: int


class SheetExportOut(BaseModel):
    url: str
    title: str
    tabs: list[SheetTabOut]
    at: ISTDatetime


class SheetImportIn(BaseModel):
    kind: Literal["stocks", "mf"]
    source: Literal["tab", "csv"]
    tab: str | None = Field(None, max_length=100, description="Default: the saved import tab")
    url: str | None = Field(None, max_length=500, description="Default: the saved CSV link")
    mapping: ColumnMappingIn | None = None


# ---------------------------------------------------------------------------- Score Shape


CheckStatus = Literal["pass", "fail", "no_data"]


class CheckOut(BaseModel):
    section: str
    check_id: str
    label: str
    status: CheckStatus
    value: float | None
    threshold: float | None
    unit: str
    display_value: str
    display_threshold: str
    explanation: str
    help: str | None
    highlight: list[str]


class SectionOut(BaseModel):
    key: str
    label: str
    question: str
    caption: str | None
    checks: list[CheckOut]
    passed: int
    with_data: int
    score: int | None = Field(description="0 … axis_max; null = not enough data")
    note: str | None


class ShapeOut(BaseModel):
    sections: list[SectionOut]
    axes: dict[str, int | None]
    total: int
    max_total: int
    axis_max: int
    step: int | None = Field(description="Colour step 1 (weak) … 5 (strong)")
    checks_total: int
    checks_with_data: int
    confidence: Literal["high", "medium", "low"]
    confidence_reason: str
    rewards: list[str]
    risks: list[str]
    summary: str


class FairValueMethodOut(BaseModel):
    name: str
    value: float
    basis: str


class FairValueOut(BaseModel):
    label: Literal["Estimate"] = "Estimate"
    value: float
    price: float
    gap_pct: float = Field(description="Price vs fair value: negative = below (cheaper)")
    methods: list[FairValueMethodOut]
    caveat: str


class YearPEOut(BaseModel):
    fy: str
    year_end: date
    price: float
    pe: float


class WeekChangeOut(BaseModel):
    since: date
    axes: dict[str, int | None]
    total: int
    previous_signal: SignalKey | None
    previous_signal_label: str | None
    signal_changed: bool


class StockChecksOut(ShapeOut):
    ticker: str
    label: str
    sector: str | None
    is_financial: bool
    style: StyleKey
    style_label: str
    risk: RiskKey
    risk_label: str
    signal: SignalKey
    signal_label: str
    fair_value: FairValueOut | None
    pe_history: list[YearPEOut]
    week_change: WeekChangeOut | None
    disclaimer: str


class HoldingShapeOut(BaseModel):
    ticker: str
    label: str
    sector: str | None
    value: float | None
    weight: float | None
    signal: SignalKey
    signal_label: str
    axes: dict[str, int | None]
    total: int
    max_total: int
    step: int | None
    confidence: Literal["high", "medium", "low"]
    top: list[str] = Field(description="Strongest and weakest section, one line each")


class AxisAverageOut(BaseModel):
    key: str
    label: str
    score: float | None
    coverage: float


class PortfolioShapeOut(BaseModel):
    axes: list[AxisAverageOut]
    total: float
    max_total: int
    axis_max: int
    step: int | None
    stock_value: float
    holdings: int


class HoldingsChecksOut(BaseModel):
    style: StyleKey
    style_label: str
    risk: RiskKey
    risk_label: str
    portfolio: PortfolioShapeOut
    holdings: list[HoldingShapeOut]
    rewards: list[str]
    risks: list[str]
    notes: list[str]
    disclaimer: str


class FundChecksOut(ShapeOut):
    code: str
    name: str
    category: str | None
    signal: FundSignalKey
    signal_label: str
    disclaimer: str


class FundHoldingsChecksOut(BaseModel):
    funds: list[FundChecksOut]
    disclaimer: str


class AxisDefOut(BaseModel):
    key: str
    label: str
    question: str
    caption: str | None


class ChecksConfigOut(BaseModel):
    axis_max: int
    score_steps: list[float]
    stock: list[AxisDefOut]
    fund: list[AxisDefOut]


class FinancialYearOut(BaseModel):
    fy: str
    year_end: date
    revenue: float | None
    net_income: float | None
    op_margin: float | None
    net_margin: float | None
    roe: float | None
    total_debt: float | None
    equity: float | None
    cash: float | None
    debt_equity: float | None
    fcf: float | None
    dividends_paid: float | None
    payout_pct: float | None
    pe: float | None
    price: float | None


class FinancialQuarterOut(BaseModel):
    label: str
    period_end: date
    revenue: float | None
    net_income: float | None


class FinancialHistoryOut(BaseModel):
    ticker: str
    label: str
    sector: str | None
    is_financial: bool
    source: str | None
    unit: str = Field("₹ Cr", description='"₹ Cr", or e.g. "USD Cr" for statements in USD')
    years: list[FinancialYearOut]
    quarters: list[FinancialQuarterOut]
    fair_value: FairValueOut | None
    notes: list[str]
    disclaimer: str


WatchItemOut.model_rebuild()
