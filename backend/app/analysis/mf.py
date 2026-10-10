"""Mutual fund analysis: your XIRR, the scheme's returns and risk, rolling returns vs its
category benchmark, Regular vs Direct, cost, overlap with your other funds, and a
Continue / Review / Switch signal with reasons.

Benchmarks are Yahoo price indices: they leave out dividends, which the official total-return
indices include, so a fund looks roughly 1–1.5% a year better here than in its factsheet.
"""

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Literal

import pandas as pd
from sqlmodel import Session, col, select

from app.analysis.returns import (
    RiskStats,
    Rolling,
    risk_stats,
    rolling_rows,
    rolling_vs,
    trailing_cagr,
    xirr,
)
from app.core.formatting import now_ist
from app.core.profiles import AssetClass, MFBenchmark, MFConfig, get_profiles
from app.data.amfi import Scheme
from app.data.freshness import Freshness
from app.data.provider import DataProvider
from app.importers.cas import PURCHASE_TYPES
from app.importers.reference import scheme_resolver
from app.importers.scheme_resolver import normalise_scheme
from app.importers.snapshots import latest_snapshot
from app.models.tables import (
    FundInfo,
    FundPortfolioRow,
    FundPortfolioUpload,
    MFHolding,
    MFTransaction,
    utcnow,
)

FundSignal = Literal["continue", "review", "switch", "no_signal"]
FUND_SIGNAL_LABEL: dict[str, str] = {
    "continue": "Continue",
    "review": "Review",
    "switch": "Switch",
    "no_signal": "Insufficient data",
}
OUTFLOW_TYPES = PURCHASE_TYPES | {"STAMP_DUTY_TAX", "STT_TAX", "TDS_TAX"}
INFLOW_TYPES = {"REDEMPTION", "SWITCH_OUT", "SWITCH_OUT_MERGER", "DIVIDEND_PAYOUT", "GIFT_OUT"}
PERIODS = (1, 3, 5)


@dataclass(frozen=True)
class Reason:
    direction: Literal["bullish", "bearish", "neutral"]
    text: str


@dataclass(frozen=True)
class Overlap:
    code: str
    name: str
    pct: float
    common: int
    approximate: bool
    note: str


@dataclass(frozen=True)
class MyHolding:
    units: float
    invested: float | None
    value: float | None
    pnl: float | None
    folios: list[str]
    first_purchase: date | None
    xirr: float | None
    xirr_basis: str
    xirr_approximate: bool


@dataclass
class FundReport:
    code: str
    name: str
    amc: str | None
    category: str | None
    asset_class: AssetClass
    plan: str | None
    option: str | None
    nav: float | None
    nav_date: date | None
    previous_nav: float | None
    nav_freshness: Freshness
    history_start: date | None
    holding: MyHolding | None
    returns: dict[int, float | None]
    benchmark: MFBenchmark | None
    benchmark_returns: dict[int, float | None]
    risk: RiskStats | None
    benchmark_risk: RiskStats | None
    rolling: list[Rolling]
    direct_twin: Scheme | None
    direct_gap_pp: float | None  # Direct − Regular CAGR, percentage points a year
    direct_gap_basis: str
    expense_ratio_pct: float | None
    overlaps: list[Overlap]
    segment_peers: list[str]  # your other funds against the same benchmark
    signal: FundSignal
    rule: str
    reasons: list[Reason]
    notes: list[str] = field(default_factory=list)
    unavailable: list[str] = field(default_factory=list)
    fetch_errors: list[str] = field(default_factory=list)

    @property
    def signal_label(self) -> str:
        return FUND_SIGNAL_LABEL[self.signal]


# ---------------------------------------------------------------------------- classification


def asset_class_of(category: str | None, cfg: MFConfig) -> AssetClass:
    c = (category or "").lower()
    classes: tuple[Literal["debt", "hybrid", "other"], ...] = ("debt", "hybrid", "other")
    for cls in classes:
        if any(k in c for k in cfg.asset_classes.get(cls, [])):
            return cls
    return "equity"


def benchmark_for(scheme_name: str, category: str | None, cfg: MFConfig) -> MFBenchmark | None:
    """First configured benchmark whose keywords appear in the category or (for index funds,
    ETFs and thematic funds) the name. Debt and 'other' funds get none."""
    if asset_class_of(category, cfg) in ("debt", "other"):
        return None
    text = f"{category or ''} {scheme_name}".lower()
    for b in cfg.benchmarks:
        if any(k in text for k in b.match):
            return b
    return None


# ---------------------------------------------------------------------------- your cash flows


def holding_cash_flows(
    session: Session, holdings: list[MFHolding]
) -> tuple[list[tuple[date, float]], bool]:
    """(flows, from_transactions). Money in is negative. Without a detailed CAS, one lump sum
    on the first purchase date is assumed when both the date and the invested amount are known."""
    ids = [h.id for h in holdings if h.id is not None]
    txns = (
        session.exec(select(MFTransaction).where(col(MFTransaction.holding_id).in_(ids))).all()
        if ids
        else []
    )
    flows: list[tuple[date, float]] = []
    for t in txns:
        if t.amount is None:
            continue
        if t.type in OUTFLOW_TYPES:
            flows.append((t.date, -abs(t.amount)))
        elif t.type in INFLOW_TYPES:
            flows.append((t.date, abs(t.amount)))
    if flows:
        return flows, True
    for h in holdings:
        if h.first_purchase_date and h.invested:
            flows.append((h.first_purchase_date, -h.invested))
    return flows, False


def _my_holding(
    session: Session, holdings: list[MFHolding], nav: float | None, today: date
) -> MyHolding:
    units = sum(h.units for h in holdings)
    invested_vals = [h.invested for h in holdings]
    invested = sum(v for v in invested_vals if v is not None) if any(invested_vals) else None
    if nav is not None:
        value: float | None = units * nav
    else:
        vals = [h.current_value for h in holdings]
        value = sum(v for v in vals if v is not None) if all(v is not None for v in vals) else None
    pnl = None if value is None or invested is None else value - invested
    firsts = [h.first_purchase_date for h in holdings if h.first_purchase_date]
    flows, from_txns = holding_cash_flows(session, holdings)
    x = None
    approx = False
    if value is not None and flows:
        x = xirr([*flows, (today, value)])
    if x is None:
        basis = (
            "Not available: needs a detailed CAS (transactions), or a purchase date and the "
            "amount invested."
        )
    elif from_txns:
        basis = f"From {len(flows)} transactions in your CAS, valued at today's NAV"
    else:
        approx = True
        basis = (
            "Approximate: assumes everything was invested in one go on the first purchase date. "
            "Import a detailed CAS for an exact XIRR."
        )
    return MyHolding(
        units=round(units, 4),
        invested=None if invested is None else round(invested, 2),
        value=None if value is None else round(value, 2),
        pnl=None if pnl is None else round(pnl, 2),
        folios=sorted({h.folio for h in holdings if h.folio}),
        first_purchase=min(firsts) if firsts else None,
        xirr=x,
        xirr_basis=basis,
        xirr_approximate=approx,
    )


# ---------------------------------------------------------------------------- overlap


@dataclass(frozen=True)
class FundPortfolio:
    code: str
    as_of: date | None
    weights: dict[str, float]  # key (ISIN or normalised name) → % of net assets
    total: float


def _key(name: str, isin: str | None) -> str:
    return f"isin:{isin}" if isin else f"name:{normalise_scheme(name)}"


def load_fund_portfolio(session: Session, code: str) -> FundPortfolio | None:
    up = session.exec(
        select(FundPortfolioUpload)
        .where(FundPortfolioUpload.amfi_code == code)
        .order_by(col(FundPortfolioUpload.created_at).desc())
    ).first()
    if up is None:
        return None
    rows = session.exec(select(FundPortfolioRow).where(FundPortfolioRow.upload_id == up.id)).all()
    w: dict[str, float] = defaultdict(float)
    for r in rows:
        w[_key(r.name, r.isin)] += r.weight_pct
    return FundPortfolio(code, up.as_of, dict(w), up.total_weight_pct)


def overlap(
    a: FundPortfolio, b: FundPortfolio, cfg: MFConfig, today: date
) -> tuple[float, int, bool, str]:
    """Σ min(weight in A, weight in B) over common holdings (by ISIN, else name)."""
    common = set(a.weights) & set(b.weights)
    pct = sum(min(a.weights[k], b.weights[k]) for k in common)
    notes = []
    for p in (a, b):
        if p.total < cfg.overlap_min_coverage_pct:
            notes.append(f"holdings for {p.code} cover only {p.total:.0f}% of the fund")
        if p.as_of is None:
            notes.append(f"no 'as of' date for {p.code}'s holdings")
        elif (today - p.as_of).days > cfg.portfolio_max_age_days:
            notes.append(f"{p.code}'s holdings are from {p.as_of:%b %Y}")
    return round(pct, 1), len(common), bool(notes), "; ".join(notes)


# ---------------------------------------------------------------------------- analysis


def _series_cagrs(s: pd.Series) -> dict[int, float | None]:
    return {y: None if (v := trailing_cagr(s, y)) is None else round(v, 2) for y in PERIODS}


def _scheme(code: str) -> Scheme | None:
    return scheme_resolver().by_code.get(code)


def analyse_fund(
    session: Session,
    provider: DataProvider,
    code: str,
    *,
    holdings: list[MFHolding] | None = None,
    others: dict[str, tuple[str, MFBenchmark | None]] | None = None,
    fetch: bool = True,
    now: datetime | None = None,
) -> FundReport:
    """`others`: your other held funds {code: (name, benchmark)} for overlap and duplicates."""
    p = get_profiles()
    cfg = p.mf
    now = now or now_ist()
    today = now.date()
    errors: list[str] = []
    notes: list[str] = []
    na: list[str] = []
    sch = _scheme(code)
    name = sch.name if sch else (holdings[0].scheme_name if holdings else code)
    category = (sch.category if sch else None) or (holdings[0].category if holdings else None)
    plan = (sch.plan if sch else None) or (holdings[0].plan if holdings else None)
    option = (sch.option if sch else None) or (holdings[0].option if holdings else None)
    acls = asset_class_of(category, cfg)
    bench = benchmark_for(name, category, cfg)
    twin = scheme_resolver().direct_twin(sch) if sch else None

    if fetch:
        for c, lab in [(code, name)] + ([(twin.code, twin.name)] if twin else []):
            r = provider.ensure_nav(c, lab)
            if r.outcome == "failed":
                errors.append(r.message)
        if bench:
            r = provider.ensure_daily(bench.ticker, bench.label)
            if r.outcome == "failed":
                errors.append(r.message)

    navs = provider.nav_history(code)
    latest = provider.latest_nav(code)
    returns: dict[int, float | None] = _series_cagrs(navs) if len(navs) else dict.fromkeys(PERIODS)
    risk = risk_stats(navs, cfg.risk_free_rate_pct, cfg.risk_stats_years, cfg.min_history_days)
    if risk is None:
        na.append(f"Risk statistics (need {cfg.min_history_days} days of NAV history)")
    bench_returns: dict[int, float | None] = {y: None for y in PERIODS}
    bench_risk = None
    rolling: list[Rolling] = []
    if bench is None:
        na.append(
            "Benchmark comparison (no free index for "
            + ("debt funds" if acls == "debt" else f"'{category or 'this category'}'")
            + ")"
        )
    else:
        bdf = provider.daily(bench.ticker).frame
        if bdf.empty:
            na.append(f"Benchmark comparison ({bench.label} prices not downloaded yet)")
        else:
            bclose = bdf["close"].dropna()
            bclose.index = pd.to_datetime(bclose.index)
            bench_returns = _series_cagrs(bclose)
            if len(navs):
                start = pd.Timestamp(navs.index[0])
                bclose_cut = bclose.loc[bclose.index >= start]
                bench_risk = risk_stats(
                    bclose_cut, cfg.risk_free_rate_pct, cfg.risk_stats_years, cfg.min_history_days
                )
                for y in cfg.rolling_windows_years:
                    rv = rolling_vs(navs, bclose, y, cfg.rolling_step_days)
                    if rv is None:
                        na.append(
                            f"Rolling {y}-year returns (need {y}+ years of overlapping history)"
                        )
                    else:
                        rolling.append(rv)
            notes.append(
                f"Benchmark: {bench.label} price index (Yahoo has no total-return index, so it "
                "leaves out dividends: funds look about 1–1.5% a year better than in factsheets)."
            )

    # Regular vs Direct
    gap: float | None = None
    gap_basis = ""
    if plan == "regular":
        if twin is None:
            gap_basis = "No Direct plan of this scheme was found in the AMFI list."
        else:
            tw = provider.nav_history(twin.code)
            for y in (3, 1):
                a, b = trailing_cagr(tw, y), trailing_cagr(navs, y)
                if a is not None and b is not None:
                    gap = round(a - b, 2)
                    gap_basis = f"Direct minus Regular CAGR over {y} year{'s' if y > 1 else ''}"
                    break
            if gap is None:
                gap_basis = "Not enough NAV history for both plans yet."

    info = session.get(FundInfo, code)
    ter = info.expense_ratio_pct if info else None
    if ter is None:
        na.append("Expense ratio (no free API publishes it; enter it from the fund's factsheet)")

    # Overlap and duplicates against your other funds
    overlaps: list[Overlap] = []
    peers: list[str] = []
    others = {k: v for k, v in (others or {}).items() if k != code}
    if others:
        mine = load_fund_portfolio(session, code)
        if mine is None:
            na.append("Overlap with your other funds (upload this fund's portfolio holdings)")
        for oc, (oname, obench) in others.items():
            if bench and obench and obench.label == bench.label:
                peers.append(oname)
            if mine is None:
                continue
            theirs = load_fund_portfolio(session, oc)
            if theirs is None:
                continue
            pct, common, approx, note = overlap(mine, theirs, cfg, today)
            overlaps.append(Overlap(oc, oname, pct, common, approx, note))

    my = _my_holding(session, holdings, latest.nav, today) if holdings else None
    signal, rule, reasons = fund_signal(
        has_nav=len(navs) > 0,
        plan=plan,
        twin=twin,
        gap=gap,
        gap_basis=gap_basis,
        rolling=rolling,
        returns=returns,
        bench_returns=bench_returns,
        bench=bench,
        risk=risk,
        bench_risk=bench_risk,
        ter=ter,
        acls=acls,
        overlaps=overlaps,
        peers=peers,
        cfg=cfg,
    )
    return FundReport(
        code=code,
        name=name,
        amc=(sch.amc if sch else None) or (holdings[0].amc if holdings else None),
        category=category,
        asset_class=acls,
        plan=plan,
        option=option,
        nav=latest.nav,
        nav_date=latest.nav_date,
        previous_nav=latest.previous_nav,
        nav_freshness=latest.freshness,
        history_start=navs.index[0] if len(navs) else None,
        holding=my,
        returns=returns,
        benchmark=bench,
        benchmark_returns=bench_returns,
        risk=risk,
        benchmark_risk=bench_risk,
        rolling=rolling,
        direct_twin=twin,
        direct_gap_pp=gap,
        direct_gap_basis=gap_basis,
        expense_ratio_pct=ter,
        overlaps=sorted(overlaps, key=lambda o: -o.pct),
        segment_peers=peers,
        signal=signal,
        rule=rule,
        reasons=reasons,
        notes=notes,
        unavailable=na,
        fetch_errors=errors,
    )


def fund_signal(
    *,
    has_nav: bool,
    plan: str | None,
    twin: Scheme | None,
    gap: float | None,
    gap_basis: str,
    rolling: list[Rolling],
    returns: dict[int, float | None],
    bench_returns: dict[int, float | None],
    bench: MFBenchmark | None,
    risk: RiskStats | None,
    bench_risk: RiskStats | None,
    ter: float | None,
    acls: AssetClass,
    overlaps: list[Overlap],
    peers: list[str],
    cfg: MFConfig,
) -> tuple[FundSignal, str, list[Reason]]:
    """Switch beats Review beats Continue. Every rule that fires is listed as a reason."""
    rules = cfg.signals
    reasons: list[Reason] = []
    switch: list[str] = []
    review: list[str] = []
    if not has_nav:
        return "no_signal", "No NAV history yet: run a market-data refresh", []

    if plan == "regular":
        if twin is not None and rules.regular_plan_switch:
            gap_txt = (
                f"; it returned {gap:+.2f} pp a year vs this plan ({gap_basis.lower()})"
                if gap is not None
                else ""
            )
            switch.append(
                f"Regular plan: the Direct plan ({twin.code}) has the same portfolio at a lower "
                f"cost{gap_txt}. Switching is a redemption: check exit load and capital gains tax"
            )
        else:
            reasons.append(Reason("bearish", "Regular plan (higher cost than a Direct plan)"))
    elif plan == "direct":
        reasons.append(Reason("bullish", "Direct plan: no distributor commission in the cost"))

    long = next((r for r in rolling if r.years == 3), None) or next(
        (r for r in sorted(rolling, key=lambda r: -r.years)), None
    )
    if long is not None and bench is not None:
        txt = (
            f"Rolling {long.years}-year returns: {long.fund_avg:.1f}% vs {bench.label} "
            f"{long.bench_avg:.1f}% on average ({long.avg_excess:+.1f} pp), beating it in "
            f"{long.beat_share * 100:.0f}% of {long.windows} windows"
        )
        if (
            long.avg_excess <= rules.switch_rolling_excess_pp
            and long.beat_share <= rules.switch_max_beat_share
        ):
            switch.append(txt + ": a persistent underperformer")
        elif long.avg_excess < rules.review_rolling_excess_pp:
            review.append(txt)
        elif long.avg_excess > 0:
            reasons.append(Reason("bullish", txt))
        else:
            reasons.append(Reason("neutral", txt))
    f1, b1 = returns.get(1), bench_returns.get(1)
    if f1 is not None and b1 is not None and bench is not None:
        ex = f1 - b1
        txt = f"Last year {f1:+.1f}% vs {bench.label} {b1:+.1f}% ({ex:+.1f} pp)"
        if ex < rules.review_1y_excess_pp:
            review.append(txt)
        else:
            reasons.append(Reason("bullish" if ex > 0 else "neutral", txt))
    if risk and bench_risk and risk.sharpe is not None and bench_risk.sharpe is not None:
        better = risk.sharpe >= bench_risk.sharpe
        reasons.append(
            Reason(
                "bullish" if better else "bearish",
                f"Sharpe {risk.sharpe:.2f} vs benchmark {bench_risk.sharpe:.2f} "
                f"over {risk.years:g} years "
                f"({'better' if better else 'worse'} risk-adjusted return)",
            )
        )
    if risk and bench_risk:
        reasons.append(
            Reason(
                "neutral",
                f"Worst fall {risk.max_drawdown:.1f}% vs benchmark {bench_risk.max_drawdown:.1f}%",
            )
        )
    if ter is not None:
        limit = cfg.expense_ratio_high_pct[
            "debt" if acls == "debt" else "equity" if acls == "equity" else "other"
        ]
        if ter > limit:
            review.append(f"Expense ratio {ter:.2f}% is above {limit:g}%")
        else:
            reasons.append(Reason("bullish", f"Expense ratio {ter:.2f}% (at or below {limit:g}%)"))
    for o in overlaps:
        txt = f"{o.pct:.0f}% of its portfolio overlaps with {o.name}" + (
            " (approximate)" if o.approximate else ""
        )
        if o.pct > cfg.overlap_high_pct:
            review.append(txt)
        else:
            reasons.append(Reason("neutral", txt))
    if len(peers) + 1 > cfg.duplicate_category_max and bench is not None:
        review.append(
            f"You hold {len(peers) + 1} funds in the same segment ({bench.label}): "
            + ", ".join(peers)
            + " and this one"
        )
    reasons = [Reason("bearish", t) for t in switch + review] + reasons
    if switch:
        return "switch", "; ".join(switch), reasons
    if review:
        return "review", "; ".join(review), reasons
    if long is None and f1 is None:
        return "continue", "No rule fired, but there's little history to judge", reasons
    return "continue", "No review or switch rule fired", reasons


# ---------------------------------------------------------------------------- your funds


def held_funds(session: Session) -> dict[str, list[MFHolding]]:
    snap = latest_snapshot(session, "mf")
    if snap is None:
        return {}
    out: dict[str, list[MFHolding]] = defaultdict(list)
    for h in session.exec(select(MFHolding).where(MFHolding.snapshot_id == snap.id)).all():
        if h.amfi_code and h.units > 0:
            out[h.amfi_code].append(h)
    return dict(out)


def fund_peers(
    funds: dict[str, list[MFHolding]],
) -> dict[str, tuple[str, MFBenchmark | None]]:
    """{code: (name, benchmark)} for your held funds."""
    cfg = get_profiles().mf
    out: dict[str, tuple[str, MFBenchmark | None]] = {}
    for c, hs in funds.items():
        sch = _scheme(c)
        nm = sch.name if sch else hs[0].scheme_name
        cat = (sch.category if sch else None) or hs[0].category
        out[c] = (nm, benchmark_for(nm, cat, cfg))
    return out


def analyse_holdings(
    session: Session, provider: DataProvider, *, fetch: bool = False, now: datetime | None = None
) -> list[FundReport]:
    funds = held_funds(session)
    others = fund_peers(funds)
    return [
        analyse_fund(session, provider, c, holdings=hs, others=others, fetch=fetch, now=now)
        for c, hs in funds.items()
    ]


def set_expense_ratio(session: Session, code: str, pct: float | None) -> FundInfo:
    row = session.get(FundInfo, code) or FundInfo(amfi_code=code)
    row.expense_ratio_pct = pct
    row.updated_at = utcnow()
    session.add(row)
    session.commit()
    session.refresh(row)
    return row


def mf_refresh_targets(session: Session) -> tuple[list[tuple[str, str]], list[tuple[str, str]]]:
    """(extra NAV codes, benchmark tickers) the daily refresh should keep fresh for your funds:
    Direct twins of Regular plans, and each fund's category benchmark."""
    cfg = get_profiles().mf
    navs: dict[str, str] = {}
    benches: dict[str, str] = {}
    for c, hs in held_funds(session).items():
        sch = _scheme(c)
        if sch is None:
            continue
        twin = scheme_resolver().direct_twin(sch)
        if twin:
            navs[twin.code] = twin.name
        b = benchmark_for(sch.name, sch.category or hs[0].category, cfg)
        if b:
            benches[b.ticker] = b.label
    return list(navs.items()), list(benches.items())


# ---------------------------------------------------------------------------- charts


@dataclass
class RollingSeries:
    years: int
    starts: list[date]
    fund: list[float]
    benchmark: list[float]


@dataclass
class FundChart:
    code: str
    benchmark: MFBenchmark | None
    dates: list[date]
    fund: list[float]  # growth of 100
    bench: list[float | None]  # growth of 100, same dates; None before the index's history
    rolling: list[RollingSeries]
    notes: list[str]


def fund_chart(provider: DataProvider, code: str, years: int) -> FundChart:
    """NAV vs benchmark (both rebased to 100) over the last `years`, plus rolling-return
    series for the configured windows. Cached data only."""
    cfg = get_profiles().mf
    scheme = scheme_resolver().by_code.get(code)
    bench = benchmark_for(scheme.name, scheme.category, cfg) if scheme else None
    navs = provider.nav_history(code)
    notes: list[str] = []
    if not len(navs):
        return FundChart(code, bench, [], [], [], [], ["No NAV history downloaded yet"])
    navs = navs.copy()
    navs.index = pd.to_datetime(navs.index)
    cut = navs.index[-1] - pd.DateOffset(years=years)
    shown = navs.loc[navs.index >= cut]
    bclose = pd.Series(dtype=float)
    if bench is not None:
        bdf = provider.daily(bench.ticker).frame
        if not bdf.empty:
            bclose = bdf["close"].dropna()
            bclose.index = pd.to_datetime(bclose.index)
        else:
            notes.append(f"{bench.label} prices not downloaded yet")
    else:
        notes.append("No benchmark for this category")
    bvals: list[float | None] = []
    if len(bclose):
        aligned = bclose.reindex(shown.index.union(bclose.index)).ffill().reindex(shown.index)
        valid = aligned.dropna()
        if len(valid):
            # Rebase the fund and index at the first date both have.
            t0 = valid.index[0]
            shown = shown.loc[shown.index >= t0]
            aligned = aligned.loc[shown.index]
            bvals = [round(float(v / aligned.iloc[0] * 100), 2) for v in aligned]
    fund = [round(float(v / shown.iloc[0] * 100), 2) for v in shown]
    if not bvals:
        bvals = [None] * len(fund)
    rolling = []
    if len(bclose):
        for y in cfg.rolling_windows_years:
            rows = rolling_rows(navs, bclose, y, cfg.rolling_step_days)
            if rows:
                rolling.append(
                    RollingSeries(
                        y,
                        [r[0] for r in rows],
                        [round(r[1], 2) for r in rows],
                        [round(r[2], 2) for r in rows],
                    )
                )
    if bench is not None:
        notes.append(
            f"{bench.label} is a price index (no dividends), so it understates the index return"
        )
    return FundChart(code, bench, [d.date() for d in shown.index], fund, bvals, rolling, notes)
