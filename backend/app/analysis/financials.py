"""Year-by-year and quarter-by-quarter figures for the stock page's charts.

Straight from the statements the fundamental engine already chose (Yahoo or your Screener.in
upload), in ₹ crore, plus a few ratios worked out per year the same way the engine does for the
latest year. Nothing here feeds a score."""

from dataclasses import dataclass
from datetime import date

import pandas as pd

from app.analysis.fundamental import FundamentalReport, _f, _fy, _qtr
from app.analysis.valuation import YearPE


@dataclass(frozen=True)
class FinancialYear:
    fy: str
    year_end: date
    revenue: float | None
    net_income: float | None
    op_margin: float | None  # %
    net_margin: float | None  # %
    roe: float | None  # %, on year-end equity
    total_debt: float | None
    equity: float | None
    cash: float | None
    debt_equity: float | None
    fcf: float | None
    dividends_paid: float | None
    payout_pct: float | None
    pe: float | None  # at the year-end close (see valuation.pe_history)
    price: float | None


@dataclass(frozen=True)
class FinancialQuarter:
    label: str
    period_end: date
    revenue: float | None
    net_income: float | None


def _ratio(a: float | None, b: float | None, scale: float = 100.0) -> float | None:
    if a is None or b is None or b <= 0:
        return None
    return round(a / b * scale, 2)


def financial_history(
    report: FundamentalReport, pe_points: list[YearPE]
) -> tuple[list[FinancialYear], list[FinancialQuarter]]:
    st = report.statements
    if st is None:
        return [], []
    pes = {p.year_end: p for p in pe_points}
    years: list[FinancialYear] = []
    a: pd.DataFrame = st.annual
    for d, row in a.iterrows():
        g = {k: _f(row.get(k)) for k in a.columns}
        op = g.get("operating_income") if g.get("operating_income") is not None else g.get("ebit")
        financial = report.is_financial
        div = g.get("dividends_paid")
        ni = g.get("net_income")
        pe = pes.get(d)
        years.append(
            FinancialYear(
                fy=_fy(d),
                year_end=d,
                revenue=g.get("revenue"),
                net_income=ni,
                op_margin=None if financial else _ratio(op, g.get("revenue")),
                net_margin=_ratio(ni, g.get("revenue")),
                roe=_ratio(ni, g.get("equity")),
                total_debt=g.get("total_debt"),
                equity=g.get("equity"),
                cash=g.get("cash"),
                debt_equity=None
                if financial
                else _ratio(g.get("total_debt"), g.get("equity"), 1.0),
                fcf=None if financial else g.get("free_cash_flow"),
                dividends_paid=div,
                payout_pct=_ratio(div, ni) if div is not None and ni and ni > 0 else None,
                pe=pe.pe if pe else None,
                price=pe.price if pe else None,
            )
        )
    quarters = [
        FinancialQuarter(
            _qtr(d),
            d,
            _f(row.get("revenue")),
            _f(row.get("net_income")),
        )
        for d, row in st.quarterly.iterrows()
    ]
    return years, quarters
