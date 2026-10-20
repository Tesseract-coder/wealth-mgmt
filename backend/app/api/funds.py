"""Mutual fund analysis and portfolio-level analytics."""

from datetime import date, timedelta

from fastapi import APIRouter, Depends, File, Form, HTTPException, Path, Query, UploadFile
from sqlmodel import Session

from app.analysis.actions import action_list
from app.analysis.mf import (
    FundReport,
    analyse_fund,
    analyse_holdings,
    fund_chart,
    fund_peers,
    held_funds,
    load_fund_portfolio,
    overlap,
    set_expense_ratio,
)
from app.analysis.portfolio import PortfolioSummary, summarise
from app.analysis.returns import RiskStats
from app.api.imports import _read, _user_mapping, needs_mapping_out
from app.api.market import fr_out
from app.core.db import get_session
from app.core.formatting import now_ist
from app.core.memo import Memo
from app.core.profiles import get_profiles
from app.data.provider import CachedProvider
from app.importers.fund_portfolio import import_fund_portfolio
from app.importers.groww import NeedsMapping
from app.importers.reference import scheme_resolver
from app.importers.tabular import ImportFileError
from app.models.schemas import (
    ActionOut,
    ActionsOut,
    BenchmarkOut,
    ExpenseRatioIn,
    FundChartOut,
    FundPortfolioImportedOut,
    FundReasonOut,
    FundReportOut,
    MFHoldingsAnalysisOut,
    MyFundHoldingOut,
    NeedsMappingOut,
    OverlapMatrixOut,
    OverlapOut,
    PeriodReturnOut,
    PortfolioSummaryOut,
    RiskStatsOut,
    RollingOut,
    RollingSeriesOut,
    SchemeRefOut,
    SliceOut,
    SnapshotPointOut,
)

router = APIRouter(tags=["mutual funds & portfolio"])
CODE = r"^\d{3,7}$"


def _risk(r: RiskStats | None) -> RiskStatsOut | None:
    return RiskStatsOut(**r.__dict__) if r else None


def fund_out(r: FundReport) -> FundReportOut:
    return FundReportOut(
        code=r.code,
        name=r.name,
        amc=r.amc,
        category=r.category,
        asset_class=r.asset_class,
        plan=r.plan,
        option=r.option,
        nav=r.nav,
        nav_date=r.nav_date,
        previous_nav=r.previous_nav,
        nav_freshness=fr_out(r.nav_freshness),
        history_start=r.history_start,
        holding=MyFundHoldingOut(**r.holding.__dict__) if r.holding else None,
        returns=[
            PeriodReturnOut(years=y, fund=r.returns.get(y), benchmark=r.benchmark_returns.get(y))
            for y in sorted(r.returns)
        ],
        benchmark=BenchmarkOut(ticker=r.benchmark.ticker, label=r.benchmark.label)
        if r.benchmark
        else None,
        risk=_risk(r.risk),
        benchmark_risk=_risk(r.benchmark_risk),
        rolling=[RollingOut(**x.__dict__) for x in r.rolling],
        direct_twin=SchemeRefOut(code=r.direct_twin.code, name=r.direct_twin.name)
        if r.direct_twin
        else None,
        direct_gap_pp=r.direct_gap_pp,
        direct_gap_basis=r.direct_gap_basis,
        expense_ratio_pct=r.expense_ratio_pct,
        overlaps=[OverlapOut(**o.__dict__) for o in r.overlaps],
        segment_peers=r.segment_peers,
        signal=r.signal,
        signal_label=r.signal_label,
        rule=r.rule,
        reasons=[FundReasonOut(**x.__dict__) for x in r.reasons],
        notes=r.notes,
        unavailable=r.unavailable,
        fetch_errors=r.fetch_errors,
        disclaimer=get_profiles().disclaimer,
    )


@router.get("/analysis/mf/holdings", response_model=MFHoldingsAnalysisOut)
def mf_holdings(session: Session = Depends(get_session)) -> MFHoldingsAnalysisOut:
    """Every fund you hold with its signal, plus the overlap matrix (cached data only)."""
    p = get_profiles()
    reports = analyse_holdings(session, CachedProvider(session))
    codes = [r.code for r in reports]
    ports = {c: load_fund_portfolio(session, c) for c in codes}
    today = now_ist().date()
    matrix: list[list[float | None]] = []
    approx = False
    for a in codes:
        row: list[float | None] = []
        for b in codes:
            pa, pb = ports[a], ports[b]
            if a == b:
                row.append(100.0 if pa else None)
            elif pa is None or pb is None:
                row.append(None)
            else:
                pct, _, ap, _ = overlap(pa, pb, p.mf, today)
                approx = approx or ap
                row.append(pct)
        matrix.append(row)
    warnings: list[str] = []
    seen: set[str] = set()
    for r in reports:
        if (
            r.benchmark
            and len(r.segment_peers) + 1 > p.mf.duplicate_category_max
            and r.benchmark.label not in seen
        ):
            seen.add(r.benchmark.label)
            warnings.append(
                f"{len(r.segment_peers) + 1} funds in the same segment ({r.benchmark.label}): "
                + ", ".join([r.name, *r.segment_peers])
            )
        if r.plan == "regular":
            warnings.append(f"{r.name} is a Regular plan: a Direct plan costs less.")
    if reports and all(v is None for row in matrix for i, v in enumerate(row)):
        warnings.append(
            "Overlap needs each fund's portfolio holdings: upload the AMC's monthly portfolio "
            "file for each fund (Import → Fund portfolios)."
        )
    return MFHoldingsAnalysisOut(
        funds=[fund_out(r) for r in reports],
        overlap=OverlapMatrixOut(
            codes=codes, names=[r.name for r in reports], pct=matrix, approximate=approx
        ),
        warnings=warnings,
        disclaimer=p.disclaimer,
    )


@router.get("/analysis/mf/{scheme_code}", response_model=FundReportOut)
def mf_report(
    scheme_code: str = Path(pattern=CODE, description="AMFI scheme code"),
    fetch: bool = Query(True, description="Fetch NAVs and the benchmark if missing or stale"),
    session: Session = Depends(get_session),
) -> FundReportOut:
    if scheme_code not in scheme_resolver().by_code:
        raise HTTPException(404, f"AMFI scheme code {scheme_code} not found")
    funds = held_funds(session)
    r = analyse_fund(
        session,
        CachedProvider(session),
        scheme_code,
        holdings=funds.get(scheme_code),
        others=fund_peers(funds),
        fetch=fetch,
    )
    return fund_out(r)


@router.get("/analysis/mf/{scheme_code}/chart", response_model=FundChartOut)
def mf_chart(
    scheme_code: str = Path(pattern=CODE),
    years: int = Query(5, ge=1, le=30, description="How far back the NAV chart goes"),
    session: Session = Depends(get_session),
) -> FundChartOut:
    """NAV vs benchmark (growth of 100) and rolling returns, from cached data."""
    if scheme_code not in scheme_resolver().by_code:
        raise HTTPException(404, f"AMFI scheme code {scheme_code} not found")
    c = fund_chart(CachedProvider(session), scheme_code, years)
    return FundChartOut(
        code=c.code,
        benchmark=BenchmarkOut(ticker=c.benchmark.ticker, label=c.benchmark.label)
        if c.benchmark
        else None,
        dates=c.dates,
        fund=c.fund,
        bench=c.bench,
        rolling=[RollingSeriesOut(**r.__dict__) for r in c.rolling],
        notes=c.notes,
    )


@router.put("/analysis/mf/{scheme_code}/expense-ratio", response_model=FundReportOut)
def put_expense_ratio(
    body: ExpenseRatioIn,
    scheme_code: str = Path(pattern=CODE),
    session: Session = Depends(get_session),
) -> FundReportOut:
    """Save the fund's expense ratio (TER, %) from its factsheet; null clears it."""
    if scheme_code not in scheme_resolver().by_code:
        raise HTTPException(404, f"AMFI scheme code {scheme_code} not found")
    set_expense_ratio(session, scheme_code, body.expense_ratio_pct)
    return mf_report(scheme_code, False, session)


@router.post("/import/fund-portfolio", response_model=FundPortfolioImportedOut | NeedsMappingOut)
async def import_fund_portfolio_file(
    file: UploadFile = File(..., description="AMC monthly portfolio / factsheet (.xlsx or .csv)"),
    amfi_code: str = Form(..., description="Which of your funds this file is for"),
    as_of: date | None = Form(None, description="Portfolio date, e.g. 2026-09-30"),
    sheet: str | None = Form(None, description="Sheet name, if the workbook has one per scheme"),
    mapping: str | None = Form(None, description="ColumnMappingIn JSON"),
    session: Session = Depends(get_session),
) -> FundPortfolioImportedOut | NeedsMappingOut:
    content = await _read(file)
    try:
        res = import_fund_portfolio(
            session,
            content,
            file.filename or "portfolio.xlsx",
            amfi_code,
            as_of=as_of,
            sheet=sheet,
            user=_user_mapping(mapping),
        )
    except (ImportFileError, ValueError) as e:
        raise HTTPException(400, str(e)) from None
    if isinstance(res, NeedsMapping):
        return needs_mapping_out("fund_portfolio", res)
    return FundPortfolioImportedOut(**res.__dict__)


_summaries: Memo[PortfolioSummary] = Memo("portfolio summary", timedelta(minutes=5), size=2)


@router.get("/portfolio/summary", response_model=PortfolioSummaryOut)
def portfolio_summary(session: Session = Depends(get_session)) -> PortfolioSummaryOut:
    """Value, P&L, day change, XIRR, allocation, concentration, beta, correlation and
    performance vs Nifty 50, from cached data."""
    s = _summaries.get(session, "summary", lambda ses: summarise(ses, CachedProvider(ses)))
    d = {
        k: v
        for k, v in s.__dict__.items()
        if k not in ("by_holding", "by_sector", "by_mcap", "by_asset_class", "snapshots")
    }
    return PortfolioSummaryOut(
        **d,
        by_holding=[SliceOut(**x.__dict__) for x in s.by_holding],
        by_sector=[SliceOut(**x.__dict__) for x in s.by_sector],
        by_mcap=[SliceOut(**x.__dict__) for x in s.by_mcap],
        by_asset_class=[SliceOut(**x.__dict__) for x in s.by_asset_class],
        snapshots=[
            SnapshotPointOut(created_at=c, kind=k, total_value=v) for c, k, v in s.snapshots
        ],
        disclaimer=get_profiles().disclaimer,
    )


@router.get("/portfolio/actions", response_model=ActionsOut)
def portfolio_actions(session: Session = Depends(get_session)) -> ActionsOut:
    """Everything that needs a look, most severe first, under your saved style and risk."""
    acts, style_label, risk_label = action_list(session, CachedProvider(session))
    return ActionsOut(
        style_label=style_label,
        risk_label=risk_label,
        actions=[ActionOut(**a.__dict__) for a in acts],
        disclaimer=get_profiles().disclaimer,
    )
