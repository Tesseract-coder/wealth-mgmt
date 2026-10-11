"""Score Shape: pass/fail checks per section (config/checks.yaml), turned into 0–6 axis scores.

A plain-English layer over data the engines already produce. It never changes the composite
score, signals or thresholds: profiles.yaml thresholds are referenced, not copied.

Axis score = passed ÷ checks with data × axis.max, halves up. Checks with no data are left out (they
lower the confidence label instead), and so are checks that don't apply (lenders skip debt/equity
…). With fewer than axis.min_applicable checks that have data, the axis has no score.
"""

import json
import logging
import math
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

import pandas as pd
import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator
from sqlmodel import Session, col, select

from app.analysis.check_rules import (
    FUND_RULES,
    STOCK_RULES,
    FundContext,
    Limits,
    MissingThreshold,
    Outcome,
    Status,
    StockContext,
    cr,
)
from app.analysis.mf import FundReport
from app.analysis.technical import analyse_frame
from app.analysis.valuation import FairValue, YearPE, describe, fair_value, pe_history
from app.core.formatting import format_inr, now_ist
from app.core.profiles import ConfigError, Profiles, RiskKey, RiskLevel, get_profiles
from app.core.settings import get_settings
from app.models.tables import AxisRecord, SignalRecord, utcnow

if TYPE_CHECKING:
    from app.analysis.signals import StockSignal

logger = logging.getLogger(__name__)

Kind = Literal["stock", "fund"]
Applies = Literal["all", "non_financial", "financial"]
Highlight = Literal["reward", "risk"]
Unit = Literal["x", "pct", "pp", "inr", "inr_cr", "count", "number", "text"]

# ---------------------------------------------------------------------------- config


class Ref(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ref: str


Threshold = float | Ref | None


class CheckDef(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    id: str
    label: str
    unit: Unit
    threshold: Threshold = None
    upper: Threshold = None
    ratio: Threshold = None
    applies: Applies = "all"
    highlight: list[Highlight] = Field(default_factory=list)
    help: str | None = None
    pass_text: str = Field(alias="pass")
    fail_text: str = Field(alias="fail")


class SectionDef(BaseModel):
    model_config = ConfigDict(extra="forbid")
    label: str
    question: str
    caption: str | None = None
    checks: list[CheckDef] = Field(min_length=1)


class AxisConfig(BaseModel):
    max: int = Field(ge=1)
    min_applicable: dict[Kind, int]
    score_steps: list[float] = Field(min_length=4, max_length=4)

    @model_validator(mode="after")
    def ascending(self) -> "AxisConfig":
        if self.score_steps != sorted(self.score_steps) or not all(
            0 < s < 1 for s in self.score_steps
        ):
            raise ValueError("axis.score_steps must be 4 ascending fractions between 0 and 1")
        return self


class ChecksConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: int
    axis: AxisConfig
    stock: dict[str, SectionDef]
    fund: dict[str, SectionDef]

    @model_validator(mode="after")
    def rules_match(self) -> "ChecksConfig":
        for kind, sections, rules in (
            ("stock", self.stock, STOCK_RULES),
            ("fund", self.fund, FUND_RULES),
        ):
            ids = [c.id for s in sections.values() for c in s.checks]
            if dupes := {i for i in ids if ids.count(i) > 1}:
                raise ValueError(f"{kind}: duplicate check ids {sorted(dupes)}")
            if unknown := set(ids) - set(rules):
                raise ValueError(f"{kind}: no rule for check ids {sorted(unknown)}")
            if missing := set(rules) - set(ids):
                raise ValueError(f"{kind}: rules not used by any check {sorted(missing)}")
            for key, s in sections.items():
                for company in ("non_financial", "financial"):
                    n = sum(c.applies in ("all", company) for c in s.checks)
                    if n > self.axis.max:
                        raise ValueError(
                            f"{kind}.{key}: {n} checks apply to {company} companies; "
                            f"at most axis.max ({self.axis.max})"
                        )
        return self


def resolve(spec: Threshold, p: Profiles, risk: RiskLevel) -> float | None:
    """A number, or the value at a profiles.yaml path ("risk." = your risk level)."""
    if spec is None or isinstance(spec, float | int):
        return None if spec is None else float(spec)
    parts = spec.ref.split(".")
    node: Any = risk if parts[0] == "risk" else p
    for part in parts[1:] if parts[0] == "risk" else parts:
        if isinstance(node, BaseModel):
            node = getattr(node, part)
        elif isinstance(node, dict):
            node = node[part]
        elif isinstance(node, list | tuple):
            node = node[int(part)]
        else:
            raise KeyError(part)
    return None if node is None else float(node)


def _check_refs(cfg: ChecksConfig, p: Profiles) -> None:
    for kind, sections in (("stock", cfg.stock), ("fund", cfg.fund)):
        for c in (c for s in sections.values() for c in s.checks):
            for name in ("threshold", "upper", "ratio"):
                spec = getattr(c, name)
                for risk in p.risk_levels.values():
                    try:
                        resolve(spec, p, risk)
                    except (AttributeError, KeyError, IndexError, ValueError, TypeError) as e:
                        raise ConfigError(
                            f"checks.yaml {kind} check '{c.id}': {name} ref "
                            f"'{spec.ref if isinstance(spec, Ref) else spec}' doesn't resolve "
                            f"in profiles.yaml ({e})"
                        ) from e


def load_checks(path: Path, profiles: Profiles) -> ChecksConfig:
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except FileNotFoundError as e:
        raise ConfigError(f"Checks file not found: {path}") from e
    except yaml.YAMLError as e:
        raise ConfigError(f"Checks file {path} is not valid YAML: {e}") from e
    try:
        cfg = ChecksConfig.model_validate(raw)
    except ValidationError as e:
        raise ConfigError(f"Checks file {path} failed validation:\n{e}") from e
    _check_refs(cfg, profiles)
    return cfg


_checks: ChecksConfig | None = None


def get_checks() -> ChecksConfig:
    global _checks
    if _checks is None:
        _checks = load_checks(get_settings().checks_path, get_profiles())
        logger.info("Loaded checks from %s", get_settings().checks_path)
    return _checks


def reload_checks() -> ChecksConfig:
    global _checks
    _checks = None
    return get_checks()


# ---------------------------------------------------------------------------- results


@dataclass(frozen=True)
class CheckResult:
    section: str
    check_id: str
    label: str
    status: Status
    value: float | None
    threshold: float | None
    unit: str
    display_value: str
    display_threshold: str
    explanation: str
    help: str | None
    highlight: list[str]


@dataclass(frozen=True)
class SectionResult:
    key: str
    label: str
    question: str
    caption: str | None
    checks: list[CheckResult]
    passed: int
    with_data: int
    score: int | None  # 0 … axis.max, None = not enough data
    note: str | None  # "No dividend", "Not enough data" …

    @property
    def failed(self) -> int:
        return self.with_data - self.passed


@dataclass(frozen=True)
class ShapeResult:
    kind: Kind
    sections: list[SectionResult]
    total: int
    max_total: int  # axis.max × axes that have a score
    axis_max: int
    step: int | None  # colour step 1 (weak) … 5 (strong)
    checks_total: int
    checks_with_data: int
    confidence: Literal["high", "medium", "low"]
    confidence_reason: str
    rewards: list[str]
    risks: list[str]
    summary: str
    fair_value: FairValue | None = None
    pe_history: list[YearPE] = field(default_factory=list)

    @property
    def axes(self) -> dict[str, int | None]:
        return {s.key: s.score for s in self.sections}


def fmt(v: float | None, unit: str, signed: bool = True, currency: str = "INR") -> str:
    """A check's value with its unit. `signed=False` drops the "+" (for "fell 4.5 pp")."""
    if v is None:
        return "—"
    if unit == "x":
        out = f"{v:.2f}×" if abs(v) < 10 else f"{v:.1f}×"
    elif unit == "pct":
        out = f"{v:.1f}%"
    elif unit == "pp":
        sign = ("+" if signed else "") if v > 0 else "−" if v < 0 else ""
        return f"{sign}{abs(v):.1f} pp"
    elif unit == "inr":
        out = format_inr(v)
    elif unit == "inr_cr":
        out = cr(v, currency)
    elif unit == "count":
        out = f"{v:.0f}"
    else:
        out = f"{v:.2f}" if abs(v) < 10 else f"{v:.1f}"
    return out.replace("-", "−", 1) if out.startswith("-") else out


def _run(rule: Any, ctx: Any, lim: Limits) -> Outcome:
    try:
        out: Outcome = rule(ctx, lim)
    except MissingThreshold:
        return Outcome("no_data", reason="no threshold set for this check in profiles.yaml")
    return out


class _Blank(dict[str, str]):
    def __missing__(self, key: str) -> str:
        return "—"


def _result(
    section: str, c: CheckDef, o: Outcome, lim: Limits, currency: str = "INR"
) -> CheckResult:
    shown_v = fmt(o.value, c.unit, currency=currency)
    shown_t = fmt(o.threshold, c.unit, currency=currency)
    names = _Blank(
        value=shown_v,
        threshold=shown_t,
        abs_value=fmt(None if o.value is None else abs(o.value), c.unit, False, currency),
        upper=fmt(lim.upper, c.unit),
    )
    names.update(o.vars)
    if o.status == "no_data":
        text = f"Not enough data: {o.reason}." if o.reason else "Not enough data."
    elif o.text:
        text = o.text
    else:
        text = (c.pass_text if o.status == "pass" else c.fail_text).format_map(names)
    help_text = c.help.format_map(names) if c.help else None
    return CheckResult(
        section=section,
        check_id=c.id,
        label=c.label,
        status=o.status,
        value=None if o.value is None else round(o.value, 4),
        threshold=None if o.threshold is None else round(o.threshold, 4),
        unit=c.unit,
        display_value=names["value"],
        display_threshold=names["threshold"],
        explanation=text,
        help=help_text,
        highlight=list(c.highlight),
    )


def _section(
    key: str, sd: SectionDef, results: list[CheckResult], cfg: ChecksConfig, kind: Kind
) -> SectionResult:
    with_data = [r for r in results if r.status != "no_data"]
    passed = sum(r.status == "pass" for r in with_data)
    score: int | None = None
    note: str | None = None
    if len(with_data) >= cfg.axis.min_applicable[kind]:
        # Halves round up (3 of 4 → 4.5 → 5), not to even as round() would.
        score = math.floor(passed / len(with_data) * cfg.axis.max + 0.5)
    else:
        note = "Not enough data"
    return SectionResult(
        key, sd.label, sd.question, sd.caption, results, passed, len(with_data), score, note
    )


def _confidence(
    with_data: int, total: int, p: Profiles
) -> tuple[Literal["high", "medium", "low"], str]:
    cov = with_data / total if total else 0.0
    level: Literal["high", "medium", "low"] = (
        "high"
        if cov >= p.confidence.high_min_coverage
        else "medium"
        if cov >= p.confidence.medium_min_coverage
        else "low"
    )
    missing = total - with_data
    reason = (
        f"All {total} checks had data."
        if missing == 0
        else f"{with_data} of {total} checks had data; {missing} could not be worked out."
    )
    return level, reason


def _step(total: int, max_total: int, cfg: ChecksConfig) -> int | None:
    if max_total <= 0:
        return None
    ratio = total / max_total
    return 1 + sum(ratio >= cut for cut in cfg.axis.score_steps)


def _highlights(sections: list[SectionResult], kind: Highlight, status: Status) -> list[str]:
    return [
        r.explanation
        for s in sections
        for r in s.checks
        if kind in r.highlight and r.status == status
    ]


def _dedupe(items: Sequence[str], n: int) -> list[str]:
    out: list[str] = []
    for i in items:
        if i and i not in out:
            out.append(i)
    return out[:n]


def _shape(
    kind: Kind,
    sections: list[SectionResult],
    p: Profiles,
    cfg: ChecksConfig,
    *,
    extra_risks: Sequence[str] = (),
    summary_tail: str = "",
    name: str,
) -> tuple[
    int, int, int | None, int, int, Literal["high", "medium", "low"], str, list[str], list[str], str
]:
    scored = [s for s in sections if s.score is not None]
    total = sum(s.score or 0 for s in scored)
    max_total = cfg.axis.max * len(scored)
    n_total = sum(len(s.checks) for s in sections)
    n_data = sum(s.with_data for s in sections)
    conf, conf_reason = _confidence(n_data, n_total, p)
    rewards = _dedupe(_highlights(sections, "reward", "pass"), 5)
    risks = _dedupe([*extra_risks, *_highlights(sections, "risk", "fail")], 5)
    passed = sum(s.passed for s in sections)
    parts = [f"{name} passes {passed} of the {n_data} checks that could be worked out."]
    if scored:
        best = max(scored, key=lambda s: s.score or 0)
        worst = min(scored, key=lambda s: s.score or 0)
        if best is not worst and (best.score or 0) > (worst.score or 0):
            parts.append(
                f"It looks strongest on {best.label} ({best.score}/{cfg.axis.max}) and weakest "
                f"on {worst.label} ({worst.score}/{cfg.axis.max})."
            )
    missing = n_total - n_data
    if missing:
        parts.append(
            f"{missing} check{'s' if missing != 1 else ''} had no data, so confidence is {conf}."
        )
    if summary_tail:
        parts.append(summary_tail)
    return (
        total,
        max_total,
        _step(total, max_total, cfg),
        n_total,
        n_data,
        conf,
        conf_reason,
        rewards,
        risks,
        " ".join(parts),
    )


# ---------------------------------------------------------------------------- stocks


def daily_values(sig: "StockSignal", daily: pd.DataFrame, p: Profiles) -> dict[str, float | None]:
    """Indicator values from daily bars, whatever the style (the same rule as screener facts)."""
    frame = next((t for t in sig.technical.timeframes if t.interval == "1d"), None)
    if frame is not None:
        return frame.analysis.values
    if daily.empty:
        return {}
    return analyse_frame(daily, "1d", p.technical, is_index=False).values


def stock_context(sig: "StockSignal", daily: pd.DataFrame, p: Profiles) -> StockContext:
    rep = sig.fundamental
    annual = rep.statements.annual if rep.statements is not None else pd.DataFrame()
    values = daily_values(sig, daily, p)
    price = values.get("close") or (sig.levels.close if sig.levels else None)
    closes = daily["close"] if "close" in daily else pd.Series(dtype="float64")
    # Statements in another currency (USD filers): ratios mixing them with INR prices mean nothing.
    inr = rep.currency == "INR"
    fv, why = fair_value(rep.metrics, annual if inr else None, price, rep.is_financial)
    points = pe_history(annual, closes, rep.metrics, price) if inr else []
    return StockContext(
        report=rep,
        annual=annual,
        daily=values,
        market=sig.technical.context.values,
        risk_label=sig.risk_label,
        fair_value=fv,
        fair_value_reason=why,
        pe_points=points,
        rsi_key=f"rsi{p.technical.periods.rsi}",
    )


def evaluate_stock(sig: "StockSignal", daily: pd.DataFrame) -> ShapeResult:
    p, cfg = get_profiles(), get_checks()
    risk = p.risk_levels[sig.risk]
    ctx = stock_context(sig, daily, p)
    company = "financial" if ctx.financial else "non_financial"
    sections: list[SectionResult] = []
    for key, sd in cfg.stock.items():
        results: list[CheckResult] = []
        for c in sd.checks:
            if c.applies not in ("all", company):
                continue
            lim = Limits(
                resolve(c.threshold, p, risk), resolve(c.upper, p, risk), resolve(c.ratio, p, risk)
            )
            if key != "momentum" and not sig.fundamental.applicable:
                o = Outcome("no_data", reason="company checks don't apply to ETFs and indices")
            else:
                o = _run(STOCK_RULES[c.id], ctx, lim)
            results.append(_result(key, c, o, lim, ctx.currency))
        sec = _section(key, sd, results, cfg, "stock")
        if key == "dividends" and ctx.pays_dividend is False:
            sec = SectionResult(**{**sec.__dict__, "note": "No dividend"})
        if ctx.financial and len(results) < len(sd.checks):
            note = sec.note or "Some checks don't apply to lenders and insurers"
            sec = SectionResult(**{**sec.__dict__, "note": note})
        sections.append(sec)
    severe = [f.text for f in sig.flags if f.severe]
    other = [f.text for f in sig.flags if not f.severe]
    tail = (
        f"Under your {sig.style_label} style and {sig.risk_label} risk, "
        f"the signal is {sig.signal_label}."
    )
    if ctx.fair_value is not None:
        tail = f"{describe(ctx.fair_value)} {tail}"
    total, max_total, step, n, n_data, conf, conf_reason, rewards, risks, summary = _shape(
        "stock", sections, p, cfg, extra_risks=[*severe, *other], summary_tail=tail, name=sig.label
    )
    return ShapeResult(
        kind="stock",
        sections=sections,
        total=total,
        max_total=max_total,
        axis_max=cfg.axis.max,
        step=step,
        checks_total=n,
        checks_with_data=n_data,
        confidence=conf,
        confidence_reason=conf_reason,
        rewards=rewards,
        risks=risks,
        summary=summary,
        fair_value=ctx.fair_value,
        pe_history=ctx.pe_points,
    )


# ---------------------------------------------------------------------------- funds


def _expense_limit(report: FundReport, p: Profiles) -> float:
    acls = report.asset_class
    key: Literal["equity", "debt", "other"] = (
        "debt" if acls == "debt" else "equity" if acls == "equity" else "other"
    )
    return p.mf.expense_ratio_high_pct[key]


def evaluate_fund(report: FundReport) -> ShapeResult:
    p, cfg = get_profiles(), get_checks()
    risk = p.risk_levels[p.defaults.risk]  # fund checks don't use risk-level thresholds
    ctx = FundContext(report, _expense_limit(report, p))
    sections: list[SectionResult] = []
    for key, sd in cfg.fund.items():
        results = []
        for c in sd.checks:
            lim = Limits(
                resolve(c.threshold, p, risk), resolve(c.upper, p, risk), resolve(c.ratio, p, risk)
            )
            results.append(_result(key, c, _run(FUND_RULES[c.id], ctx, lim), lim))
        sections.append(_section(key, sd, results, cfg, "fund"))
    total, max_total, step, n, n_data, conf, conf_reason, rewards, risks, summary = _shape(
        "fund",
        sections,
        p,
        cfg,
        summary_tail=f"The fund signal is {report.signal_label}: {report.rule}",
        name=report.name,
    )
    return ShapeResult(
        kind="fund",
        sections=sections,
        total=total,
        max_total=max_total,
        axis_max=cfg.axis.max,
        step=step,
        checks_total=n,
        checks_with_data=n_data,
        confidence=conf,
        confidence_reason=conf_reason,
        rewards=rewards,
        risks=risks,
        summary=summary,
    )


# ---------------------------------------------------------------------------- portfolio


@dataclass(frozen=True)
class AxisAverage:
    key: str
    label: str
    score: float | None  # value-weighted average, 0 … axis.max
    coverage: float  # share of the stock value with a score on this axis


@dataclass(frozen=True)
class PortfolioShape:
    axes: list[AxisAverage]
    total: float
    max_total: int
    axis_max: int
    step: int | None
    stock_value: float
    holdings: int


def portfolio_shape(items: Sequence[tuple[float, ShapeResult]]) -> PortfolioShape:
    """Value-weighted average of the holdings' axis scores (stocks only; funds have other axes)."""
    cfg = get_checks()
    value = sum(v for v, _ in items if v > 0)
    axes: list[AxisAverage] = []
    for key, sd in cfg.stock.items():
        scored = [(v, s.axes.get(key)) for v, s in items if v > 0 and s.axes.get(key) is not None]
        w = sum(v for v, _ in scored)
        avg = round(sum(v * (sc or 0) for v, sc in scored) / w, 1) if w > 0 else None
        axes.append(AxisAverage(key, sd.label, avg, round(w / value, 4) if value else 0.0))
    have = [a for a in axes if a.score is not None]
    total = round(sum(a.score or 0 for a in have), 1)
    max_total = cfg.axis.max * len(have)
    step = _step(round(total), max_total, cfg)
    return PortfolioShape(axes, total, max_total, cfg.axis.max, step, round(value, 2), len(items))


@dataclass(frozen=True)
class HoldingFacts:
    label: str
    value: float
    shape: ShapeResult
    signal: str
    signal_label: str
    weight: float | None
    max_weight: float


def portfolio_notes(
    holdings: Sequence[HoldingFacts],
    sectors: Sequence[tuple[str, float, float]],  # (sector, weight, limit)
) -> tuple[list[str], list[str]]:
    """Rewards and risks for the whole portfolio, in plain English."""
    cfg = get_checks()
    rewards: list[str] = []
    risks: list[str] = []
    for name, w, limit in sectors:
        if w > limit:
            risks.append(
                f"Over-exposed to {name}: {w * 100:.0f}% vs your {limit * 100:.0f}% limit."
            )
    for h in holdings:
        if h.weight is not None and h.weight > h.max_weight:
            risks.append(
                f"{h.label} is {h.weight * 100:.1f}% of the portfolio, above your "
                f"{h.max_weight * 100:.0f}% limit per stock."
            )
    sells = [h.label for h in holdings if h.signal in ("sell", "reduce")]
    if sells:
        risks.append(
            f"{len(sells)} holding{'s' if len(sells) != 1 else ''} with a Sell or Reduce signal: "
            + ", ".join(sells[:3])
            + (" …" if len(sells) > 3 else "")
            + "."
        )
    value = sum(h.value for h in holdings if h.value > 0)
    if value > 0:
        weak = cfg.axis.max // 3  # 2 of 6 or less: weak
        strong = cfg.axis.max - 1  # 5 of 6 or more: strong

        def share(pred: Any) -> float:
            return sum(h.value for h in holdings if h.value > 0 and pred(h)) / value * 100

        health_weak = share(lambda h: (h.shape.axes.get("health") or 99) <= weak)
        health_strong = share(lambda h: (h.shape.axes.get("health") or -1) >= strong)
        if health_weak >= 10:
            risks.append(
                f"{health_weak:.0f}% of your stock value is in companies with weak Financial "
                f"Health ({weak}/{cfg.axis.max} or less)."
            )
        if health_strong >= 25:
            rewards.append(
                f"{health_strong:.0f}% of your stock value is in companies with strong Financial "
                f"Health ({strong}/{cfg.axis.max} or more)."
            )
        buys = share(lambda h: h.signal in ("buy", "strong_buy"))
        if buys >= 25:
            rewards.append(f"{buys:.0f}% of your stock value has a Buy signal.")
        growth = share(lambda h: (h.shape.axes.get("growth") or -1) >= strong - 1)
        if growth >= 25:
            rewards.append(f"{growth:.0f}% of your stock value is in fast-growing companies.")
    if sectors and not any(w > limit for _, w, limit in sectors):
        rewards.append(f"Spread across {len(sectors)} sectors, none above your sector limit.")
    return rewards[:5], risks[:5]


# ---------------------------------------------------------------------------- history


def record_axes(
    session: Session, ticker: str, risk: str, shape: ShapeResult, day: date | None = None
) -> None:
    """Upsert today's shape into the axis history (one row per ticker, day and risk level)."""
    d = day or now_ist().date()
    row = session.get(AxisRecord, (ticker, d, risk)) or AxisRecord(
        ticker=ticker, day=d, risk=risk, axes_json="{}", total=0, max_total=0
    )
    row.axes_json = json.dumps(shape.axes)
    row.total = shape.total
    row.max_total = shape.max_total
    row.recorded_at = utcnow()
    session.add(row)


def record_shape(session: Session, sig: "StockSignal", daily: pd.DataFrame) -> None:
    """Save the stock's shape next to its signal. A checks problem is logged, never allowed to
    stop the signal history from being saved."""
    try:
        record_axes(session, sig.ticker, sig.risk, evaluate_stock(sig, daily))
    except Exception:
        logger.exception("Couldn't record the Score Shape for %s", sig.ticker)


@dataclass(frozen=True)
class WeekChange:
    since: date
    axes: dict[str, int | None]  # change per axis (None when either side had no score)
    total: int
    previous_signal: str | None  # the signal on or before `since`, same style and risk
    signal_changed: bool


def week_change(
    session: Session,
    ticker: str,
    risk: RiskKey | str,
    style: str,
    current: ShapeResult,
    current_signal: str,
    today: date | None = None,
    min_days: int = 6,
) -> WeekChange | None:
    """The shape and signal now vs the latest record at least `min_days` old (about a week)."""
    today = today or now_ist().date()
    cutoff = today - timedelta(days=min_days)
    old = session.exec(
        select(AxisRecord)
        .where(AxisRecord.ticker == ticker, AxisRecord.risk == risk, col(AxisRecord.day) <= cutoff)
        .order_by(col(AxisRecord.day).desc())
    ).first()
    if old is None:
        return None
    before: dict[str, int | None] = json.loads(old.axes_json)
    deltas: dict[str, int | None] = {}
    for k, now in current.axes.items():
        then = before.get(k)
        deltas[k] = now - then if now is not None and then is not None else None
    sig = session.exec(
        select(SignalRecord)
        .where(
            SignalRecord.ticker == ticker,
            SignalRecord.style == style,
            SignalRecord.risk == risk,
            col(SignalRecord.day) <= old.day,
        )
        .order_by(col(SignalRecord.day).desc())
    ).first()
    prev = sig.signal if sig else None
    return WeekChange(
        since=old.day,
        axes=deltas,
        total=current.total - old.total,
        previous_signal=prev,
        signal_changed=prev is not None and prev != current_signal,
    )
