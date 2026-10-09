"""Load and validate config/profiles.yaml. A malformed file fails fast with a readable error."""

import logging
from pathlib import Path
from typing import Literal

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

    @model_validator(mode="after")
    def bands_ordered(self) -> "SignalRules":
        if not self.reduce_floor < self.hold_floor:
            raise ValueError("reduce_floor must be below hold_floor")
        return self


class Confidence(BaseModel):
    high_min_coverage: float = Field(ge=0, le=1)
    medium_min_coverage: float = Field(ge=0, le=1)


class ScreenerConfig(BaseModel):
    default_universe: str
    min_avg_daily_traded_value_cr: float
    top_n: int = Field(gt=0)
    request_delay_seconds: float = Field(ge=0)


class DataConfig(BaseModel):
    price_history_years: int = Field(gt=0)
    stale_after_hours: float = Field(gt=0)
    fundamentals_stale_after_days: float = Field(gt=0)
    max_requests_per_minute: int = Field(gt=0)
    refresh_time_ist: str = Field(pattern=r"^\d{2}:\d{2}$")


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
    screener: ScreenerConfig
    data: DataConfig
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
        for risk in self.risk_levels.values():
            if risk.buy_threshold + self.signals.strong_buy_margin > 100:
                raise ValueError("buy_threshold + strong_buy_margin exceeds 100")
            if risk.buy_threshold <= self.signals.hold_floor:
                raise ValueError("buy_threshold must be above signals.hold_floor")
        return self


class ConfigError(RuntimeError):
    pass


def load_profiles(path: Path) -> Profiles:
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except FileNotFoundError as e:
        raise ConfigError(f"Config file not found: {path}") from e
    except yaml.YAMLError as e:
        raise ConfigError(f"Config file {path} is not valid YAML: {e}") from e
    try:
        return Profiles.model_validate(raw)
    except ValidationError as e:
        raise ConfigError(f"Config file {path} failed validation:\n{e}") from e


_profiles: Profiles | None = None


def get_profiles() -> Profiles:
    global _profiles
    if _profiles is None:
        _profiles = load_profiles(get_settings().profiles_path)
        logger.info("Loaded config from %s", get_settings().profiles_path)
    return _profiles


def reload_profiles() -> Profiles:
    global _profiles
    _profiles = None
    return get_profiles()
