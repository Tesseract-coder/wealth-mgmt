"""Filtering a stored scan: risk pre-filters, then a screen's conditions, then ranking.

Order for each scored stock:
1. Already held: left out unless you ask to include holdings.
2. Risk pre-filters from your risk level: market cap at least `min_market_cap_cr` (must be
   known), debt/equity at most `max_debt_to_equity` and beta at most `max_beta` (checked when
   known; debt/equity not for financials). Liquidity was checked during the scan.
3. Signal: `screener.exclude_signals` (Sell, Reduce by default) are never ideas.
4. The screen's filters: every condition must hold. A missing value fails the condition, except
   fields that don't apply to financials, which lenders and insurers pass.
5. Ranked by composite score (then confidence, then market cap); the top `screener.top_n`.
"""

from dataclasses import dataclass, field

from app.analysis.positions import Portfolio, add_amount
from app.analysis.signals import SIGNAL_LABEL
from app.core.formatting import format_inr
from app.core.profiles import Profiles, RebalanceConfig, RiskLevel, ScreenFilter
from app.screener.fields import FIELD_BY_KEY, OPS
from app.screener.scan import ScanRow

CONF_RANK = {"high": 0, "medium": 1, "low": 2}


def describe(f: ScreenFilter) -> str:
    meta = FIELD_BY_KEY[f.field]
    unit = "" if meta.unit in ("", "x", "₹", "₹ Cr") else meta.unit
    if f.op == "between":
        assert isinstance(f.value, list)
        return f"{meta.label} between {f.value[0]:g} and {f.value[1]:g}{unit}"
    assert not isinstance(f.value, list)
    return f"{meta.label} {OPS[f.op]} {f.value:g}{unit}"


def check(f: ScreenFilter, value: float | None, financial: bool) -> bool | None:
    """True/False, or None when the value is missing (which fails the filter)."""
    if value is None:
        return True if financial and FIELD_BY_KEY[f.field].financial_exempt else None
    if f.op == "between":
        assert isinstance(f.value, list)
        return f.value[0] <= value <= f.value[1]
    assert not isinstance(f.value, list)
    return {
        "gt": value > f.value,
        "gte": value >= f.value,
        "lt": value < f.value,
        "lte": value <= f.value,
    }[f.op]


def prefilter_failures(row: ScanRow, risk: RiskLevel) -> list[str]:
    out = []
    mc = row.facts.get("market_cap")
    if mc is None:
        out.append("Market cap unknown (no fundamentals)")
    elif mc < risk.min_market_cap_cr:
        out.append(
            f"Market cap {format_inr(mc, 0)} Cr below your "
            f"{format_inr(risk.min_market_cap_cr, 0)} Cr minimum"
        )
    de = row.facts.get("debt_equity")
    if (
        risk.max_debt_to_equity is not None
        and de is not None
        and not row.is_financial
        and de > risk.max_debt_to_equity
    ):
        out.append(f"Debt/equity {de:.2f} above your {risk.max_debt_to_equity:g} limit")
    beta = row.facts.get("beta")
    if risk.max_beta is not None and beta is not None and beta > risk.max_beta:
        out.append(f"Beta {beta:.2f} above your {risk.max_beta:g} limit")
    return out


@dataclass
class SectorImpact:
    sector: str | None
    amount: float | None  # a starter position (rebalance.buy_target × max weight per stock)
    quantity: int | None
    before: float | None
    after: float | None
    over_limit: bool
    text: str


def sector_impact(
    row: ScanRow, pf: Portfolio | None, risk: RiskLevel, cfg: RebalanceConfig
) -> SectorImpact:
    close = row.levels.close if row.levels else row.facts.get("close")
    if pf is None or pf.total <= 0:
        return SectorImpact(
            row.sector, None, None, None, None, False,
            "Import your holdings to see how this would change your sectors.",
        )  # fmt: skip
    target = risk.max_weight_per_stock * cfg.buy_target
    held_value = (pf.positions[row.ticker].value or 0.0) if row.ticker in pf.positions else 0.0
    amount = add_amount(held_value, pf.total, target)
    qty = int(amount // close) if close else None
    if not row.sector:
        return SectorImpact(
            None, round(amount, 2), qty, None, None, False,
            f"A starter position of {format_inr(amount, 0)} ({target * 100:.1f}% of your "
            "portfolio); sector unknown.",
        )  # fmt: skip
    sv = pf.sector_values.get(row.sector, 0.0)
    before = sv / pf.total
    after = (sv + amount) / (pf.total + amount)
    over = after > risk.max_weight_per_sector
    return SectorImpact(
        row.sector,
        round(amount, 2),
        qty,
        round(before, 4),
        round(after, 4),
        over,
        f"A starter position of {format_inr(amount, 0)} ({target * 100:.1f}% of your portfolio)"
        f" takes {row.sector} from {before * 100:.1f}% to {after * 100:.1f}%"
        + (f", above your {risk.max_weight_per_sector * 100:g}% sector limit" if over else ""),
    )


@dataclass
class Candidate:
    rank: int
    row: ScanRow
    passed: list[str]  # the filters it met, in words
    impact: SectorImpact


@dataclass
class ScreenResult:
    candidates: list[Candidate]
    filters: list[str]
    counts: dict[str, int]  # how many stocks fell out where
    prefilters: list[str]
    near_misses: list[tuple[ScanRow, list[str]]] = field(default_factory=list)


def screen(
    rows: list[ScanRow],
    filters: list[ScreenFilter],
    p: Profiles,
    risk: RiskLevel,
    pf: Portfolio | None,
    *,
    include_held: bool = False,
    top_n: int | None = None,
) -> ScreenResult:
    cfg = p.screener
    counts = {
        "universe": len(rows),
        "not_scored": 0,
        "held": 0,
        "prefilter": 0,
        "signal": 0,
        "filters": 0,
        "missing_data": 0,
        "passed": 0,
    }
    passing: list[tuple[ScanRow, list[str]]] = []
    misses: list[tuple[ScanRow, list[str]]] = []
    for r in rows:
        if r.status != "scored":
            counts["not_scored"] += 1
            continue
        if r.held and not include_held:
            counts["held"] += 1
            continue
        if prefilter_failures(r, risk):
            counts["prefilter"] += 1
            continue
        if r.signal in cfg.exclude_signals or r.composite is None:
            counts["signal"] += 1
            continue
        failed, missing, met = [], False, []
        for f in filters:
            ok = check(f, r.facts.get(f.field), r.is_financial)
            if ok:
                met.append(describe(f))
            else:
                missing |= ok is None
                failed.append(describe(f) + (" (no data)" if ok is None else ""))
        if failed:
            counts["missing_data" if missing and len(failed) == 1 else "filters"] += 1
            if len(failed) == 1:
                misses.append((r, failed))
            continue
        passing.append((r, met))
    counts["passed"] = len(passing)
    passing.sort(
        key=lambda x: (
            -(x[0].composite or 0),
            CONF_RANK.get(x[0].confidence or "", 3),
            -(x[0].facts.get("market_cap") or 0),
        )
    )
    misses.sort(key=lambda x: -(x[0].composite or 0))
    n = top_n or cfg.top_n
    return ScreenResult(
        candidates=[
            Candidate(i + 1, r, met, sector_impact(r, pf, risk, p.rebalance))
            for i, (r, met) in enumerate(passing[:n])
        ],
        filters=[describe(f) for f in filters],
        counts=counts,
        prefilters=prefilter_text(risk, p),
        near_misses=misses[:5],
    )


def prefilter_text(risk: RiskLevel, p: Profiles) -> list[str]:
    cfg = p.screener
    out = [
        f"Average daily traded value ≥ ₹{cfg.min_avg_daily_traded_value_cr:g} Cr "
        f"(last {cfg.traded_value_sessions} sessions)",
        f"Market cap ≥ {format_inr(risk.min_market_cap_cr, 0)} Cr",
    ]
    if risk.max_debt_to_equity is not None:
        out.append(f"Debt/equity ≤ {risk.max_debt_to_equity:g} (not for financials)")
    if risk.max_beta is not None:
        out.append(f"Beta ≤ {risk.max_beta:g}")
    if cfg.exclude_signals:
        out.append("Signal not " + " or ".join(SIGNAL_LABEL[s] for s in cfg.exclude_signals))
    return out
