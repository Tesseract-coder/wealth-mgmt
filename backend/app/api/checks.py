"""Score Shape: pass/fail checks per section and the 0–6 axis scores built from them
(config/checks.yaml), for stocks, funds and the whole portfolio, plus the yearly figures behind
the stock page's charts. Read-only views over the existing analysis; no score or signal changes."""

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from sqlmodel import Session

from app.analysis.checks import (
    HoldingFacts,
    ShapeResult,
    WeekChange,
    evaluate_fund,
    evaluate_stock,
    get_checks,
    portfolio_notes,
    portfolio_shape,
    week_change,
)
from app.analysis.financials import financial_history
from app.analysis.fundamental import analyse_fundamentals
from app.analysis.mf import FundReport, analyse_fund, analyse_holdings, fund_peers, held_funds
from app.analysis.positions import load_portfolio
from app.analysis.signals import (
    SIGNAL_LABEL,
    active_profile,
    analyse_stock,
    holdings_analysis,
    resolve_style,
)
from app.analysis.valuation import FairValue, fair_value, pe_history
from app.api.funds import CODE
from app.api.market import TICKER
from app.core.db import get_session
from app.core.formatting import format_inr
from app.core.profiles import RiskKey, StyleKey, get_profiles
from app.data.provider import CachedProvider
from app.importers.reference import scheme_resolver
from app.models.schemas import (
    AxisAverageOut,
    AxisDefOut,
    CheckOut,
    ChecksConfigOut,
    FairValueMethodOut,
    FairValueOut,
    FinancialHistoryOut,
    FinancialQuarterOut,
    FinancialYearOut,
    FundChecksOut,
    FundHoldingsChecksOut,
    HoldingsChecksOut,
    HoldingShapeOut,
    PortfolioShapeOut,
    SectionOut,
    StockChecksOut,
    WeekChangeOut,
    YearPEOut,
)

router = APIRouter(prefix="/analysis", tags=["score shape"])


def shape_fields(r: ShapeResult) -> dict[str, object]:
    return {
        "sections": [
            SectionOut(
                key=s.key,
                label=s.label,
                question=s.question,
                caption=s.caption,
                checks=[CheckOut(**c.__dict__) for c in s.checks],
                passed=s.passed,
                with_data=s.with_data,
                score=s.score,
                note=s.note,
            )
            for s in r.sections
        ],
        "axes": r.axes,
        "total": r.total,
        "max_total": r.max_total,
        "axis_max": r.axis_max,
        "step": r.step,
        "checks_total": r.checks_total,
        "checks_with_data": r.checks_with_data,
        "confidence": r.confidence,
        "confidence_reason": r.confidence_reason,
        "rewards": r.rewards,
        "risks": r.risks,
        "summary": r.summary,
    }


def fair_value_out(fv: FairValue | None) -> FairValueOut | None:
    if fv is None:
        return None
    return FairValueOut(
        value=fv.value,
        price=fv.price,
        gap_pct=fv.gap_pct,
        methods=[FairValueMethodOut(**m.__dict__) for m in fv.methods],
        caveat=fv.caveat,
    )


def week_change_out(wc: WeekChange | None) -> WeekChangeOut | None:
    if wc is None:
        return None
    return WeekChangeOut(
        since=wc.since,
        axes=wc.axes,
        total=wc.total,
        previous_signal=wc.previous_signal,
        previous_signal_label=SIGNAL_LABEL.get(wc.previous_signal) if wc.previous_signal else None,
        signal_changed=wc.signal_changed,
    )


def _strongest_weakest(r: ShapeResult) -> list[str]:
    scored = [s for s in r.sections if s.score is not None]
    if not scored:
        return []
    best = max(scored, key=lambda s: s.score or 0)
    worst = min(scored, key=lambda s: s.score or 0)
    out = [f"Strongest: {best.label} {best.score}/{r.axis_max}"]
    if worst is not best and worst.score != best.score:
        out.append(f"Weakest: {worst.label} {worst.score}/{r.axis_max}")
    return out


@router.get("/checks/config", response_model=ChecksConfigOut)
def checks_config() -> ChecksConfigOut:
    """The axes (sections) of the stock and fund shapes, in order, and the colour steps."""
    cfg = get_checks()
    return ChecksConfigOut(
        axis_max=cfg.axis.max,
        score_steps=cfg.axis.score_steps,
        stock=[
            AxisDefOut(key=k, label=s.label, question=s.question, caption=s.caption)
            for k, s in cfg.stock.items()
        ],
        fund=[
            AxisDefOut(key=k, label=s.label, question=s.question, caption=s.caption)
            for k, s in cfg.fund.items()
        ],
    )


@router.get("/stock/{ticker}/checks", response_model=StockChecksOut)
def stock_checks(
    ticker: str = Path(pattern=TICKER, description="Yahoo ticker, e.g. RELIANCE.NS"),
    style: StyleKey | None = Query(None, description="Defaults to your saved style"),
    risk: RiskKey | None = Query(None, description="Defaults to your saved risk level"),
    fetch: bool = Query(True, description="Fetch missing or stale data first"),
    session: Session = Depends(get_session),
) -> StockChecksOut:
    """Every check for one stock, its Score Shape, Rewards and Risks, a plain-English summary,
    the fair-value estimate and the change since about a week ago.

    Style only affects the signal shown alongside; the checks depend on your risk level
    (debt limit) but never on style."""
    st, rk, ctw = active_profile(session, style, risk)
    provider = CachedProvider(session)
    pf = load_portfolio(session, provider, get_profiles().rebalance)
    t = ticker.upper()
    sig = analyse_stock(
        session,
        provider,
        t,
        style=st,
        risk_key=rk,
        custom_technical_weight=ctw,
        portfolio=pf,
        fetch=fetch,
    )
    r = evaluate_stock(sig, provider.daily(t).frame)
    return StockChecksOut(
        **shape_fields(r),
        ticker=t,
        label=sig.label,
        sector=sig.sector,
        is_financial=sig.fundamental.is_financial,
        style=sig.style,
        style_label=sig.style_label,
        risk=sig.risk,
        risk_label=sig.risk_label,
        signal=sig.signal,
        signal_label=sig.signal_label,
        fair_value=fair_value_out(r.fair_value),
        pe_history=[YearPEOut(**p.__dict__) for p in r.pe_history],
        week_change=week_change_out(week_change(session, t, sig.risk, sig.style, r, sig.signal)),
        disclaimer=get_profiles().disclaimer,
    )


@router.get("/checks/holdings", response_model=HoldingsChecksOut)
def holdings_checks(
    style: StyleKey | None = Query(None, description="Defaults to your saved style"),
    risk: RiskKey | None = Query(None, description="Defaults to your saved risk level"),
    session: Session = Depends(get_session),
) -> HoldingsChecksOut:
    """Each stock holding's shape, the portfolio's value-weighted shape, and Rewards and Risks
    for the whole portfolio. Cached data only (no network)."""
    st, rk, ctw = active_profile(session, style, risk)
    p = get_profiles()
    style_key, notes = resolve_style(st)
    provider = CachedProvider(session)
    a = holdings_analysis(session, provider, style_key, rk, ctw)
    pf = a.portfolio
    facts: list[HoldingFacts] = []
    out: list[HoldingShapeOut] = []
    for s, r in zip(a.signals, a.shapes(provider), strict=True):
        value = s.position.value if s.position and s.position.value is not None else 0.0
        facts.append(
            HoldingFacts(s.label, value, r, s.signal, s.signal_label, s.weight, s.max_weight)
        )
        out.append(
            HoldingShapeOut(
                ticker=s.ticker,
                label=s.label,
                sector=s.sector,
                value=round(value, 2) if value else None,
                weight=None if s.weight is None else round(s.weight, 4),
                signal=s.signal,
                signal_label=s.signal_label,
                axes=r.axes,
                total=r.total,
                max_total=r.max_total,
                step=r.step,
                confidence=r.confidence,
                top=_strongest_weakest(r),
            )
        )
    shape = portfolio_shape([(f.value, f.shape) for f in facts])
    risk_level = p.risk_levels[rk]
    sectors = [
        (name, v / pf.total, risk_level.max_weight_per_sector)
        for name, v in sorted(pf.sector_values.items(), key=lambda x: -x[1])
        if pf.total > 0
    ]
    rewards, risks = portfolio_notes(facts, sectors)
    if pf.fund_value > 0:
        notes.append(
            f"The portfolio shape covers your stocks ({format_inr(pf.stock_value, 0)}). "
            "Mutual funds "
            f"({format_inr(pf.fund_value, 0)}) have their own shapes on the Mutual Funds page."
        )
    return HoldingsChecksOut(
        style=style_key,
        style_label=p.styles[style_key].label,
        risk=rk,
        risk_label=risk_level.label,
        portfolio=PortfolioShapeOut(
            axes=[AxisAverageOut(**a.__dict__) for a in shape.axes],
            total=shape.total,
            max_total=shape.max_total,
            axis_max=shape.axis_max,
            step=shape.step,
            stock_value=shape.stock_value,
            holdings=shape.holdings,
        ),
        holdings=out,
        rewards=rewards,
        risks=risks,
        notes=notes,
        disclaimer=p.disclaimer,
    )


@router.get("/fundamental/{ticker}/history", response_model=FinancialHistoryOut)
def fundamental_history(
    ticker: str = Path(pattern=TICKER, description="Yahoo ticker, e.g. RELIANCE.NS"),
    fetch: bool = Query(True, description="Fetch Yahoo fundamentals if missing or stale"),
    session: Session = Depends(get_session),
) -> FinancialHistoryOut:
    """Yearly revenue, profit, margins, debt, equity, cash, free cash flow, dividends and the P/E
    at each year-end, plus recent quarters: the data behind the stock page's charts (₹ crore)."""
    provider = CachedProvider(session)
    t = ticker.upper()
    rep = analyse_fundamentals(session, provider, t, fetch=fetch)
    if fetch:  # year-end closes for the P/E history (usually cached already)
        provider.ensure_daily(t, rep.label)
    daily = provider.daily(t).frame
    closes = daily.get("close")
    price = float(closes.iloc[-1]) if closes is not None and len(closes) else None
    annual = rep.statements.annual if rep.statements is not None else None
    inr = rep.currency == "INR"
    points = pe_history(annual, closes, rep.metrics, price) if closes is not None and inr else []
    years, quarters = financial_history(rep, points)
    fv, why = fair_value(rep.metrics, annual if inr else None, price, rep.is_financial)
    notes = list(rep.notes)
    if not inr:
        notes.append(
            f"Statements are in {rep.currency}: amounts are {rep.currency} crore, and the P/E "
            "history is left out (prices are in rupees)."
        )
    if fv is None and rep.applicable:
        notes.append(f"Fair value estimate not available: {why}.")
    if not years:
        notes.append("No yearly statements cached for this stock yet.")
    return FinancialHistoryOut(
        ticker=t,
        label=rep.label,
        sector=rep.sector,
        is_financial=rep.is_financial,
        source=rep.source,
        unit="₹ Cr" if inr else f"{rep.currency} Cr",
        years=[FinancialYearOut(**y.__dict__) for y in years],
        quarters=[FinancialQuarterOut(**q.__dict__) for q in quarters],
        fair_value=fair_value_out(fv),
        notes=notes,
        disclaimer=get_profiles().disclaimer,
    )


def fund_checks_out(r_fund: FundReport, shape: ShapeResult) -> FundChecksOut:
    return FundChecksOut(
        **shape_fields(shape),
        code=r_fund.code,
        name=r_fund.name,
        category=r_fund.category,
        signal=r_fund.signal,
        signal_label=r_fund.signal_label,
        disclaimer=get_profiles().disclaimer,
    )


# Before /mf/{code}/checks, or "holdings" would be read as a scheme code.
@router.get("/mf/holdings/checks", response_model=FundHoldingsChecksOut)
def fund_holdings_checks(session: Session = Depends(get_session)) -> FundHoldingsChecksOut:
    """The shape and checks for every fund you hold (cached data only)."""
    reports = analyse_holdings(session, CachedProvider(session))
    return FundHoldingsChecksOut(
        funds=[fund_checks_out(r, evaluate_fund(r)) for r in reports],
        disclaimer=get_profiles().disclaimer,
    )


@router.get("/mf/{code}/checks", response_model=FundChecksOut)
def fund_checks(
    code: str = Path(pattern=CODE, description="AMFI scheme code"),
    fetch: bool = Query(True, description="Fetch NAVs and the benchmark if missing or stale"),
    session: Session = Depends(get_session),
) -> FundChecksOut:
    """One fund's checks: returns and consistency vs its benchmark, risk, risk-adjusted return
    and cost, as a 5-axis shape."""
    if code not in scheme_resolver().by_code:
        raise HTTPException(404, f"AMFI scheme code {code} not found")
    funds = held_funds(session)
    r = analyse_fund(
        session,
        CachedProvider(session),
        code,
        holdings=funds.get(code),
        others=fund_peers(funds),
        fetch=fetch,
    )
    return fund_checks_out(r, evaluate_fund(r))
