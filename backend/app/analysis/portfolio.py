"""Portfolio analytics: value, P&L, day change, XIRR, allocation, concentration, beta,
correlation of top holdings, and performance vs Nifty 50.

Everything is built from cached data and your latest stock and fund snapshots. Where an input
is missing (no purchase dates, no NAV yet) the result says how much of the portfolio it covers
instead of filling the gap.
"""

from collections import defaultdict
from dataclasses import dataclass, field, replace
from datetime import date, datetime, timedelta

import pandas as pd
from sqlmodel import Session, col, select

from app.analysis.mf import asset_class_of, benchmark_for, held_funds, holding_cash_flows
from app.analysis.positions import Portfolio, load_portfolio
from app.analysis.returns import beta, xirr
from app.analysis.signals import active_profile
from app.core.formatting import now_ist
from app.core.profiles import get_profiles
from app.data.provider import DataProvider
from app.importers.reference import scheme_resolver, ticker_resolver
from app.models.tables import DailyBar, Snapshot

ETF_LARGE = ("nifty 50", "nifty50", "sensex", "nifty next 50", "nifty 100", "bees")


@dataclass(frozen=True)
class Slice:
    key: str
    label: str
    value: float
    weight: float
    limited: bool = True  # False for groups that aren't a sector (funds, ETFs, unknown)


# Sector slices that hold several sectors at once: the sector limit doesn't apply.
NOT_A_SECTOR = ("Mutual funds", "Unknown", "Index ETFs")


@dataclass(frozen=True)
class Holding:
    key: str  # Yahoo ticker or "mf:<AMFI code>"
    label: str
    kind: str  # "stock" | "etf" | "fund"
    value: float
    invested: float | None
    day_change: float | None
    series_kind: str  # "price" | "nav"
    code: str
    sector: str | None
    mcap: str
    asset_class: str


@dataclass
class PortfolioSummary:
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
    by_holding: list[Slice]
    by_sector: list[Slice]
    by_mcap: list[Slice]
    by_asset_class: list[Slice]
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
    snapshots: list[tuple[datetime, str, float | None]]
    notes: list[str] = field(default_factory=list)


def _prev_close(session: Session, ticker: str) -> tuple[float, float, date] | None:
    bars = session.exec(
        select(DailyBar)
        .where(DailyBar.ticker == ticker, col(DailyBar.close).is_not(None))
        .order_by(col(DailyBar.date).desc())
        .limit(2)
    ).all()
    if len(bars) < 2 or bars[0].close is None or bars[1].close is None:
        return None
    return bars[0].close, bars[1].close, bars[0].date


def stock_mcap(
    provider: DataProvider, ticker: str, label: str, cfg_large: float, cfg_mid: float
) -> str:
    symbol = ticker.removesuffix(".NS") if ticker.endswith(".NS") else None
    sec = ticker_resolver().by_symbol.get(symbol) if symbol else None
    if sec is not None and sec.kind == "etf":
        return "Large cap" if any(k in label.lower() for k in ETF_LARGE) else "Unknown"
    raw = provider.fundamentals(ticker)
    mc = raw.info.get("marketCap") if raw else None
    if not isinstance(mc, (int, float)) or mc <= 0:
        return "Unknown"
    cr = mc / 1e7
    if cr >= cfg_large:
        return "Large cap"
    if cr >= cfg_mid:
        return "Mid cap"
    return "Small cap"


def fund_mcap(name: str, category: str | None, acls: str) -> str:
    if acls == "debt":
        return "Debt (not equity)"
    if acls == "hybrid":
        return "Hybrid funds"
    if acls == "other":
        return "Other funds"
    b = benchmark_for(name, category, get_profiles().mf)
    lab = (b.label if b else "").lower()
    if "smallcap" in lab:
        return "Small cap"
    if "midcap" in lab and "large" not in lab:
        return "Mid cap"
    if lab in ("nifty 50", "nifty next 50", "nifty bank"):
        return "Large cap"
    return "Multi-cap funds"


def _slices(
    values: dict[str, float], total: float, labels: dict[str, str] | None = None
) -> list[Slice]:
    if total <= 0:
        return []
    out = [
        Slice(k, (labels or {}).get(k, k), round(v, 2), round(v / total, 4))
        for k, v in values.items()
        if v > 0
    ]
    return sorted(out, key=lambda s: -s.value)


def build_holdings(
    session: Session, provider: DataProvider, now: datetime
) -> tuple[list[Holding], Portfolio, list[str]]:
    p = get_profiles()
    pc = p.portfolio
    notes: list[str] = []
    pf = load_portfolio(session, provider, p.rebalance, now)
    notes += [n for n in pf.notes if "whole portfolio" not in n]
    out: list[Holding] = []
    for t, pos in pf.positions.items():
        if pos.value is None:
            continue
        pv = _prev_close(session, t)
        dc = pos.quantity * (pv[0] - pv[1]) if pv else None
        symbol = t.removesuffix(".NS") if t.endswith(".NS") else None
        sec = ticker_resolver().by_symbol.get(symbol) if symbol else None
        etf = sec is not None and sec.kind == "etf"
        out.append(
            Holding(
                key=t,
                label=pos.label,
                kind="etf" if etf else "stock",
                value=pos.value,
                invested=pos.invested,
                day_change=dc,
                series_kind="price",
                code=t,
                sector=pos.sector if not etf else "Index ETFs",
                mcap=stock_mcap(provider, t, pos.label, pc.large_cap_min_cr, pc.mid_cap_min_cr),
                asset_class="Stocks & ETFs",
            )
        )
    for code, hs in held_funds(session).items():
        sch = scheme_resolver().by_code.get(code)
        name = sch.name if sch else hs[0].scheme_name
        cat = (sch.category if sch else None) or hs[0].category
        acls = asset_class_of(cat, p.mf)
        ln = provider.latest_nav(code)
        units = sum(h.units for h in hs)
        if ln.nav is not None:
            value: float | None = units * ln.nav
        else:
            vals = [h.current_value for h in hs]
            value = (
                sum(v for v in vals if v is not None) if all(v is not None for v in vals) else None
            )
        if value is None:
            notes.append(f"{name}: no NAV or value yet, left out")
            continue
        inv = [h.invested for h in hs]
        out.append(
            Holding(
                key=f"mf:{code}",
                label=name,
                kind="fund",
                value=value,
                invested=sum(v for v in inv if v is not None)
                if all(v is not None for v in inv)
                else None,
                day_change=(
                    units * (ln.nav - ln.previous_nav)
                    if ln.nav is not None and ln.previous_nav is not None
                    else None
                ),
                series_kind="nav",
                code=code,
                sector=None,
                mcap=fund_mcap(name, cat, acls),
                asset_class={
                    "equity": "Equity funds",
                    "debt": "Debt funds",
                    "hybrid": "Hybrid funds",
                }.get(acls, "Other funds"),
            )
        )
    return out, pf, notes


def _series(provider: DataProvider, h: Holding) -> pd.Series:
    if h.series_kind == "nav":
        s = provider.nav_history(h.code)
    else:
        df = provider.daily(h.code).frame
        s = df["close"] if not df.empty else pd.Series(dtype=float)
    s = s.dropna()
    s.index = pd.to_datetime(s.index)
    return s.sort_index()


def summarise(
    session: Session, provider: DataProvider, now: datetime | None = None
) -> PortfolioSummary:
    p = get_profiles()
    pc = p.portfolio
    _, risk_key, _ = active_profile(session)
    risk = p.risk_levels[risk_key]
    now = now or now_ist()
    today = now.date()
    holdings, pf, notes = build_holdings(session, provider, now)
    total = sum(h.value for h in holdings)
    stock_value = sum(h.value for h in holdings if h.kind != "fund")
    fund_value = total - stock_value

    # Invested and P&L: only when every holding's cost is known.
    missing_cost = [h.label for h in holdings if h.invested is None]
    invested = None if missing_cost or not holdings else sum(h.invested or 0 for h in holdings)
    invested_note = (
        f"Invested amount unknown for {len(missing_cost)} holding(s) ({', '.join(missing_cost[:3])}"
        + ("…" if len(missing_cost) > 3 else "")
        + "): P&L is left out rather than understated."
        if missing_cost
        else None
    )
    pnl = None if invested is None else total - invested
    pnl_pct = None if pnl is None or not invested else pnl / invested * 100

    missing_day = [h for h in holdings if h.day_change is None]
    day = sum(h.day_change for h in holdings if h.day_change is not None)
    day_note = (
        f"{len(missing_day)} holding(s) have no previous price/NAV and are left out of the "
        "day change."
        if missing_day
        else None
    )
    base_prev = total - day
    day_pct = day / base_prev * 100 if base_prev > 0 and holdings else None

    # XIRR over holdings with dated cash flows.
    flows: list[tuple[date, float]] = []
    covered = 0.0
    approx = False
    for pos in pf.positions.values():
        dated = [lot for lot in pos.lots if lot.purchase_date]
        if not dated or pos.price is None:
            continue
        q = sum(lot.quantity for lot in dated)
        for lot in dated:
            flows.append((lot.purchase_date, -lot.quantity * lot.avg_price))  # type: ignore[arg-type]
        flows.append((today, q * pos.price))
        covered += q * pos.price
    funds = held_funds(session)
    by_key = {h.key: h for h in holdings}
    for code, hs in funds.items():
        h = by_key.get(f"mf:{code}")
        if h is None:
            continue
        f, from_txn = holding_cash_flows(session, hs)
        if not f:
            continue
        approx = approx or not from_txn
        flows += f
        flows.append((today, h.value))
        covered += h.value
    cov = covered / total if total > 0 else 0.0
    x = xirr(flows) if flows else None
    if x is None:
        xbasis = (
            "Not available: needs purchase dates for stocks (manual entry) or a detailed CAS "
            "for funds."
        )
    else:
        xbasis = f"Covers {cov * 100:.0f}% of your portfolio (holdings with dated purchases)"
        if approx:
            xbasis += (
                "; funds without a detailed CAS assume one lump sum on the first purchase date"
            )
        if cov < pc.xirr_min_coverage:
            xbasis += ". Partial: treat with care"

    # Allocation
    by_holding = _slices(
        {h.key: h.value for h in holdings}, total, {h.key: h.label for h in holdings}
    )
    sectors: dict[str, float] = defaultdict(float)
    mcaps: dict[str, float] = defaultdict(float)
    classes: dict[str, float] = defaultdict(float)
    for h in holdings:
        sectors[
            h.sector or ("Mutual funds (not split by sector)" if h.kind == "fund" else "Unknown")
        ] += h.value
        mcaps[h.mcap] += h.value
        classes[h.asset_class] += h.value

    warnings: list[str] = []
    for s in by_holding:
        h = by_key[s.key]
        if h.kind != "fund" and s.weight > risk.max_weight_per_stock:
            warnings.append(
                f"{s.label} is {s.weight * 100:.1f}% of your portfolio, above your "
                f"{risk.max_weight_per_stock * 100:g}% limit per stock ({risk.label} risk)"
            )
    for name, v in sectors.items():
        w = v / total if total else 0
        if not name.startswith(NOT_A_SECTOR) and w > risk.max_weight_per_sector:
            warnings.append(
                f"{name} is {w * 100:.1f}% of your portfolio, above your "
                f"{risk.max_weight_per_sector * 100:g}% sector limit"
            )
    top = by_holding[: pc.top_n_concentration]
    if len(by_holding) > pc.top_n_concentration:
        warnings_top = sum(s.weight for s in top)
        notes.append(
            f"Your top {len(top)} holdings are {warnings_top * 100:.0f}% of the portfolio."
        )
    segs: dict[str, list[str]] = defaultdict(list)
    for code, hs in funds.items():
        sch = scheme_resolver().by_code.get(code)
        nm = sch.name if sch else hs[0].scheme_name
        b = benchmark_for(nm, (sch.category if sch else None) or hs[0].category, p.mf)
        if b:
            segs[b.label].append(nm)
    for lab, names in segs.items():
        if len(names) > p.mf.duplicate_category_max:
            warnings.append(f"{len(names)} funds in the same segment ({lab}): {', '.join(names)}")

    # Beta (value-weighted) vs Nifty 50
    nifty_t = p.data.benchmarks["nifty50"]
    nifty = provider.daily(nifty_t).frame
    nclose = nifty["close"] if not nifty.empty else pd.Series(dtype=float)
    series = {h.key: _series(provider, h) for h in holdings}
    bsum = 0.0
    bcov = 0.0
    for h in holdings:
        hb, _n = beta(
            series[h.key], nclose, p.scoring.beta_lookback_sessions, p.scoring.beta_min_sessions
        )
        if hb is not None:
            bsum += hb * h.value
            bcov += h.value
    port_beta = round(bsum / bcov, 2) if bcov > 0 else None
    beta_cov = bcov / total if total > 0 else 0.0
    beta_basis = (
        f"Value-weighted beta of daily returns vs Nifty 50 over up to "
        f"{p.scoring.beta_lookback_sessions} sessions; covers {beta_cov * 100:.0f}% of the "
        "portfolio"
        if port_beta is not None
        else "Not available yet: needs a year of prices/NAVs alongside Nifty 50"
    )

    # Correlation of the top holdings' daily returns
    top_h = [by_key[s.key] for s in by_holding[: pc.correlation_top_n]]
    ret_map = {h.label: series[h.key].pct_change() for h in top_h if len(series[h.key]) > 2}
    rets = pd.concat(ret_map, axis=1, sort=True) if ret_map else pd.DataFrame()
    rets = rets.dropna(how="all").iloc[-pc.correlation_lookback_sessions :]
    labels: list[str] = list(rets.columns)
    corr: list[list[float | None]] = []
    if labels:
        cm = rets.corr(min_periods=60)
        corr = [
            [None if pd.isna(v) else round(float(v), 2) for v in cm.loc[a, labels]] for a in labels
        ]
    corr_basis = (
        f"Daily returns over the last {pc.correlation_lookback_sessions} sessions; blank where two "
        "series share fewer than 60 days"
    )

    # Performance vs Nifty 50: your current holdings, held throughout
    snaps = list(session.exec(select(Snapshot).order_by(col(Snapshot.created_at))).all())
    first = snaps[0].created_at.date() if snaps else today
    hypothetical = (today - first).days < pc.performance_min_days
    start = today - timedelta(days=pc.performance_fallback_days) if hypothetical else first
    cut = {h.key: series[h.key].loc[pd.Timestamp(start) :] for h in holdings if len(series[h.key])}
    frame = pd.concat(cut, axis=1, sort=True) if cut else pd.DataFrame()
    qty: dict[str, float] = {}
    for h in holdings:
        ser = series.get(h.key)
        if ser is not None and len(ser):
            qty[h.key] = h.value / float(ser.iloc[-1])
    dates: list[date] = []
    port_idx: list[float] = []
    nifty_idx: list[float] = []
    perf_basis = "Not available yet: no price history cached"
    if not frame.empty and not nclose.empty:
        frame = frame.ffill()
        complete = frame.dropna()  # start where every holding has a price/NAV
        if not complete.empty:
            vals = sum(complete[k] * q for k, q in qty.items() if k in complete)
            nf = nclose.copy()
            nf.index = pd.to_datetime(nf.index)
            nf = nf.reindex(complete.index).ffill().dropna()
            common = vals.index.intersection(nf.index)
            if len(common) > 1:
                v = vals.loc[common]
                n_ = nf.loc[common]
                dates = [d.date() for d in common]
                port_idx = [round(float(x), 2) for x in (v / v.iloc[0] * 100)]
                nifty_idx = [round(float(x), 2) for x in (n_ / n_.iloc[0] * 100)]
                since = dates[0]
                perf_basis = (
                    f"Your current holdings, held unchanged since {since:%d %b %Y}"
                    + (
                        f" (your first import was under {pc.performance_min_days} days ago, so the "
                        "last year is shown)"
                        if hypothetical
                        else " (your first import)"
                    )
                    + ". Not your actual trading history: buys and sells in between aren't known."
                )
                if since > start + timedelta(days=7):
                    perf_basis += f" Starts {since:%d %b %Y}, when every holding has data."
    as_of_dates = [
        d for h in holdings if len(series[h.key]) for d in [series[h.key].index[-1].date()]
    ]
    return PortfolioSummary(
        as_of=max(as_of_dates) if as_of_dates else None,
        total_value=round(total, 2),
        stock_value=round(stock_value, 2),
        fund_value=round(fund_value, 2),
        invested=None if invested is None else round(invested, 2),
        invested_note=invested_note,
        pnl=None if pnl is None else round(pnl, 2),
        pnl_pct=None if pnl_pct is None else round(pnl_pct, 2),
        day_change=round(day, 2) if holdings else None,
        day_change_pct=None if day_pct is None else round(day_pct, 2),
        day_change_note=day_note,
        xirr=x,
        xirr_coverage=round(cov, 3),
        xirr_basis=xbasis,
        by_holding=by_holding,
        by_sector=[
            replace(x, limited=not x.key.startswith(NOT_A_SECTOR))
            for x in _slices(dict(sectors), total)
        ],
        by_mcap=_slices(dict(mcaps), total),
        by_asset_class=_slices(dict(classes), total),
        warnings=warnings,
        beta=port_beta,
        beta_coverage=round(beta_cov, 3),
        beta_basis=beta_basis,
        correlation_labels=labels,
        correlation=corr,
        correlation_basis=corr_basis,
        performance_dates=dates,
        performance_portfolio=port_idx,
        performance_nifty=nifty_idx,
        performance_basis=perf_basis,
        snapshots=[(s.created_at, s.kind, s.total_value) for s in snaps],
        notes=notes,
    )
