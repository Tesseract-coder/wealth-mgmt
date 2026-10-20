"""How each check in config/checks.yaml is worked out. Wording and thresholds live in the YAML;
this module only measures. Every rule returns pass / fail / no data with the value it used, and
reads only data the analysis engines already produced: nothing here changes a score or signal."""

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Literal

import pandas as pd

from app.analysis.fundamental import FundamentalReport, Metric, _col
from app.analysis.mf import FundReport
from app.analysis.returns import Rolling
from app.analysis.valuation import FairValue, YearPE, pe_history_median
from app.core.formatting import format_inr

Status = Literal["pass", "fail", "no_data"]


@dataclass(frozen=True)
class Outcome:
    status: Status
    value: float | None = None
    threshold: float | None = None
    vars: dict[str, str] = field(default_factory=dict)  # extra {names} for the text
    reason: str | None = None  # no data: why
    text: str | None = None  # replaces the configured pass/fail sentence


def no_data(reason: str) -> Outcome:
    return Outcome("no_data", reason=reason)


def judge(ok: bool, value: float | None, threshold: float | None = None, **vars: str) -> Outcome:
    return Outcome("pass" if ok else "fail", value, threshold, dict(vars))


class MissingThreshold(ValueError):
    """A check needs a threshold that resolved to nothing (e.g. cleared in Settings)."""


@dataclass(frozen=True)
class Limits:
    """A check's thresholds, resolved from the YAML (numbers or profiles.yaml references)."""

    threshold: float | None
    upper: float | None
    ratio: float | None

    @property
    def t(self) -> float:
        if self.threshold is None:
            raise MissingThreshold("no threshold set")
        return self.threshold


def cr(v: float, currency: str = "INR") -> str:
    """Crore amount: ₹69,197 Cr (or "USD 1,234 Cr" for statements in another currency)."""
    if currency != "INR":
        return f"{currency} {format_inr(v, 0).replace('₹', '')} Cr"
    return f"{format_inr(v, 0)} Cr"


def pct(v: float) -> str:
    return f"{v:.1f}%"


# ---------------------------------------------------------------------------- stocks


@dataclass
class StockContext:
    report: FundamentalReport
    annual: pd.DataFrame  # empty when no statements
    daily: dict[str, float | None]  # daily-bar indicator values (close, sma50, rsi14 …)
    market: dict[str, float | None]  # 52-week, relative strength … (always from daily bars)
    risk_label: str
    fair_value: FairValue | None
    fair_value_reason: str
    pe_points: list[YearPE]
    rsi_key: str = "rsi14"

    @property
    def financial(self) -> bool:
        return self.report.is_financial

    def metric(self, key: str) -> Metric | None:
        m = self.report.metrics.get(key)
        return m if m is not None and m.value is not None else None

    def v(self, key: str) -> float | None:
        m = self.report.metrics.get(key)
        return None if m is None or m.value is None else float(m.value)

    @property
    def currency(self) -> str:
        return self.report.currency

    def money(self, v: float) -> str:
        return cr(v, self.currency)

    def why_missing(self, label_prefix: str, default: str) -> str:
        """The fundamental engine's own "not available" reason, when it gave one."""
        prefixes = [label_prefix]
        if label_prefix in VALUATION_LABELS:  # skipped as a group (statements in USD …)
            prefixes.append("Valuation ratios")
        for prefix in prefixes:
            for u in self.report.unavailable:
                if u.lower().startswith(prefix.lower()):
                    m = re.search(r"\((.*)\)\s*$", u)
                    return m.group(1) if m else u
        return default

    def series(self, key: str) -> pd.Series:
        return _col(self.annual, key).dropna()

    @property
    def pays_dividend(self) -> bool | None:
        dy = self.v("dividend_yield")
        if dy is not None:
            return dy > 0
        divs = self.series("dividends_paid")
        return None if divs.empty else bool(divs.iloc[-1] > 0)


StockRule = Callable[[StockContext, Limits], Outcome]
VALUATION_LABELS = {"P/E", "P/B", "EV/EBITDA", "PEG", "Dividend yield"}
NO_PEERS = "too few peers in the sector for a median"


def _vs_median(ctx: StockContext, key: str, lower_is_better: bool, missing: str) -> Outcome:
    v, m = ctx.v(key), ctx.metric(key)
    if v is None or m is None:
        return no_data(ctx.why_missing(missing, f"no {missing} figure"))
    med = m.sector_median
    if med is None:
        return no_data(NO_PEERS)
    return judge(v <= med if lower_is_better else v >= med, v, med)


def pe_vs_sector(ctx: StockContext, _: Limits) -> Outcome:
    return _vs_median(ctx, "pe", True, "P/E")


def pe_vs_history(ctx: StockContext, _: Limits) -> Outcome:
    pe = ctx.v("pe")
    if pe is None:
        return no_data(ctx.why_missing("P/E", "no P/E figure"))
    med = pe_history_median(ctx.pe_points)
    if med is None:
        return no_data(
            f"needs P/E at 3 past year-ends, have {len(ctx.pe_points)} (profit and price history)"
        )
    return judge(pe <= med, pe, med, years=str(len(ctx.pe_points)))


def peg(ctx: StockContext, lim: Limits) -> Outcome:
    v = ctx.v("peg")
    if v is None:
        return no_data(ctx.why_missing("PEG", "needs P/E and positive expected profit growth"))
    growth = ctx.v("forward_growth")
    return judge(v <= lim.t, v, lim.threshold, growth=pct(growth) if growth else "—")


def fair_value_check(ctx: StockContext, _: Limits) -> Outcome:
    fv = ctx.fair_value
    if fv is None:
        return no_data(ctx.why_missing("P/E", ctx.fair_value_reason))
    gap = "far" if fv.value <= 0 else f"{abs(fv.gap_pct):.1f}%"  # no value: the gap is infinite
    return judge(fv.price < fv.value, fv.price, fv.value, gap=gap)


def ev_ebitda_vs_sector(ctx: StockContext, _: Limits) -> Outcome:
    return _vs_median(ctx, "ev_ebitda", True, "EV/EBITDA")


def pb_vs_sector(ctx: StockContext, lim: Limits) -> Outcome:
    v, m = ctx.v("pb"), ctx.metric("pb")
    if v is None or m is None:
        return no_data(ctx.why_missing("P/B", "no P/B figure"))
    if m.sector_median is None:
        return no_data(NO_PEERS)
    ratio = lim.ratio or 1.0
    limit = round(m.sector_median * ratio, 2)
    return judge(
        v <= limit,
        v,
        limit,
        ratio_text=f"{ratio:g}×",
        median=f"{m.sector_median:.2f}×",
    )


def _at_least(ctx: StockContext, key: str, lim: Limits, missing: str) -> Outcome:
    v = ctx.v(key)
    if v is None:
        return no_data(ctx.why_missing(missing, f"no {missing} figure"))
    return judge(v >= lim.t, v, lim.threshold)


def revenue_cagr(ctx: StockContext, lim: Limits) -> Outcome:
    return _at_least(ctx, "revenue_cagr_3y", lim, "Revenue CAGR 3y")


def profit_cagr(ctx: StockContext, lim: Limits) -> Outcome:
    return _at_least(ctx, "profit_cagr_3y", lim, "Profit CAGR 3y")


def revenue_quarter(ctx: StockContext, lim: Limits) -> Outcome:
    return _at_least(ctx, "revenue_qoq_yoy", lim, "Latest quarter revenue YoY")


def profit_quarter(ctx: StockContext, lim: Limits) -> Outcome:
    return _at_least(ctx, "profit_qoq_yoy", lim, "Latest quarter profit YoY")


def _faster(ctx: StockContext, a: str, b: str, a_label: str, b_label: str) -> Outcome:
    x, y = ctx.v(a), ctx.v(b)
    if x is None:
        return no_data(ctx.why_missing(a_label, f"no {a_label} figure"))
    if y is None:
        return no_data(ctx.why_missing(b_label, f"no {b_label} figure"))
    return judge(x > y, x, y)


def revenue_accelerating(ctx: StockContext, _: Limits) -> Outcome:
    return _faster(
        ctx, "revenue_qoq_yoy", "revenue_cagr_3y", "Latest quarter revenue YoY", "Revenue CAGR 3y"
    )


def profit_outpacing_revenue(ctx: StockContext, _: Limits) -> Outcome:
    return _faster(ctx, "profit_cagr_3y", "revenue_cagr_3y", "Profit CAGR 3y", "Revenue CAGR 3y")


def roe_good(ctx: StockContext, lim: Limits) -> Outcome:
    o = _at_least(ctx, "roe", lim, "ROE")
    if o.value is not None:
        o.vars["value_plain"] = f"{o.value:.0f}"
    return o


def roe_vs_sector(ctx: StockContext, _: Limits) -> Outcome:
    return _vs_median(ctx, "roe", False, "ROE")


def roce_good(ctx: StockContext, lim: Limits) -> Outcome:
    return _at_least(ctx, "roce", lim, "ROCE")


def margin_vs_sector(ctx: StockContext, _: Limits) -> Outcome:
    return _vs_median(ctx, "op_margin", False, "Operating margin")


def margin_trend(ctx: StockContext, lim: Limits) -> Outcome:
    key, label = ("op_margin_change", "Operating margin")
    if ctx.financial or ctx.metric(key) is None:
        key, label = ("net_margin_change", "Net margin")
    m = ctx.metric(key)
    if m is None:
        return no_data("needs at least 2 years of revenue and profit")
    span = re.findall(r"FY(\d{4})", m.basis)
    years = str(int(span[1]) - int(span[0])) if len(span) == 2 else "3"
    return judge(float(m.value or 0) >= -lim.t, m.value, lim.threshold, margin=label, years=years)


def profitable_every_year(ctx: StockContext, _: Limits) -> Outcome:
    ni = ctx.series("net_income")
    if len(ni) < 2:
        return no_data(f"needs 2 years of results, have {len(ni)}")
    losses = int((ni < 0).sum())
    return judge(losses == 0, float(len(ni)), None, years=str(len(ni)), losses=str(losses))


def debt_equity(ctx: StockContext, lim: Limits) -> Outcome:
    v = ctx.v("debt_equity")
    if v is None:
        return no_data(ctx.why_missing("Debt/equity", "needs debt and positive equity"))
    if lim.threshold is None:
        return Outcome("pass", v, None, {"risk": ctx.risk_label, "threshold": "none set"})
    return judge(v <= lim.t, v, lim.threshold, risk=ctx.risk_label)


def interest_coverage(ctx: StockContext, lim: Limits) -> Outcome:
    v = ctx.v("interest_coverage")
    if v is None:
        interest = ctx.series("interest_expense")
        if not interest.empty and interest.iloc[-1] == 0:
            return Outcome("pass", None, lim.threshold, text="No interest to pay.")
        return no_data(ctx.why_missing("Interest coverage", "needs EBIT and interest expense"))
    return judge(v >= lim.t, v, lim.threshold)


def current_ratio(ctx: StockContext, lim: Limits) -> Outcome:
    return _at_least(ctx, "current_ratio", lim, "Current ratio")


def fcf_positive(ctx: StockContext, _: Limits) -> Outcome:
    v = ctx.v("fcf")
    if v is None:
        return no_data(ctx.why_missing("Free cash flow", "needs operating cash flow and capex"))
    return judge(v > 0, v, 0.0)


def debt_trend(ctx: StockContext, _: Limits) -> Outcome:
    debt = ctx.series("total_debt")
    if len(debt) < 2:
        return no_data(f"needs debt for 2 years, have {len(debt)}")
    first_d, last_d = debt.index[0], debt.index[-1]
    years = str(round((last_d - first_d).days / 365.25))
    d0, d1 = float(debt.iloc[0]), float(debt.iloc[-1])
    if d0 == 0 and d1 == 0:
        return Outcome("pass", 0.0, 0.0, text=f"Debt-free throughout the last {years} years.")
    eq = ctx.series("equity")
    e0 = float(eq[first_d]) if first_d in eq.index else None
    e1 = float(eq[last_d]) if last_d in eq.index else None
    if e0 and e1 and e0 > 0 and e1 > 0:
        r0, r1 = d0 / e0, d1 / e1
        moved = "fell" if r1 <= r0 else "rose"
        text = (
            f"Debt {moved} from {r0:.2f}× to {r1:.2f}× equity over {years} years "
            f"({ctx.money(d0)} to {ctx.money(d1)})."
        )
        return Outcome(
            "pass" if r1 <= r0 else "fail", round(r1, 2), round(r0, 2), {"trend_text": text}
        )
    moved = "fell" if d1 <= d0 else "rose"
    text = f"Debt {moved} from {ctx.money(d0)} to {ctx.money(d1)} over {years} years."
    return Outcome("pass" if d1 <= d0 else "fail", d1, d0, {"trend_text": text})


def pledge(ctx: StockContext, lim: Limits) -> Outcome:
    v = ctx.v("pledge_pct")
    if v is None:
        return no_data("needs a Screener.in upload with shareholding")
    return judge(v < lim.t, v, lim.threshold)


def _latest_ratio(ctx: StockContext, num: str, den: str) -> float | None:
    a = ctx.annual
    if a.empty or num not in a or den not in a:
        return None
    row = a[[num, den]].dropna()
    if row.empty or row.iloc[-1][den] <= 0:
        return None
    return float(row.iloc[-1][num] / row.iloc[-1][den] * 100)


def capital_cushion(ctx: StockContext, lim: Limits) -> Outcome:
    v = _latest_ratio(ctx, "equity", "total_assets")
    if v is None:
        return no_data("needs equity and total assets")
    return judge(v >= lim.t, v, lim.threshold)


def book_growth(ctx: StockContext, _: Limits) -> Outcome:
    eq = ctx.series("equity")
    if len(eq) < 2:
        return no_data(f"needs equity for 2 years, have {len(eq)}")
    years = str(round((eq.index[-1] - eq.index[0]).days / 365.25))
    e0, e1 = float(eq.iloc[0]), float(eq.iloc[-1])
    return judge(e1 > e0, e1, e0, first=ctx.money(e0), years=years)


def roa(ctx: StockContext, lim: Limits) -> Outcome:
    v = _latest_ratio(ctx, "net_income", "total_assets")
    if v is None:
        return no_data("needs net profit and total assets")
    return judge(v >= lim.t, v, lim.threshold)


def _price_vs(ctx: StockContext, avg: str, days: int) -> Outcome:
    close, ma = ctx.daily.get("close"), ctx.daily.get(avg)
    if close is None or ma is None:
        return no_data(f"needs {days} days of prices")
    return judge(close > ma, close, ma)


def above_sma200(ctx: StockContext, _: Limits) -> Outcome:
    return _price_vs(ctx, "sma200", 200)


def above_sma50(ctx: StockContext, _: Limits) -> Outcome:
    return _price_vs(ctx, "sma50", 50)


def rsi_healthy(ctx: StockContext, lim: Limits) -> Outcome:
    v = ctx.daily.get(ctx.rsi_key)
    if v is None:
        return no_data("needs a few weeks of prices")
    lo, hi = lim.threshold or 0, lim.upper or 100
    zone = "overheated" if v > hi else "weak"
    return judge(lo <= v <= hi, v, lo, zone=zone)


def macd_positive(ctx: StockContext, _: Limits) -> Outcome:
    h = ctx.daily.get("macd_hist")
    if h is None:
        return no_data("needs a few months of prices")
    return judge(h > 0, h, 0.0)


def beats_nifty_6m(ctx: StockContext, _: Limits) -> Outcome:
    v = ctx.market.get("rs_6m")
    if v is None:
        return no_data("needs 6 months of prices for the stock and the Nifty 50")
    return judge(v > 0, v, 0.0)


def obv_rising(ctx: StockContext, lim: Limits) -> Outcome:
    v = ctx.daily.get("obv_slope")
    if v is None:
        return no_data("needs volume data")
    return judge(v > (lim.threshold or 0), v, lim.threshold)


def _no_dividend() -> Outcome:
    return Outcome("fail", text="Pays no dividend.")


def pays_dividend(ctx: StockContext, _: Limits) -> Outcome:
    pays = ctx.pays_dividend
    if pays is None:
        return no_data("needs a dividend figure (cash-flow statement)")
    return judge(pays, ctx.v("dividend_yield"))


def _dividend_rule(fn: StockRule) -> StockRule:
    """Non-payers fail every dividend check with the same plain sentence."""

    def wrapped(ctx: StockContext, lim: Limits) -> Outcome:
        pays = ctx.pays_dividend
        if pays is None:
            return no_data("needs a dividend figure (cash-flow statement)")
        return fn(ctx, lim) if pays else _no_dividend()

    return wrapped


@_dividend_rule
def yield_high(ctx: StockContext, lim: Limits) -> Outcome:
    return _at_least(ctx, "dividend_yield", lim, "Dividend yield")


@_dividend_rule
def dividend_consistent(ctx: StockContext, _: Limits) -> Outcome:
    divs = ctx.series("dividends_paid")
    if len(divs) < 2:
        return no_data(f"needs dividends for 2 years, have {len(divs)}")
    paid = int((divs > 0).sum())
    return judge(paid == len(divs), float(paid), float(len(divs)), years=str(len(divs)))


@_dividend_rule
def dividend_growing(ctx: StockContext, _: Limits) -> Outcome:
    divs = ctx.series("dividends_paid")
    if len(divs) < 2:
        return no_data(f"needs dividends for 2 years, have {len(divs)}")
    d0, d1 = float(divs.iloc[0]), float(divs.iloc[-1])
    years = str(round((divs.index[-1] - divs.index[0]).days / 365.25))
    return judge(d1 > d0, d1, d0, first=ctx.money(d0), years=years)


@_dividend_rule
def payout_sustainable(ctx: StockContext, lim: Limits) -> Outcome:
    rows = ctx.annual[["dividends_paid", "net_income"]].dropna() if not ctx.annual.empty else None
    if rows is None or rows.empty:
        return no_data("needs dividends paid and net profit")
    div, ni = float(rows.iloc[-1]["dividends_paid"]), float(rows.iloc[-1]["net_income"])
    if ni <= 0:
        return Outcome("fail", text="Paid a dividend in a loss-making year.")
    v = div / ni * 100
    return judge(v <= lim.t, v, lim.threshold)


@_dividend_rule
def fcf_covers_dividend(ctx: StockContext, _: Limits) -> Outcome:
    rows = (
        ctx.annual[["dividends_paid", "free_cash_flow"]].dropna() if not ctx.annual.empty else None
    )
    if rows is None or rows.empty:
        return no_data("needs dividends paid and free cash flow")
    div, fcf = float(rows.iloc[-1]["dividends_paid"]), float(rows.iloc[-1]["free_cash_flow"])
    return judge(fcf >= div, div, fcf)


STOCK_RULES: dict[str, StockRule] = {
    "pe_vs_sector": pe_vs_sector,
    "pe_vs_history": pe_vs_history,
    "peg": peg,
    "fair_value": fair_value_check,
    "ev_ebitda_vs_sector": ev_ebitda_vs_sector,
    "pb_vs_sector": pb_vs_sector,
    "revenue_cagr": revenue_cagr,
    "profit_cagr": profit_cagr,
    "revenue_quarter": revenue_quarter,
    "profit_quarter": profit_quarter,
    "revenue_accelerating": revenue_accelerating,
    "profit_outpacing_revenue": profit_outpacing_revenue,
    "roe_good": roe_good,
    "roe_vs_sector": roe_vs_sector,
    "roce_good": roce_good,
    "margin_vs_sector": margin_vs_sector,
    "margin_trend": margin_trend,
    "profitable_every_year": profitable_every_year,
    "debt_equity": debt_equity,
    "interest_coverage": interest_coverage,
    "current_ratio": current_ratio,
    "fcf_positive": fcf_positive,
    "debt_trend": debt_trend,
    "pledge": pledge,
    "capital_cushion": capital_cushion,
    "book_growth": book_growth,
    "roa": roa,
    "above_sma200": above_sma200,
    "above_sma50": above_sma50,
    "rsi_healthy": rsi_healthy,
    "macd_positive": macd_positive,
    "beats_nifty_6m": beats_nifty_6m,
    "obv_rising": obv_rising,
    "pays_dividend": pays_dividend,
    "yield_high": yield_high,
    "dividend_consistent": dividend_consistent,
    "dividend_growing": dividend_growing,
    "payout_sustainable": payout_sustainable,
    "fcf_covers_dividend": fcf_covers_dividend,
}


# ---------------------------------------------------------------------------- funds


@dataclass
class FundContext:
    report: FundReport
    expense_limit: float


FundRule = Callable[[FundContext, Limits], Outcome]


def _beat_bench(years: int) -> FundRule:
    def rule(ctx: FundContext, _: Limits) -> Outcome:
        r = ctx.report
        if r.benchmark is None:
            return no_data("no equity benchmark for this kind of fund")
        f, b = r.returns.get(years), r.benchmark_returns.get(years)
        if f is None or b is None:
            return no_data(f"needs {years} year{'s' if years > 1 else ''} of NAV history")
        return judge(f >= b, f, b, bench=r.benchmark.label)

    return rule


def above_risk_free(ctx: FundContext, lim: Limits) -> Outcome:
    f = ctx.report.returns.get(3)
    if f is None:
        return no_data("needs 3 years of NAV history")
    return judge(f >= lim.t, f, lim.threshold)


def _rolling(ctx: FundContext, years: int) -> Rolling | None:
    return next((x for x in ctx.report.rolling if x.years == years), None)


def _beat_share(years: int) -> FundRule:
    def rule(ctx: FundContext, lim: Limits) -> Outcome:
        if ctx.report.benchmark is None:
            return no_data("no equity benchmark for this kind of fund")
        r = _rolling(ctx, years)
        if r is None:
            return no_data(f"needs more than {years} year{'s' if years > 1 else ''} of NAV history")
        v = r.beat_share * 100
        return judge(v >= lim.t, v, lim.threshold)

    return rule


def rolling3_avg_excess(ctx: FundContext, lim: Limits) -> Outcome:
    if ctx.report.benchmark is None:
        return no_data("no equity benchmark for this kind of fund")
    r = _rolling(ctx, 3)
    if r is None:
        return no_data("needs more than 3 years of NAV history")
    return judge(r.avg_excess >= lim.t, r.avg_excess, lim.threshold)


def _vs_bench_risk(attr: str, higher_is_better: bool) -> FundRule:
    def rule(ctx: FundContext, _: Limits) -> Outcome:
        r = ctx.report
        f = getattr(r.risk, attr, None) if r.risk else None
        b = getattr(r.benchmark_risk, attr, None) if r.benchmark_risk else None
        if r.benchmark is None:
            return no_data("no equity benchmark for this kind of fund")
        if f is None or b is None:
            return no_data("needs a year of NAV history alongside the benchmark")
        return judge(f >= b if higher_is_better else f <= b, f, b)

    return rule


def overlap_low(ctx: FundContext, lim: Limits) -> Outcome:
    ov = ctx.report.overlaps
    if not ov:
        return no_data("needs the portfolio file for this fund and your others (Import)")
    top = max(ov, key=lambda o: o.pct)
    return judge(top.pct <= lim.t, top.pct, lim.threshold, other=top.name)


def direct_plan(ctx: FundContext, _: Limits) -> Outcome:
    plan = ctx.report.plan
    if plan is None:
        return no_data("plan (Direct or Regular) unknown")
    gap = ctx.report.direct_gap_pp
    return judge(plan == "direct", None, gap=f" (about {gap:.1f} pp a year)" if gap else "")


def expense_ok(ctx: FundContext, _: Limits) -> Outcome:
    ter = ctx.report.expense_ratio_pct
    if ter is None:
        return no_data("enter the expense ratio on the fund's page")
    asset = ctx.report.asset_class
    return judge(ter <= ctx.expense_limit, ter, ctx.expense_limit, asset=asset)


FUND_RULES: dict[str, FundRule] = {
    "beat_bench_1y": _beat_bench(1),
    "beat_bench_3y": _beat_bench(3),
    "beat_bench_5y": _beat_bench(5),
    "above_risk_free": above_risk_free,
    "rolling3_beat_share": _beat_share(3),
    "rolling3_avg_excess": rolling3_avg_excess,
    "rolling1_beat_share": _beat_share(1),
    "volatility_vs_bench": _vs_bench_risk("volatility", False),
    "drawdown_vs_bench": _vs_bench_risk("max_drawdown", True),  # drawdowns are negative %
    "overlap_low": overlap_low,
    "sharpe_vs_bench": _vs_bench_risk("sharpe", True),
    "sortino_vs_bench": _vs_bench_risk("sortino", True),
    "direct_plan": direct_plan,
    "expense_ok": expense_ok,
}
