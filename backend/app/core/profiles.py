"""Load and validate config/profiles.yaml. A malformed file fails fast with a readable error."""

import logging
from datetime import time
from pathlib import Path
from typing import Any, Literal, get_args

import yaml
from pydantic import BaseModel, Field, ValidationError, model_validator

from app.core.settings import get_settings

logger = logging.getLogger(__name__)

StyleKey = Literal["intraday", "swing", "positional", "long_term", "custom"]
RiskKey = Literal["low", "medium", "high"]
STYLE_KEYS: tuple[StyleKey, ...] = ("intraday", "swing", "positional", "long_term", "custom")
RISK_KEYS: tuple[RiskKey, ...] = ("low", "medium", "high")


class Style(BaseModel):
    label: str
    horizon: str
    timeframes: list[str]
    technical_weight: float = Field(ge=0, le=1)
    fundamental_weight: float = Field(ge=0, le=1)
    stop_breach_exits: bool = True
    note: str | None = None

    @model_validator(mode="after")
    def weights_sum_to_one(self) -> "Style":
        if abs(self.technical_weight + self.fundamental_weight - 1.0) > 1e-6:
            raise ValueError("technical_weight + fundamental_weight must equal 1.0")
        return self


class RiskLevel(BaseModel):
    label: str
    max_weight_per_stock: float = Field(gt=0, le=1)
    max_weight_per_sector: float = Field(gt=0, le=1)
    stop_loss_atr_multiple: float = Field(gt=0)
    min_market_cap_cr: float = Field(ge=0)
    max_debt_to_equity: float | None
    max_beta: float | None
    buy_threshold: float = Field(ge=0, le=100)


class SevereFlags(BaseModel):
    max_pledge_pct: float
    consecutive_loss_years: int


class SignalRules(BaseModel):
    strong_buy_margin: float
    hold_floor: float
    reduce_floor: float
    severe_flags: SevereFlags
    stop_loss_lookback_bars: int = Field(ge=1)
    target_r_multiples: list[float] = Field(min_length=1)

    @model_validator(mode="after")
    def bands_ordered(self) -> "SignalRules":
        if not self.reduce_floor < self.hold_floor:
            raise ValueError("reduce_floor must be below hold_floor")
        if any(r <= 0 for r in self.target_r_multiples):
            raise ValueError("signals.target_r_multiples must be positive")
        return self


ConfidenceLevel = Literal["high", "medium", "low"]


class Confidence(BaseModel):
    high_min_coverage: float = Field(ge=0, le=1)
    medium_min_coverage: float = Field(ge=0, le=1)
    stale_caps_at: Literal["medium", "low"]

    @model_validator(mode="after")
    def ordered(self) -> "Confidence":
        if self.medium_min_coverage > self.high_min_coverage:
            raise ValueError("confidence.medium_min_coverage must not exceed high_min_coverage")
        return self


TechCategory = Literal[
    "trend", "momentum", "volatility", "volume", "structure", "relative_strength", "pattern"
]
FundCategory = Literal["valuation", "profitability", "growth", "health", "quality", "ownership"]


class ScoringConfig(BaseModel):
    technical_weights: dict[TechCategory, float]
    fundamental_weights: dict[FundCategory, float]
    financial_exempt: list[FundCategory]
    primary_timeframe_weight: float = Field(gt=0, le=1)
    minor_weight: float = Field(ge=0)
    neutral_weight: float = Field(ge=0)
    info_only: list[str]
    reading_weights: dict[str, float]
    beta_lookback_sessions: int = Field(gt=10)
    beta_min_sessions: int = Field(gt=10)

    @model_validator(mode="after")
    def weights_valid(self) -> "ScoringConfig":
        for name, have, keys in (
            ("technical_weights", self.technical_weights, get_args(TechCategory)),
            ("fundamental_weights", self.fundamental_weights, get_args(FundCategory)),
        ):
            if missing := set(keys) - set(have):
                raise ValueError(f"scoring.{name} is missing {sorted(missing)}")
            if any(v < 0 for v in have.values()) or sum(have.values()) <= 0:
                raise ValueError(f"scoring.{name} must be non-negative and not all zero")
        if any(v < 0 for v in self.reading_weights.values()):
            raise ValueError("scoring.reading_weights must be non-negative")
        if self.beta_min_sessions > self.beta_lookback_sessions:
            raise ValueError("scoring.beta_min_sessions must not exceed beta_lookback_sessions")
        return self


class RebalanceConfig(BaseModel):
    weight_base: Literal["portfolio", "stocks"]
    strong_buy_target: float = Field(gt=0, le=1)
    buy_target: float = Field(gt=0, le=1)
    reduce_keep: float = Field(ge=0, lt=1)
    min_trade_value_inr: float = Field(ge=0)


class MFBenchmark(BaseModel):
    match: list[str] = Field(min_length=1)
    ticker: str
    label: str


class MFSignalRules(BaseModel):
    review_rolling_excess_pp: float
    switch_rolling_excess_pp: float
    switch_max_beat_share: float = Field(ge=0, le=1)
    review_1y_excess_pp: float
    regular_plan_switch: bool

    @model_validator(mode="after")
    def ordered(self) -> "MFSignalRules":
        if self.switch_rolling_excess_pp > self.review_rolling_excess_pp:
            raise ValueError(
                "mf.signals.switch_rolling_excess_pp must not exceed review_rolling_excess_pp"
            )
        return self


AssetClass = Literal["equity", "debt", "hybrid", "other"]


class MFConfig(BaseModel):
    risk_free_rate_pct: float = Field(ge=0, lt=50)
    risk_stats_years: int = Field(ge=1)
    min_history_days: int = Field(ge=30)
    rolling_windows_years: list[int] = Field(min_length=1)
    rolling_step_days: int = Field(ge=1)
    benchmarks: list[MFBenchmark]
    asset_classes: dict[Literal["debt", "hybrid", "other"], list[str]]
    overlap_high_pct: float = Field(gt=0, le=100)
    overlap_min_coverage_pct: float = Field(gt=0, le=100)
    portfolio_max_age_days: int = Field(gt=0)
    duplicate_category_max: int = Field(ge=1)
    expense_ratio_high_pct: dict[Literal["equity", "debt", "other"], float]
    signals: MFSignalRules

    @model_validator(mode="after")
    def windows_valid(self) -> "MFConfig":
        if any(y <= 0 for y in self.rolling_windows_years):
            raise ValueError("mf.rolling_windows_years must be positive")
        return self


class PortfolioConfig(BaseModel):
    large_cap_min_cr: float = Field(gt=0)
    mid_cap_min_cr: float = Field(gt=0)
    correlation_top_n: int = Field(ge=2)
    correlation_lookback_sessions: int = Field(gt=20)
    performance_min_days: int = Field(ge=1)
    performance_fallback_days: int = Field(ge=30)
    xirr_min_coverage: float = Field(ge=0, le=1)
    top_n_concentration: int = Field(ge=1)

    @model_validator(mode="after")
    def caps_ordered(self) -> "PortfolioConfig":
        if self.mid_cap_min_cr >= self.large_cap_min_cr:
            raise ValueError("portfolio.mid_cap_min_cr must be below large_cap_min_cr")
        return self


class ScreenerConfig(BaseModel):
    default_universe: str
    min_avg_daily_traded_value_cr: float
    top_n: int = Field(gt=0)
    request_delay_seconds: float = Field(ge=0)


_HHMM = r"^([01]\d|2[0-3]):[0-5]\d$"
SourceKey = Literal["yahoo", "mfapi", "nse", "amfi"]
ReferenceKey = Literal["nse_equity", "nse_etf", "nifty500", "amfi_navall"]


def parse_hhmm(value: str) -> time:
    h, m = value.split(":")
    return time(int(h), int(m))


class DataConfig(BaseModel):
    price_history_years: int = Field(gt=0)
    market_open_ist: str = Field(pattern=_HHMM)
    market_close_ist: str = Field(pattern=_HHMM)
    refresh_time_ist: str = Field(pattern=_HHMM)
    nav_refresh_time_ist: str = Field(pattern=_HHMM)
    refresh_on_startup: bool
    stale_after_hours: float = Field(gt=0)
    max_missing_sessions: int = Field(ge=0)
    reference_refresh_days: float = Field(gt=0)
    intraday_stale_after_minutes: float = Field(gt=0)
    intraday_max_days: dict[Literal["15m", "1h"], int]
    incremental_overlap_days: int = Field(ge=1)
    split_check_tolerance: float = Field(gt=0, lt=1)
    fundamentals_stale_after_days: float = Field(gt=0)
    http_timeout_seconds: float = Field(gt=0)
    http_retries: int = Field(ge=0)
    http_backoff_seconds: float = Field(ge=0)
    rate_limits_per_minute: dict[SourceKey, float]
    reference_min_rows: dict[ReferenceKey, int]
    benchmarks: dict[str, str]

    @model_validator(mode="after")
    def complete(self) -> "DataConfig":
        for name, keys, have in (
            ("rate_limits_per_minute", get_args(SourceKey), self.rate_limits_per_minute),
            ("reference_min_rows", get_args(ReferenceKey), self.reference_min_rows),
            ("intraday_max_days", ("15m", "1h"), self.intraday_max_days),
        ):
            if missing := set(keys) - set(have):
                raise ValueError(f"data.{name} is missing {sorted(missing)}")
        if any(v <= 0 for v in self.rate_limits_per_minute.values()):
            raise ValueError("data.rate_limits_per_minute values must be positive")
        if parse_hhmm(self.refresh_time_ist) < parse_hhmm(self.market_close_ist):
            raise ValueError("data.refresh_time_ist must be after market_close_ist")
        return self

    @property
    def price_ready(self) -> time:
        return parse_hhmm(self.refresh_time_ist)

    @property
    def nav_ready(self) -> time:
        return parse_hhmm(self.nav_refresh_time_ist)


class SupertrendPeriods(BaseModel):
    period: int = Field(gt=1)
    multiplier: float = Field(gt=0)


class MacdPeriods(BaseModel):
    fast: int = Field(gt=1)
    slow: int = Field(gt=1)
    signal: int = Field(gt=1)

    @model_validator(mode="after")
    def fast_below_slow(self) -> "MacdPeriods":
        if self.fast >= self.slow:
            raise ValueError("macd.fast must be below macd.slow")
        return self


class StochasticPeriods(BaseModel):
    k: int = Field(gt=1)
    smooth: int = Field(ge=1)
    d: int = Field(ge=1)


class BollingerPeriods(BaseModel):
    period: int = Field(gt=1)
    std: float = Field(gt=0)


class TechnicalPeriods(BaseModel):
    sma: list[int] = Field(min_length=1)
    ema: list[int] = Field(min_length=2, max_length=2)
    adx: int = Field(gt=1)
    supertrend: SupertrendPeriods
    rsi: int = Field(gt=1)
    macd: MacdPeriods
    stochastic: StochasticPeriods
    roc: int = Field(gt=0)
    bollinger: BollingerPeriods
    atr: int = Field(gt=1)
    hist_vol: int = Field(gt=1)
    volume_avg: int = Field(gt=1)
    obv_trend: int = Field(gt=2)
    high_low_sessions: int = Field(gt=1)
    relative_strength: dict[str, int]
    delivery_avg: int = Field(gt=1)

    @model_validator(mode="after")
    def sma_has_trend_pair(self) -> "TechnicalPeriods":
        if not {50, 200} <= set(self.sma):
            raise ValueError("technical.periods.sma must include 50 and 200 (golden/death cross)")
        if self.ema[0] >= self.ema[1]:
            raise ValueError("technical.periods.ema must be [fast, slow]")
        return self


class TechnicalThresholds(BaseModel):
    rsi_overbought: float = Field(gt=0, lt=100)
    rsi_oversold: float = Field(gt=0, lt=100)
    rsi_neutral_band: tuple[float, float]
    stoch_overbought: float = Field(gt=0, lt=100)
    stoch_oversold: float = Field(gt=0, lt=100)
    adx_trending: float = Field(gt=0)
    adx_weak: float = Field(gt=0)
    cross_lookback_bars: int = Field(ge=1)
    volume_surge: float = Field(gt=1)
    near_52w_pct: float = Field(gt=0)
    squeeze_lookback_bars: int = Field(gt=1)
    delivery_surge: float = Field(gt=1)
    obv_slope_min: float = Field(ge=0)
    candle_doji_body: float = Field(gt=0, lt=1)
    candle_hammer_shadow: float = Field(gt=0)

    @model_validator(mode="after")
    def ordered(self) -> "TechnicalThresholds":
        lo, hi = self.rsi_neutral_band
        if not self.rsi_oversold < lo <= hi < self.rsi_overbought:
            raise ValueError("need rsi_oversold < rsi_neutral_band < rsi_overbought")
        if not self.stoch_oversold < self.stoch_overbought:
            raise ValueError("stoch_oversold must be below stoch_overbought")
        if not self.adx_weak <= self.adx_trending:
            raise ValueError("adx_weak must not exceed adx_trending")
        return self


class SupportResistance(BaseModel):
    lookback_bars: int = Field(gt=10)
    pivot_window: int = Field(ge=1)
    cluster_pct: float = Field(gt=0)
    min_touches: int = Field(ge=1)
    breakout_buffer_pct: float = Field(ge=0)
    breakout_window_bars: int = Field(ge=1)


class TechnicalConfig(BaseModel):
    periods: TechnicalPeriods
    thresholds: TechnicalThresholds
    support_resistance: SupportResistance
    delivery_lookback_sessions: int = Field(gt=0)

    @model_validator(mode="after")
    def enough_delivery_history(self) -> "TechnicalConfig":
        if self.delivery_lookback_sessions < self.periods.delivery_avg + 1:
            raise ValueError(
                "technical.delivery_lookback_sessions must be at least periods.delivery_avg + 1"
            )
        return self


class FundamentalThresholds(BaseModel):
    valuation_cheap_ratio: float = Field(gt=0)
    valuation_rich_ratio: float = Field(gt=0)
    peg_cheap: float = Field(gt=0)
    peg_rich: float = Field(gt=0)
    roe_good: float
    roe_poor: float
    roce_good: float
    roce_poor: float
    margin_trend_flat_pp: float = Field(ge=0)
    growth_good: float
    growth_poor: float
    quarter_yoy_good: float
    quarter_yoy_poor: float
    debt_equity_low: float = Field(ge=0)
    interest_coverage_good: float
    interest_coverage_poor: float
    current_ratio_good: float
    current_ratio_poor: float
    dividend_yield_high: float = Field(ge=0)
    fscore_strong: int = Field(ge=0, le=9)
    fscore_weak: int = Field(ge=0, le=9)
    promoter_change_pp: float = Field(gt=0)
    pledge_warn_pct: float = Field(ge=0, le=100)
    institution_change_pp: float = Field(gt=0)

    @model_validator(mode="after")
    def ordered(self) -> "FundamentalThresholds":
        pairs = [
            ("valuation_cheap_ratio", "valuation_rich_ratio"),
            ("peg_cheap", "peg_rich"),
            ("roe_poor", "roe_good"),
            ("roce_poor", "roce_good"),
            ("growth_poor", "growth_good"),
            ("quarter_yoy_poor", "quarter_yoy_good"),
            ("interest_coverage_poor", "interest_coverage_good"),
            ("current_ratio_poor", "current_ratio_good"),
            ("fscore_weak", "fscore_strong"),
        ]
        for lo, hi in pairs:
            if getattr(self, lo) >= getattr(self, hi):
                raise ValueError(f"fundamental.thresholds.{lo} must be below {hi}")
        return self


class FundamentalConfig(BaseModel):
    financial_sectors: list[str]
    sector_min_peers: int = Field(ge=1)
    sector_max_peers: int = Field(ge=1)
    refresh_day: Literal["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
    refresh_time_ist: str = Field(pattern=_HHMM)
    screener_max_age_days: int = Field(gt=0)
    cross_check_tolerance: float = Field(gt=0)
    thresholds: FundamentalThresholds


class ImportConfig(BaseModel):
    header_scan_rows: int = Field(gt=0)
    column_match_min_score: float = Field(ge=0, le=100)
    min_header_matches: int = Field(ge=1)
    ticker_name_auto_accept: float = Field(ge=0, le=100)
    ticker_name_suggest: float = Field(ge=0, le=100)
    scheme_name_auto_accept: float = Field(ge=0, le=100)
    scheme_name_suggest: float = Field(ge=0, le=100)
    max_suggestions: int = Field(gt=0)
    max_upload_mb: float = Field(gt=0)


class TaxConfig(BaseModel):
    verify_note: str
    equity_ltcg_min_holding_days: int
    equity_stcg_rate: float
    equity_ltcg_rate: float
    equity_ltcg_exemption_inr: float


class Defaults(BaseModel):
    style: StyleKey | None = None
    risk: RiskKey = "medium"


class Profiles(BaseModel):
    version: int
    defaults: Defaults
    styles: dict[StyleKey, Style]
    risk_levels: dict[RiskKey, RiskLevel]
    signals: SignalRules
    confidence: Confidence
    scoring: ScoringConfig
    rebalance: RebalanceConfig
    mf: MFConfig
    portfolio: PortfolioConfig
    screener: ScreenerConfig
    data: DataConfig
    technical: TechnicalConfig
    fundamental: FundamentalConfig
    importing: ImportConfig
    tax: TaxConfig
    disclaimer: str

    @model_validator(mode="after")
    def all_keys_present(self) -> "Profiles":
        missing_styles = set(STYLE_KEYS) - set(self.styles)
        missing_risks = set(RISK_KEYS) - set(self.risk_levels)
        if missing_styles or missing_risks:
            raise ValueError(
                f"missing styles {sorted(missing_styles)} / risk levels {sorted(missing_risks)}"
            )
        if "nifty50" not in self.data.benchmarks:
            raise ValueError("data.benchmarks must include nifty50 (used for relative strength)")
        for risk in self.risk_levels.values():
            if risk.buy_threshold + self.signals.strong_buy_margin > 100:
                raise ValueError("buy_threshold + strong_buy_margin exceeds 100")
            if risk.buy_threshold <= self.signals.hold_floor:
                raise ValueError("buy_threshold must be above signals.hold_floor")
        return self


class ConfigError(RuntimeError):
    pass


def deep_merge(base: dict[str, Any], over: dict[str, Any]) -> dict[str, Any]:
    out = dict(base)
    for k, v in over.items():
        out[k] = (
            deep_merge(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else v
        )
    return out


def read_yaml(path: Path) -> dict[str, Any]:
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except FileNotFoundError as e:
        raise ConfigError(f"Config file not found: {path}") from e
    except yaml.YAMLError as e:
        raise ConfigError(f"Config file {path} is not valid YAML: {e}") from e
    if not isinstance(raw, dict):
        raise ConfigError(f"Config file {path} must be a mapping")
    return raw


def load_profiles(path: Path, override: Path | None = None) -> Profiles:
    raw = read_yaml(path)
    if override is not None and override.exists():
        raw = deep_merge(raw, read_yaml(override))
    try:
        return Profiles.model_validate(raw)
    except ValidationError as e:
        where = f"{path} + {override}" if override is not None and override.exists() else path
        raise ConfigError(f"Config file {where} failed validation:\n{e}") from e


_profiles: Profiles | None = None


def get_profiles() -> Profiles:
    global _profiles
    if _profiles is None:
        _profiles = load_profiles(
            get_settings().profiles_path, get_settings().profiles_override_path
        )
        logger.info("Loaded config from %s", get_settings().profiles_path)
    return _profiles


def reload_profiles() -> Profiles:
    global _profiles
    _profiles = None
    return get_profiles()
