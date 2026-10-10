"""Fundamental engine: statements → metrics → plain-English observations.

Metrics are computed from the statements (not taken from Yahoo's pre-computed ratios), so each
one can show its basis ("TTM to Jun 2026", "FY2026", "Screener.in"). For a given stock one
statement source is used throughout — Screener.in's company export when uploaded and current,
else Yahoo — because mixing consolidated and standalone figures would distort growth rates.

Metrics that can't be computed are listed with the reason. Phase 6 scores the observations.
"""

import json
import math
import statistics
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any, Literal

import pandas as pd
from sqlmodel import Session, col, select

from app.analysis.statements import Statements, fill_missing, from_rows, from_yahoo
from app.core.formatting import format_inr, now_ist
from app.core.profiles import FundamentalConfig, RiskLevel, get_profiles
from app.data.freshness import Freshness, as_utc
from app.data.indices import nifty500_by_symbol
from app.data.provider import DataProvider
from app.importers.reference import ticker_resolver
from app.models.tables import FundamentalMetrics, ScreenerData, utcnow

Direction = Literal["bullish", "bearish", "neutral"]
Category = Literal["valuation", "profitability", "growth", "health", "quality", "ownership"]

# Metrics compared against the sector median, and whether lower is better.
PEER_METRICS: dict[str, bool] = {
    "pe": True,
    "pb": True,
    "ev_ebitda": True,
    "roe": False,
    "roce": False,
    "op_margin": False,
    "debt_equity": True,
    "revenue_cagr_3y": False,
}
# Not meaningful for lenders/insurers (their debt is their raw material).
NOT_FOR_FINANCIALS = {
    "ev_ebitda",
    "roce",
    "debt_equity",
    "interest_coverage",
    "current_ratio",
    "op_margin",
    "fcf",
}
# Our ratio vs Yahoo's pre-computed one, for the data cross-check.
YAHOO_CROSSCHECK = {"pe": "trailingPE", "pb": "priceToBook", "ev_ebitda": "enterpriseToEbitda"}


@dataclass(frozen=True)
class Metric:
    key: str
    label: str
    value: float | None
    unit: str  # "x" | "%" | "₹ Cr" | "pp" | ""
    basis: str  # where the number comes from
    sector_median: float | None = None
    peers: int = 0


@dataclass(frozen=True)
class FTest:
    name: str
    passed: bool | None  # None = not computable
    detail: str


@dataclass(frozen=True)
class FScore:
    score: int | None  # None unless all 9 tests are computable
    tests: list[FTest]

    @property
    def computable(self) -> int:
        return sum(t.passed is not None for t in self.tests)


@dataclass(frozen=True)
class Observation:
    key: str
    category: Category
    direction: Direction
    text: str
    value: float | None = None
    minor: bool = False


@dataclass
class FundamentalReport:
    ticker: str
    label: str
    sector: str | None
    sector_key: str | None
    is_financial: bool
    source: str | None  # "yahoo" | "screener" | None
    latest_year: date | None
    freshness: Freshness
    metrics: dict[str, Metric]
    fscore: FScore | None
    observations: list[Observation]
    unavailable: list[str]
    notes: list[str] = field(default_factory=list)
    fetch_errors: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------- helpers


def _f(v: Any) -> float | None:
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(x) or math.isinf(x) else x


def _fy(d: date) -> str:
    """Indian fiscal year label: a March 2026 year end is FY2026."""
    return f"FY{d.year + 1 if d.month > 3 else d.year}"


def _qtr(d: date) -> str:
    return f"{d:%b %Y} quarter"


def _cagr(first: float | None, last: float | None, years: int) -> float | None:
    if first is None or last is None or first <= 0 or last <= 0 or years <= 0:
        return None
    return float(((last / first) ** (1 / years) - 1) * 100)


def _ratio(a: float | None, b: float | None) -> float | None:
    if a is None or b is None or b == 0:
        return None
    return a / b


def _col(df: pd.DataFrame, key: str) -> pd.Series:
    return df[key] if key in df else pd.Series(dtype="float64")


def _val(df: pd.DataFrame, key: str, i: int = -1) -> float | None:
    s = _col(df, key)
    if len(s) < abs(i) + (0 if i < 0 else 1):
        return None
    return _f(s.iloc[i])


def is_financial_sector(sector: str | None, cfg: FundamentalConfig) -> bool:
    if not sector:
        return False
    s = sector.lower()
    return any(f.lower() in s for f in cfg.financial_sectors)


def sector_of(symbol: str | None, info: dict[str, Any]) -> tuple[str | None, str | None]:
    """(display sector, grouping key). NSE's industry for Nifty 500 stocks, else Yahoo's."""
    if symbol:
        c = nifty500_by_symbol().get(symbol)
        if c and c.industry:
            return c.industry, f"nse:{c.industry}"
    ys = info.get("sector")
    return (ys, f"yahoo:{ys}") if ys else (None, None)


# ---------------------------------------------------------------------------- metrics


def ttm_net_income(q: pd.DataFrame) -> tuple[float | None, str | None]:
    """Sum of the last four quarters when they are consecutive (no gaps)."""
    ni = _col(q, "net_income").dropna()
    if len(ni) < 4:
        return None, None
    last4 = list(ni.index[-4:])
    gaps = [(b - a).days for a, b in zip(last4, last4[1:], strict=False)]
    if not all(80 <= g <= 100 for g in gaps):
        return None, None
    return float(ni.iloc[-4:].sum()), f"TTM to {last4[-1]:%b %Y}"


def quarter_yoy(q: pd.DataFrame, key: str) -> tuple[float | None, str | None]:
    s = _col(q, key).dropna()
    if s.empty:
        return None, None
    latest_d, latest = s.index[-1], float(s.iloc[-1])
    target = latest_d - timedelta(days=365)
    prior = [d for d in s.index if abs((d - target).days) <= 20]
    if not prior:
        return None, None
    base = float(s.loc[prior[0]])
    if base <= 0:
        return None, None
    return (latest / base - 1) * 100, f"{_qtr(latest_d)} vs {_qtr(prior[0])}"


def compute_metrics(
    st: Statements,
    *,
    price: float | None,
    price_basis: str,
    info: dict[str, Any],
    screener: dict[str, Any],
    financial: bool,
) -> tuple[dict[str, Metric], list[str]]:
    """All metrics with their basis, plus 'not available' reasons."""
    a, q = st.annual, st.quarterly
    m: dict[str, Metric] = {}
    na: list[str] = []
    src = "Screener.in" if st.source == "screener" else "Yahoo"
    if a.empty:
        na.append("Annual financial statements (none available from Yahoo or a Screener.in upload)")
    ly = st.latest_year()
    fy = _fy(ly) if ly else ""

    def put(
        key: str, label: str, value: float | None, unit: str, basis: str, why: str | None = None
    ) -> None:
        if value is None:
            if why:
                na.append(f"{label} ({why})")
            return
        m[key] = Metric(key, label, round(value, 2), unit, basis)

    # Market cap: our latest close × shares, else Yahoo's figure.
    shares = _f(info.get("sharesOutstanding")) or _val(a, "shares")
    mcap = price * shares / 1e7 if price and shares else None
    mcap_basis = f"{price_basis} × {shares / 1e7:,.2f} Cr shares" if mcap and shares else ""
    if mcap is None and _f(info.get("marketCap")):
        mcap, mcap_basis = float(info["marketCap"]) / 1e7, "Yahoo market cap"
    if mcap is None and _f(screener.get("market_cap_cr")):
        mcap, mcap_basis = float(screener["market_cap_cr"]), "Screener.in market cap"
    put("market_cap", "Market cap", mcap, "₹ Cr", mcap_basis, "no price or share count")
    currency = info.get("financialCurrency")
    foreign = bool(currency and currency != "INR")
    if foreign:
        na.append(f"Valuation ratios (statements are in {currency}, price in INR)")
        mcap = None

    # ---------------- valuation
    ni_ttm, ttm_basis = ttm_net_income(q)
    if ni_ttm is None:
        ni_ttm, ttm_basis = _val(a, "net_income"), fy
    m_ni = ni_ttm
    if mcap is not None:
        if m_ni is not None and m_ni > 0:
            put("pe", "P/E", mcap / m_ni, "x", f"Market cap ÷ net profit ({ttm_basis})")
        elif m_ni is not None:
            na.append("P/E (loss-making: not meaningful)")
        else:
            na.append("P/E (no net profit figure)")
        eq = _val(a, "equity")
        if eq and eq > 0:
            put("pb", "P/B", mcap / eq, "x", f"Market cap ÷ equity ({fy})")
        else:
            na.append("P/B (no positive equity figure)")
        if not financial:
            ebitda = _val(a, "ebitda")
            debt, cash = _val(a, "total_debt") or 0.0, _val(a, "cash") or 0.0
            if ebitda and ebitda > 0:
                put(
                    "ev_ebitda",
                    "EV/EBITDA",
                    (mcap + debt - cash) / ebitda,
                    "x",
                    f"(Market cap + debt − cash) ÷ EBITDA ({fy})",
                )
            else:
                na.append("EV/EBITDA (no positive EBITDA)")
        divs = _val(a, "dividends_paid")
        if divs is not None:
            put(
                "dividend_yield",
                "Dividend yield",
                divs / mcap * 100,
                "%",
                f"Dividends paid ({fy}) ÷ market cap",
            )
    if "dividend_yield" not in m and _f(screener.get("div_yield_pct")) is not None:
        put(
            "dividend_yield", "Dividend yield", float(screener["div_yield_pct"]), "%", "Screener.in"
        )

    # ---------------- growth
    n = len(a)
    for key, label, fld in (("revenue", "Revenue", "revenue"), ("profit", "Profit", "net_income")):
        for yrs in (3, 5):
            v = None
            if n > yrs:
                v = _cagr(_val(a, fld, -1 - yrs), _val(a, fld), yrs)
            mk = f"{key}_cagr_{yrs}y"
            if v is not None:
                put(mk, f"{label} CAGR {yrs}y", v, "%", f"{_fy(a.index[-1 - yrs])}→{fy}, {src}")
                continue
            sk = f"{'sales' if key == 'revenue' else 'profit'}_growth_{yrs}y_pct"
            if _f(screener.get(sk)) is not None:
                put(mk, f"{label} CAGR {yrs}y", float(screener[sk]), "%", "Screener.in")
            elif n <= yrs:
                na.append(f"{label} CAGR {yrs}y (needs {yrs + 1} years of results, have {n})")
            else:
                na.append(f"{label} CAGR {yrs}y (loss or missing figure in the base year)")
    for key, label, fld in (
        ("revenue_qoq_yoy", "Latest quarter revenue YoY", "revenue"),
        ("profit_qoq_yoy", "Latest quarter profit YoY", "net_income"),
    ):
        v, basis = quarter_yoy(q, fld)
        if v is not None:
            put(key, label, v, "%", basis or "")
            continue
        sk = "qtr_sales_var_pct" if fld == "revenue" else "qtr_profit_var_pct"
        if _f(screener.get(sk)) is not None:
            put(key, label, float(screener[sk]), "%", "Screener.in")
        else:
            na.append(f"{label} (needs the same quarter last year)")
    pc = m.get("profit_cagr_3y")
    if "pe" in m and pc and pc.value and pc.value > 0:
        put("peg", "PEG", m["pe"].value / pc.value, "x", "P/E ÷ 3-year profit CAGR")  # type: ignore[operator]
    elif "pe" in m:
        na.append("PEG (needs positive 3-year profit growth)")

    # ---------------- profitability
    ni = _val(a, "net_income")
    eq_now, eq_prev = _val(a, "equity"), _val(a, "equity", -2) if n >= 2 else None
    avg_eq = (eq_now + eq_prev) / 2 if eq_now and eq_prev else eq_now
    if ni is not None and avg_eq and avg_eq > 0:
        put(
            "roe",
            "ROE",
            ni / avg_eq * 100,
            "%",
            f"Net profit ÷ {'average ' if eq_prev else ''}equity ({fy})",
        )
    elif _f(screener.get("roe_pct")) is not None:
        put("roe", "ROE", float(screener["roe_pct"]), "%", "Screener.in")
    else:
        na.append("ROE (needs net profit and positive equity)")
    if not financial:
        ebit = _val(a, "ebit")
        ta, cl = _val(a, "total_assets"), _val(a, "current_liabilities")
        ce, ce_basis = (ta - cl, "total assets − current liabilities") if ta and cl else (None, "")
        if ce is None and eq_now is not None:
            ce, ce_basis = eq_now + (_val(a, "total_debt") or 0.0), "equity + debt"
        if ebit is not None and ce and ce > 0:
            put("roce", "ROCE", ebit / ce * 100, "%", f"EBIT ÷ ({ce_basis}), {fy}")
        elif _f(screener.get("roce_pct")) is not None:
            put("roce", "ROCE", float(screener["roce_pct"]), "%", "Screener.in")
        else:
            na.append("ROCE (needs EBIT and capital employed)")

    def margins(fld: str) -> pd.Series:
        rev = _col(a, "revenue")
        num = _col(a, fld)
        if fld == "operating_income" and num.dropna().empty:
            num = _col(a, "ebit")
        return (num / rev.where(rev > 0) * 100).dropna()

    margin_items = [("net_margin", "Net margin", "net_income")]
    if not financial:  # a lender's interest cost is its raw material: "operating margin" misleads
        margin_items.insert(0, ("op_margin", "Operating margin", "operating_income"))
    for key, label, fld in margin_items:
        s = margins(fld)
        if s.empty:
            if key == "op_margin" and _f(screener.get("opm_pct")) is not None:
                put(key, label, float(screener["opm_pct"]), "%", "Screener.in")
            else:
                na.append(f"{label} (needs revenue and profit figures)")
            continue
        put(key, label, float(s.iloc[-1]), "%", _fy(s.index[-1]))
        if len(s) >= 2:
            span = min(3, len(s) - 1)
            put(
                f"{key}_change",
                f"{label} change over {span}y",
                float(s.iloc[-1] - s.iloc[-1 - span]),
                "pp",
                f"{_fy(s.index[-1 - span])}→{_fy(s.index[-1])}",
            )

    # ---------------- health
    if not financial:
        debt_h, eq_h = _val(a, "total_debt"), _val(a, "equity")
        if eq_h and eq_h > 0 and debt_h is not None:
            put("debt_equity", "Debt/equity", debt_h / eq_h, "x", f"Total debt ÷ equity ({fy})")
        elif _f(screener.get("debt_to_equity")) is not None:
            put("debt_equity", "Debt/equity", float(screener["debt_to_equity"]), "x", "Screener.in")
        else:
            na.append("Debt/equity (needs debt and positive equity)")
        ebit, interest = _val(a, "ebit"), _val(a, "interest_expense")
        if ebit is not None and interest and interest > 0:
            put(
                "interest_coverage",
                "Interest coverage",
                ebit / interest,
                "x",
                f"EBIT ÷ interest ({fy})",
            )
        elif interest == 0:
            na.append("Interest coverage (no interest expense)")
        elif _f(screener.get("interest_coverage")) is not None:
            put(
                "interest_coverage",
                "Interest coverage",
                float(screener["interest_coverage"]),
                "x",
                "Screener.in",
            )
        else:
            na.append("Interest coverage (needs EBIT and interest expense)")
        cr = _ratio(_val(a, "current_assets"), _val(a, "current_liabilities"))
        if cr is not None:
            put(
                "current_ratio",
                "Current ratio",
                cr,
                "x",
                f"Current assets ÷ current liabilities ({fy})",
            )
        elif _f(screener.get("current_ratio")) is not None:
            put(
                "current_ratio",
                "Current ratio",
                float(screener["current_ratio"]),
                "x",
                "Screener.in",
            )
        else:
            na.append("Current ratio (needs current assets and liabilities)")
    # Deposits and loans flow through a lender's operating cash flow, so FCF says nothing there.
    fcf = pd.Series(dtype="float64") if financial else _col(a, "free_cash_flow").dropna()
    if financial:
        pass
    elif not fcf.empty:
        if foreign:  # the ratio-free count below still applies; the amount isn't in rupees
            na.append(f"Free cash flow amount (statements are in {currency})")
        else:
            put("fcf", "Free cash flow", float(fcf.iloc[-1]), "₹ Cr", _fy(fcf.index[-1]))
        last3 = fcf.iloc[-3:]
        put(
            "fcf_positive_years",
            "Years of positive FCF (last 3)",
            float((last3 > 0).sum()),
            "",
            f"{_fy(last3.index[0])}–{_fy(last3.index[-1])}",
        )
    else:
        na.append("Free cash flow (needs operating cash flow and capex)")
    nis = _col(a, "net_income").dropna()
    losses = 0
    for v in reversed(nis.tolist()):
        if v < 0:
            losses += 1
        else:
            break
    put("consecutive_loss_years", "Consecutive loss years", float(losses), "", src)
    debts = _col(a, "total_debt").dropna()
    if len(debts) >= 2:
        put(
            "debt_change",
            "Debt change (1y)",
            float(debts.iloc[-1] - debts.iloc[-2]),
            f"{currency} (Yahoo units)" if foreign else "₹ Cr",
            f"{_fy(debts.index[-2])}→{_fy(debts.index[-1])}",
        )

    # ---------------- ownership (Screener.in only)
    for key, label, sk, unit in (
        ("promoter_pct", "Promoter holding", "promoter_pct", "%"),
        ("promoter_change", "Change in promoter holding", "promoter_change_pct", "pp"),
        ("pledge_pct", "Promoter shares pledged", "pledge_pct", "%"),
        ("fii_pct", "FII holding", "fii_pct", "%"),
        ("fii_change", "Change in FII holding", "fii_change_pct", "pp"),
        ("dii_pct", "DII holding", "dii_pct", "%"),
        ("dii_change", "Change in DII holding", "dii_change_pct", "pp"),
    ):
        v = _f(screener.get(sk))
        if v is not None:
            put(key, label, v, unit, "Screener.in")
    if not any(k in m for k in ("promoter_pct", "pledge_pct", "fii_pct")):
        na.append("Ownership: promoter, pledge, FII/DII (upload a Screener.in export to add these)")
    return m, na


def piotroski(a: pd.DataFrame, financial: bool) -> FScore:
    """Piotroski F-score on the last two fiscal years (year-end figures; ROA on opening assets)."""

    def v(k: str, i: int) -> float | None:
        return _val(a, k, i) if len(a) >= abs(i) else None

    tests: list[FTest] = []

    def add(name: str, ok: bool | None, detail: str) -> None:
        tests.append(FTest(name, ok, detail))

    ni0, ni1 = v("net_income", -1), v("net_income", -2)
    ta0, ta1, ta2 = v("total_assets", -1), v("total_assets", -2), v("total_assets", -3)
    cfo0 = v("operating_cash_flow", -1)
    roa0 = _ratio(ni0, ta1)
    roa1 = _ratio(ni1, ta2)
    add(
        "Profitable (ROA > 0)",
        None if roa0 is None else roa0 > 0,
        "—" if roa0 is None else f"ROA {roa0 * 100:.1f}%",
    )
    add(
        "Positive operating cash flow",
        None if cfo0 is None else cfo0 > 0,
        "—" if cfo0 is None else ("positive" if cfo0 > 0 else "negative"),
    )
    add(
        "ROA improving",
        None if roa0 is None or roa1 is None else roa0 > roa1,
        "—" if roa0 is None or roa1 is None else f"{roa1 * 100:.1f}% → {roa0 * 100:.1f}%",
    )
    add(
        "Cash flow exceeds profit (earnings quality)",
        None if cfo0 is None or ni0 is None else cfo0 > ni0,
        "—" if cfo0 is None or ni0 is None else f"CFO {cfo0:,.0f} vs profit {ni0:,.0f} Cr",
    )
    ltd0, ltd1 = v("long_term_debt", -1), v("long_term_debt", -2)
    lev0, lev1 = _ratio(ltd0 or 0.0, ta0), _ratio(ltd1 or 0.0, ta1)
    lev_known = ltd0 is not None or ltd1 is not None
    add(
        "Leverage not rising",
        None if not lev_known or lev0 is None or lev1 is None else lev0 <= lev1,
        "—"
        if not lev_known or lev0 is None or lev1 is None
        else f"LT debt/assets {lev1:.2f} → {lev0:.2f}",
    )
    cr0 = _ratio(v("current_assets", -1), v("current_liabilities", -1))
    cr1 = _ratio(v("current_assets", -2), v("current_liabilities", -2))
    add(
        "Current ratio improving",
        None if financial or cr0 is None or cr1 is None else cr0 > cr1,
        "not meaningful for financials"
        if financial
        else "—"
        if cr0 is None or cr1 is None
        else f"{cr1:.2f} → {cr0:.2f}",
    )
    sh0, sh1 = v("shares", -1), v("shares", -2)
    add(
        "No new shares issued",
        None if sh0 is None or sh1 is None else sh0 <= sh1 * 1.001,
        "—" if sh0 is None or sh1 is None else f"{sh1 / 1e7:,.2f} → {sh0 / 1e7:,.2f} Cr shares",
    )
    gm0 = _ratio(v("gross_profit", -1), v("revenue", -1))
    gm1 = _ratio(v("gross_profit", -2), v("revenue", -2))
    add(
        "Gross margin improving",
        None if financial or gm0 is None or gm1 is None else gm0 > gm1,
        "not meaningful for financials"
        if financial
        else "—"
        if gm0 is None or gm1 is None
        else f"{gm1 * 100:.1f}% → {gm0 * 100:.1f}%",
    )
    at0 = _ratio(v("revenue", -1), ta1)
    at1 = _ratio(v("revenue", -2), ta2)
    add(
        "Asset turnover improving",
        None if at0 is None or at1 is None else at0 > at1,
        "—" if at0 is None or at1 is None else f"{at1:.2f} → {at0:.2f}",
    )
    computable = [t for t in tests if t.passed is not None]
    score = sum(bool(t.passed) for t in computable) if len(computable) == 9 else None
    return FScore(score, tests)


# ---------------------------------------------------------------------------- observations


def observations(
    m: dict[str, Metric],
    fs: FScore | None,
    cfg: FundamentalConfig,
    risk: RiskLevel,
    risk_label: str,
    severe_pledge: float,
) -> list[Observation]:
    t = cfg.thresholds
    out: list[Observation] = []

    def add(
        key: str,
        cat: Category,
        d: Direction,
        text: str,
        v: float | None = None,
        minor: bool = False,
    ) -> None:
        out.append(Observation(key, cat, d, text, v, minor))

    def g(k: str) -> float | None:
        return m[k].value if k in m else None

    # valuation vs peers
    for key, label in (("pe", "P/E"), ("pb", "P/B"), ("ev_ebitda", "EV/EBITDA")):
        x = m.get(key)
        if not x or x.value is None:
            continue
        med = x.sector_median
        if med is None or med <= 0:
            add(
                f"{key}_value",
                "valuation",
                "neutral",
                f"{label} {x.value:.1f} (no sector median: {x.peers} peer(s) with data)",
                x.value,
            )
            continue
        r = x.value / med
        if r <= t.valuation_cheap_ratio:
            add(
                f"{key}_cheap",
                "valuation",
                "bullish",
                f"{label} {x.value:.1f} vs sector median {med:.1f}: cheaper than peers",
                x.value,
            )
        elif r >= t.valuation_rich_ratio:
            add(
                f"{key}_rich",
                "valuation",
                "bearish",
                f"{label} {x.value:.1f} vs sector median {med:.1f}: pricier than peers",
                x.value,
            )
        else:
            add(
                f"{key}_inline",
                "valuation",
                "neutral",
                f"{label} {x.value:.1f}, in line with the sector median {med:.1f}",
                x.value,
            )
    peg = g("peg")
    if peg is not None:
        if peg <= t.peg_cheap:
            add(
                "peg_cheap",
                "valuation",
                "bullish",
                f"PEG {peg:.2f}: price looks low for its growth",
                peg,
            )
        elif peg >= t.peg_rich:
            add(
                "peg_rich",
                "valuation",
                "bearish",
                f"PEG {peg:.2f}: price runs ahead of its growth",
                peg,
            )
        else:
            add("peg_fair", "valuation", "neutral", f"PEG {peg:.2f}", peg)
    dy = g("dividend_yield")
    if dy is not None and dy >= t.dividend_yield_high:
        add("dividend_high", "valuation", "bullish", f"Dividend yield {dy:.1f}%", dy, minor=True)

    # profitability
    for key, label, good, poor in (
        ("roe", "ROE", t.roe_good, t.roe_poor),
        ("roce", "ROCE", t.roce_good, t.roce_poor),
    ):
        fv = g(key)
        if fv is None:
            continue
        med = m[key].sector_median
        vs = f" (sector median {med:.1f}%)" if med is not None else ""
        if fv >= good:
            add(
                f"{key}_good",
                "profitability",
                "bullish",
                f"{label} {fv:.1f}%: high return on capital{vs}",
                fv,
            )
        elif fv <= poor:
            add(
                f"{key}_poor",
                "profitability",
                "bearish",
                f"{label} {fv:.1f}%: weak return on capital{vs}",
                fv,
            )
        else:
            add(f"{key}_ok", "profitability", "neutral", f"{label} {fv:.1f}%{vs}", fv)
    for key, label in (
        ("op_margin_change", "Operating margin"),
        ("net_margin_change", "Net margin"),
    ):
        x = m.get(key)
        if not x or x.value is None:
            continue
        base = m[key.removesuffix("_change")].value
        if x.value > t.margin_trend_flat_pp:
            add(
                f"{key}_up",
                "profitability",
                "bullish",
                f"{label} up {x.value:.1f} pp to {base:.1f}% ({x.basis})",
                x.value,
            )
        elif x.value < -t.margin_trend_flat_pp:
            add(
                f"{key}_down",
                "profitability",
                "bearish",
                f"{label} down {abs(x.value):.1f} pp to {base:.1f}% ({x.basis})",
                x.value,
            )
        else:
            add(
                f"{key}_flat",
                "profitability",
                "neutral",
                f"{label} stable at {base:.1f}% ({x.basis})",
                x.value,
            )

    # growth
    for key, label in (
        ("revenue_cagr_3y", "Revenue"),
        ("profit_cagr_3y", "Profit"),
        ("revenue_cagr_5y", "Revenue"),
        ("profit_cagr_5y", "Profit"),
    ):
        fv = g(key)
        if fv is None:
            continue
        yrs = key[-2]
        if fv >= t.growth_good:
            add(
                f"{key}_strong",
                "growth",
                "bullish",
                f"{label} grew {fv:.1f}% a year over {yrs} years",
                fv,
            )
        elif fv < t.growth_poor:
            add(
                f"{key}_falling",
                "growth",
                "bearish",
                f"{label} shrank {abs(fv):.1f}% a year over {yrs} years",
                fv,
            )
        else:
            add(
                f"{key}_modest",
                "growth",
                "neutral",
                f"{label} grew {fv:.1f}% a year over {yrs} years",
                fv,
            )
    for key, label in (("revenue_qoq_yoy", "revenue"), ("profit_qoq_yoy", "profit")):
        x = m.get(key)
        if not x or x.value is None:
            continue
        if x.value >= t.quarter_yoy_good:
            add(
                f"{key}_strong",
                "growth",
                "bullish",
                f"Latest quarter {label} up {x.value:.1f}% year on year ({x.basis})",
                x.value,
            )
        elif x.value < t.quarter_yoy_poor:
            add(
                f"{key}_falling",
                "growth",
                "bearish",
                f"Latest quarter {label} down {abs(x.value):.1f}% year on year ({x.basis})",
                x.value,
            )
        else:
            add(
                f"{key}_modest",
                "growth",
                "neutral",
                f"Latest quarter {label} up {x.value:.1f}% year on year ({x.basis})",
                x.value,
            )

    # health
    de = g("debt_equity")
    if de is not None:
        limit = risk.max_debt_to_equity
        if limit is not None and de > limit:
            add(
                "debt_above_limit",
                "health",
                "bearish",
                f"Debt/equity {de:.2f}, above your limit of {limit:g} ({risk_label} risk)",
                de,
            )
        elif de <= t.debt_equity_low:
            add("debt_low", "health", "bullish", f"Debt/equity {de:.2f}: low debt", de)
        else:
            add(
                "debt_ok",
                "health",
                "neutral",
                f"Debt/equity {de:.2f}" + (f", within your limit of {limit:g}" if limit else ""),
                de,
            )
    ic = g("interest_coverage")
    if ic is not None:
        if ic >= t.interest_coverage_good:
            add(
                "interest_cover_good",
                "health",
                "bullish",
                f"Interest coverage {ic:.1f}×: debt is easily serviced",
                ic,
            )
        elif ic < t.interest_coverage_poor:
            add(
                "interest_cover_poor",
                "health",
                "bearish",
                f"Interest coverage {ic:.1f}×: profits barely cover interest",
                ic,
            )
        else:
            add("interest_cover_ok", "health", "neutral", f"Interest coverage {ic:.1f}×", ic)
    cr = g("current_ratio")
    if cr is not None:
        if cr >= t.current_ratio_good:
            add(
                "current_ratio_good",
                "health",
                "bullish",
                f"Current ratio {cr:.2f}: comfortable liquidity",
                cr,
            )
        elif cr < t.current_ratio_poor:
            add(
                "current_ratio_poor",
                "health",
                "bearish",
                f"Current ratio {cr:.2f}: short-term dues exceed current assets",
                cr,
            )
        else:
            add("current_ratio_ok", "health", "neutral", f"Current ratio {cr:.2f}", cr)
    pos = g("fcf_positive_years")
    fcf = m.get("fcf")
    if pos is not None and fcf is not None and fcf.value is not None:
        span = m["fcf_positive_years"].basis
        if pos >= 3:
            add(
                "fcf_consistent",
                "health",
                "bullish",
                f"Free cash flow positive in each of the last 3 years ({span}); "
                f"latest {format_inr(fcf.value, 0)} Cr",
                fcf.value,
            )
        elif fcf.value < 0 and pos <= 1:
            add(
                "fcf_negative",
                "health",
                "bearish",
                f"Free cash flow negative ({format_inr(fcf.value, 0)} Cr in {fcf.basis}); "
                f"positive in only {pos:.0f} of 3 years",
                fcf.value,
            )
        else:
            add(
                "fcf_mixed",
                "health",
                "neutral",
                f"Free cash flow {format_inr(fcf.value, 0)} Cr in {fcf.basis}; "
                f"positive in {pos:.0f} of the last 3 years",
                fcf.value,
            )
    losses = g("consecutive_loss_years")
    if losses:
        rising = (g("debt_change") or 0) > 0
        add(
            "loss_making",
            "health",
            "bearish",
            f"Net loss in the last {losses:.0f} year(s)" + (" while debt rose" if rising else ""),
            losses,
        )

    # quality
    if fs is not None:
        if fs.score is None:
            add(
                "fscore_partial",
                "quality",
                "neutral",
                f"Piotroski F-score not computed: only {fs.computable} of 9 tests have data",
            )
        elif fs.score >= t.fscore_strong:
            add(
                "fscore_strong",
                "quality",
                "bullish",
                f"Piotroski F-score {fs.score}/9: strong financial position",
                fs.score,
            )
        elif fs.score <= t.fscore_weak:
            add(
                "fscore_weak",
                "quality",
                "bearish",
                f"Piotroski F-score {fs.score}/9: weak financial position",
                fs.score,
            )
        else:
            add("fscore_mid", "quality", "neutral", f"Piotroski F-score {fs.score}/9", fs.score)

    # ownership
    pc = g("promoter_change")
    if pc is not None:
        held = g("promoter_pct")
        tail = f" (now {held:.1f}%)" if held is not None else ""
        if pc <= -t.promoter_change_pp:
            add(
                "promoter_selling",
                "ownership",
                "bearish",
                f"Promoters cut their stake by {abs(pc):.1f} pp{tail}",
                pc,
            )
        elif pc >= t.promoter_change_pp:
            add(
                "promoter_buying",
                "ownership",
                "bullish",
                f"Promoters raised their stake by {pc:.1f} pp{tail}",
                pc,
            )
    pl = g("pledge_pct")
    if pl is not None:
        if pl > severe_pledge:
            add(
                "pledge_severe",
                "ownership",
                "bearish",
                f"{pl:.1f}% of promoter shares are pledged "
                f"(above {severe_pledge:g}%: a severe red flag)",
                pl,
            )
        elif pl > t.pledge_warn_pct:
            add(
                "pledge_high",
                "ownership",
                "bearish",
                f"{pl:.1f}% of promoter shares are pledged",
                pl,
            )
        elif pl == 0:
            add("pledge_none", "ownership", "bullish", "No promoter shares pledged", pl, minor=True)
    for key, label in (("fii_change", "FIIs"), ("dii_change", "DIIs")):
        fv = g(key)
        if fv is None:
            continue
        if fv >= t.institution_change_pp:
            add(
                f"{key}_up",
                "ownership",
                "bullish",
                f"{label} raised their stake by {fv:.1f} pp",
                fv,
            )
        elif fv <= -t.institution_change_pp:
            add(
                f"{key}_down",
                "ownership",
                "bearish",
                f"{label} cut their stake by {abs(fv):.1f} pp",
                fv,
            )
    return out


# ---------------------------------------------------------------------------- persistence


def screener_for(
    session: Session, symbol: str | None
) -> tuple[dict[str, Any], Statements | None, str | None]:
    """(screen fields, company statements, note) from the latest Screener.in upload, if current."""
    if not symbol:
        return {}, None, None
    row = session.get(ScreenerData, symbol)
    if row is None:
        return {}, None, None
    age = utcnow() - as_utc(row.updated_at)
    max_age = get_profiles().fundamental.screener_max_age_days
    if age > timedelta(days=max_age):
        return (
            {},
            None,
            (
                f"Your Screener.in data for {symbol} is {age.days} days old "
                f"(over {max_age}); upload a fresh export to use it."
            ),
        )
    fields = json.loads(row.fields_json or "{}")
    stmts = None
    if row.statements_json:
        d = json.loads(row.statements_json)
        stmts = from_rows("screener", d.get("annual", {}), d.get("quarterly", {}))
    return fields, stmts, None


def store_metrics(
    session: Session, ticker: str, sector_key: str | None, m: dict[str, Metric]
) -> None:
    row = session.get(FundamentalMetrics, ticker) or FundamentalMetrics(ticker=ticker)
    row.sector_key = sector_key
    row.computed_at = utcnow()
    row.metrics_json = json.dumps({k: x.value for k, x in m.items() if k in PEER_METRICS})
    session.add(row)


def sector_medians(
    session: Session, sector_key: str, exclude: str
) -> dict[str, tuple[float | None, int]]:
    rows = session.exec(
        select(FundamentalMetrics).where(
            FundamentalMetrics.sector_key == sector_key, col(FundamentalMetrics.ticker) != exclude
        )
    ).all()
    min_peers = get_profiles().fundamental.sector_min_peers
    out: dict[str, tuple[float | None, int]] = {}
    values: dict[str, list[float]] = {k: [] for k in PEER_METRICS}
    for r in rows:
        for k, v in json.loads(r.metrics_json or "{}").items():
            if k in values and v is not None:
                values[k].append(float(v))
    for k, vals in values.items():
        out[k] = (round(statistics.median(vals), 2) if len(vals) >= min_peers else None, len(vals))
    return out


# ---------------------------------------------------------------------------- entry point


def analyse_fundamentals(
    session: Session,
    provider: DataProvider,
    ticker: str,
    *,
    label: str | None = None,
    risk: RiskLevel | None = None,
    risk_label: str = "Medium",
    fetch: bool = True,
    now: datetime | None = None,
) -> FundamentalReport:
    profiles = get_profiles()
    cfg = profiles.fundamental
    risk = risk or profiles.risk_levels["medium"]
    now = now or now_ist()
    errors: list[str] = []
    notes: list[str] = []
    is_index = ticker.startswith("^")
    symbol = ticker.removesuffix(".NS") if ticker.endswith(".NS") else None
    sec = ticker_resolver().by_symbol.get(symbol) if symbol else None
    if is_index or (sec is not None and sec.kind == "etf"):
        what = "an index" if is_index else "an ETF (it holds a basket of stocks)"
        return FundamentalReport(
            ticker,
            label or ticker,
            None,
            None,
            False,
            None,
            None,
            Freshness("unavailable", f"Company fundamentals don't apply to {what}"),
            {},
            None,
            [],
            [f"Fundamentals (not applicable to {what})"],
        )
    if fetch:
        res = provider.ensure_fundamentals(ticker, label)
        if res.outcome == "failed":
            errors.append(res.message)
    raw = provider.fundamentals(ticker)
    info = raw.info if raw else {}
    yahoo_st = from_yahoo(raw.statements) if raw else None
    fields, scr_st, scr_note = screener_for(session, symbol)
    if scr_note:
        notes.append(scr_note)
    # One source for all statements: Screener.in's export if it's at least as recent as Yahoo's.
    st = yahoo_st
    if (
        scr_st is not None
        and scr_st.years
        and (
            yahoo_st is None
            or not yahoo_st.years
            or (scr_st.latest_year() or date.min) >= (yahoo_st.latest_year() or date.min)
        )
    ):
        st = scr_st
        notes.append(f"Statements from your Screener.in upload ({scr_st.years} years).")
        if yahoo_st is not None:
            filled = fill_missing(scr_st, yahoo_st)
            if filled:
                notes.append(
                    "Not in the Screener.in export, taken from Yahoo for the same years: "
                    + ", ".join(filled).lower()
                    + "."
                )
    elif yahoo_st is not None and yahoo_st.years:
        notes.append(f"Statements from Yahoo Finance ({yahoo_st.years} years).")
    if st is None:
        st = from_rows("none", {}, {})
    sector, sector_key = sector_of(symbol, info)
    financial = is_financial_sector(sector, cfg) or is_financial_sector(info.get("sector"), cfg)
    if financial:
        notes.append(
            "Lender/insurer: debt/equity, ROCE, EV/EBITDA, operating margin, current ratio, "
            "free cash flow and the Piotroski F-score are skipped as not meaningful."
        )
    bars = provider.daily(ticker)
    price, price_basis = None, ""
    if len(bars.frame):
        price = float(bars.frame["close"].iloc[-1])
        price_basis = f"close {format_inr(price)} on {bars.frame.index[-1]:%d %b %Y}"
    elif _f(info.get("currentPrice")):
        price = float(info["currentPrice"])
        price_basis = f"Yahoo price {format_inr(price)}"
    metrics, na = compute_metrics(
        st, price=price, price_basis=price_basis, info=info, screener=fields, financial=financial
    )
    if sector_key:
        store_metrics(session, ticker, sector_key, metrics)
        session.commit()
        meds = sector_medians(session, sector_key, ticker)
        for k, (med, peers) in meds.items():
            if k in metrics:
                metrics[k] = Metric(**{**metrics[k].__dict__, "sector_median": med, "peers": peers})
        if all(med is None for med, _ in meds.values()):
            n_peers = max((p for _, p in meds.values()), default=0)
            na.append(
                f"Sector medians ({n_peers} {sector} peer(s) cached; need "
                f"{cfg.sector_min_peers}: run the fundamentals refresh)"
            )
    else:
        na.append("Sector medians (sector unknown)")
    fs = None
    if financial:
        na.append(
            "Piotroski F-score (designed for non-financial companies; not meaningful for lenders)"
        )
    elif st.years >= 2:
        fs = piotroski(st.annual, financial)
    else:
        na.append(f"Piotroski F-score (needs 2 years of results, have {st.years})")
    tol = cfg.cross_check_tolerance
    for k, yk in YAHOO_CROSSCHECK.items():
        ours, theirs = metrics.get(k), _f(info.get(yk))
        if ours and ours.value and theirs and theirs > 0 and abs(ours.value / theirs - 1) > tol:
            notes.append(
                f"Data check: our {ours.label} {ours.value:.2f} differs from Yahoo's own figure "
                f"{theirs:.2f}. Yahoo's statements and ratios disagree; a Screener.in export "
                "would settle it."
            )
    obs = observations(
        metrics, fs, cfg, risk, risk_label, profiles.signals.severe_flags.max_pledge_pct
    )
    freshness = provider.fundamentals_freshness(ticker)
    if st.source == "screener":
        freshness = Freshness("fresh", "From your Screener.in upload")
    return FundamentalReport(
        ticker=ticker,
        label=label or info.get("longName") or ticker,
        sector=sector,
        sector_key=sector_key,
        is_financial=financial,
        source=st.source if st.years else None,
        latest_year=st.latest_year(),
        freshness=freshness,
        metrics=metrics,
        fscore=fs,
        observations=obs,
        unavailable=na,
        notes=notes,
        fetch_errors=errors,
    )
