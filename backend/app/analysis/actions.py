"""The Overview's "Action needed" list: every signal, flag and warning worth a look, most
severe first. Built from cached data only; it repeats what the signals already say, with
a link to the reasons."""

from dataclasses import dataclass
from typing import Literal

from sqlmodel import Session

from app.analysis.mf import FundReport, analyse_holdings
from app.analysis.signals import StockSignal, active_profile, evaluate_holdings, resolve_style
from app.core.profiles import get_profiles
from app.data.provider import DataProvider

Severity = Literal["high", "medium", "low"]
SEVERITY_ORDER: dict[Severity, int] = {"high": 0, "medium": 1, "low": 2}


@dataclass(frozen=True)
class Action:
    severity: Severity
    kind: Literal["stock", "fund", "portfolio", "data"]
    subject: str
    title: str
    detail: str
    link: str | None


def _stock_actions(s: StockSignal) -> list[Action]:
    link = f"/analysis/{s.ticker}"
    out: list[Action] = []
    if s.signal == "sell":
        out.append(Action("high", "stock", s.label, "Sell", s.rule, link))
    elif s.signal == "reduce":
        out.append(Action("medium", "stock", s.label, "Reduce", s.rule, link))
    for f in s.flags:
        if f.key == "sector_concentration":
            continue  # listed once per sector, not once per stock
        if f.severe and s.signal == "sell" and f.text in s.rule:
            continue  # a severe flag usually *is* the Sell rule; don't say it twice
        if f.key == "stop_breached" and not f.severe:
            out.append(Action("low", "stock", s.label, "Below trailing stop", f.text, link))
            continue
        sev: Severity = "high" if f.severe else "medium"
        out.append(Action(sev, "stock", s.label, "Red flag", f.text, link))
    if s.signal in ("strong_buy", "buy") and s.rebalance.action == "add":
        out.append(Action("low", "stock", s.label, s.signal_label, s.rebalance.text, link))
    tfs = s.technical.timeframes
    fr = tfs[0].freshness if tfs else None
    if fr is None or fr.status != "fresh":
        why = fr.reason if fr else "No price data"
        out.append(Action("low", "data", s.label, "Prices not fresh", why, link))
    return out


def _fund_actions(f: FundReport) -> list[Action]:
    link = f"/mutual-funds/{f.code}"
    if f.signal == "switch":
        # Underperformance is worse news than a cheaper plan with the same portfolio.
        sev: Severity = "medium" if f.plan == "regular" and "Direct plan" in f.rule else "high"
        return [Action(sev, "fund", f.name, "Switch", f.rule, link)]
    if f.signal == "review":
        return [Action("low", "fund", f.name, "Review", f.rule, link)]
    return []


def action_list(session: Session, provider: DataProvider) -> tuple[list[Action], str, str]:
    """(actions, style label, risk label) for your saved profile."""
    st, rk, ctw = active_profile(session)
    style_key, _ = resolve_style(st)
    profiles = get_profiles()
    pf, sigs = evaluate_holdings(session, provider, style_key, rk, ctw, save=False)
    out: list[Action] = []
    for s in sigs:
        out.extend(_stock_actions(s))
    limit = profiles.risk_levels[rk].max_weight_per_sector
    if pf.total > 0:
        for name, v in sorted(pf.sector_values.items(), key=lambda x: -x[1]):
            w = v / pf.total
            if w > limit:
                out.append(
                    Action(
                        "medium",
                        "portfolio",
                        name,
                        "Sector over limit",
                        f"{name} is {w * 100:.1f}% of your portfolio, above your "
                        f"{limit * 100:.0f}% sector limit.",
                        "/holdings",
                    )
                )
    for f in analyse_holdings(session, provider):
        out.extend(_fund_actions(f))
    out.sort(key=lambda a: (SEVERITY_ORDER[a.severity], a.kind != "portfolio", a.subject))
    return out, profiles.styles[style_key].label, profiles.risk_levels[rk].label
