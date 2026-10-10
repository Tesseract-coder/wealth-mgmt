"""Return and risk maths on price / NAV series. All results are percent unless noted.

Series are pandas Series indexed by date (ascending). Nothing is interpolated: a period that
the history doesn't cover returns None.
"""

import math
from dataclasses import dataclass
from datetime import date, timedelta

import numpy as np
import pandas as pd

TOLERANCE_DAYS = 7  # a series starting this close to the period start still covers it


def _dates(s: pd.Series) -> pd.Series:
    s = s.dropna()
    s.index = pd.to_datetime(s.index)
    return s.sort_index()


def value_on(s: pd.Series, d: date) -> tuple[date, float] | None:
    """Last value on or before d."""
    sub = s.loc[: pd.Timestamp(d)]
    if sub.empty:
        return None
    return sub.index[-1].date(), float(sub.iloc[-1])


def cagr(first: float, last: float, days: float) -> float | None:
    if first <= 0 or last <= 0 or days <= 0:
        return None
    return float(((last / first) ** (365.25 / days) - 1) * 100)


def trailing_cagr(s: pd.Series, years: int) -> float | None:
    """Point-to-point CAGR over the last `years` years; None if the history is shorter."""
    s = _dates(s)
    if len(s) < 2:
        return None
    end = s.index[-1].date()
    start = (
        end.replace(year=end.year - years)
        if not (end.month == 2 and end.day == 29)
        else end - timedelta(days=365 * years)
    )
    if s.index[0].date() > start + timedelta(days=TOLERANCE_DAYS):
        return None
    v0 = value_on(s, start) or (s.index[0].date(), float(s.iloc[0]))
    return cagr(v0[1], float(s.iloc[-1]), (end - v0[0]).days)


@dataclass(frozen=True)
class RiskStats:
    start: date
    end: date
    years: float
    cagr: float | None
    volatility: float  # annualised, %
    sharpe: float | None
    sortino: float | None
    max_drawdown: float  # %, negative
    drawdown_peak: date
    drawdown_trough: date


def risk_stats(s: pd.Series, risk_free_pct: float, years: int, min_days: int) -> RiskStats | None:
    s = _dates(s)
    if len(s) < 3:
        return None
    end = s.index[-1]
    s = s.loc[end - pd.DateOffset(years=years) :]
    span = (s.index[-1] - s.index[0]).days
    if span < min_days:
        return None
    r = s.pct_change().dropna()
    ppy = len(r) / (span / 365.25)
    vol = float(r.std(ddof=1) * math.sqrt(ppy))
    g = cagr(float(s.iloc[0]), float(s.iloc[-1]), span)
    rf_per = (1 + risk_free_pct / 100) ** (1 / ppy) - 1
    downside = np.minimum(r.to_numpy() - rf_per, 0.0)
    dd_dev = float(math.sqrt(float(np.mean(downside**2))) * math.sqrt(ppy))
    sharpe = None if g is None or vol <= 0 else (g - risk_free_pct) / (vol * 100)
    sortino = None if g is None or dd_dev <= 0 else (g - risk_free_pct) / (dd_dev * 100)
    peak = s.cummax()
    dd = s / peak - 1
    trough = dd.idxmin()
    peak_date = s.loc[:trough].idxmax()
    return RiskStats(
        start=s.index[0].date(),
        end=s.index[-1].date(),
        years=round(span / 365.25, 2),
        cagr=None if g is None else round(g, 2),
        volatility=round(vol * 100, 2),
        sharpe=None if sharpe is None else round(sharpe, 2),
        sortino=None if sortino is None else round(sortino, 2),
        max_drawdown=round(float(dd.min()) * 100, 2),
        drawdown_peak=peak_date.date(),
        drawdown_trough=trough.date(),
    )


@dataclass(frozen=True)
class Rolling:
    years: int
    windows: int
    fund_avg: float
    bench_avg: float
    avg_excess: float  # fund − benchmark, percentage points a year
    beat_share: float  # share of windows where the fund beat the benchmark (0–1)
    worst_excess: float
    best_excess: float
    first_start: date
    last_start: date


def rolling_vs(fund: pd.Series, bench: pd.Series, years: int, step_days: int) -> Rolling | None:
    """Rolling `years`-year CAGR of the fund vs the benchmark, a window starting every step."""
    f, b = _dates(fund), _dates(bench)
    if len(f) < 2 or len(b) < 2:
        return None
    first = max(f.index[0], b.index[0])
    last = min(f.index[-1], b.index[-1])
    starts = pd.date_range(first, last - pd.DateOffset(years=years), freq=f"{step_days}D")
    rows = []
    for st in starts:
        en = st + pd.DateOffset(years=years)
        fv0, fv1 = value_on(f, st.date()), value_on(f, en.date())
        bv0, bv1 = value_on(b, st.date()), value_on(b, en.date())
        if not (fv0 and fv1 and bv0 and bv1):
            continue
        days = (en - st).days
        fc = cagr(fv0[1], fv1[1], days)
        bc = cagr(bv0[1], bv1[1], days)
        if fc is not None and bc is not None:
            rows.append((st.date(), fc, bc))
    if not rows:
        return None
    fcs = np.array([x[1] for x in rows])
    bcs = np.array([x[2] for x in rows])
    ex = fcs - bcs
    return Rolling(
        years=years,
        windows=len(rows),
        fund_avg=round(float(fcs.mean()), 2),
        bench_avg=round(float(bcs.mean()), 2),
        avg_excess=round(float(ex.mean()), 2),
        beat_share=round(float((ex > 0).mean()), 3),
        worst_excess=round(float(ex.min()), 2),
        best_excess=round(float(ex.max()), 2),
        first_start=rows[0][0],
        last_start=rows[-1][0],
    )


def xirr(flows: list[tuple[date, float]]) -> float | None:
    """Annualised internal rate of return (%) of dated cash flows: money in < 0, money out > 0.

    None when it can't be defined (all flows one sign) or doesn't converge."""
    flows = sorted((d, a) for d, a in flows if a != 0)
    if not flows or not any(a < 0 for _, a in flows) or not any(a > 0 for _, a in flows):
        return None
    t0 = flows[0][0]
    ts = np.array([(d - t0).days / 365.0 for d, _ in flows])
    cf = np.array([a for _, a in flows])

    def npv(r: float) -> float:
        return float(np.sum(cf / (1 + r) ** ts))

    lo, hi = -0.9999, 100.0
    f_lo, f_hi = npv(lo), npv(hi)
    if f_lo * f_hi > 0:
        return None
    for _ in range(200):  # bisection: robust for the irregular flows of real portfolios
        mid = (lo + hi) / 2
        f_mid = npv(mid)
        if abs(f_mid) < 1e-7 or hi - lo < 1e-10:
            return round(mid * 100, 2)
        if f_lo * f_mid < 0:
            hi = mid
        else:
            lo, f_lo = mid, f_mid
    return round((lo + hi) / 2 * 100, 2)


def daily_returns(s: pd.Series) -> pd.Series:
    return _dates(s).pct_change().dropna()


def beta(
    asset: pd.Series, bench: pd.Series, lookback: int, min_obs: int
) -> tuple[float | None, int]:
    """Beta of returns on common dates over the last `lookback` observations."""
    j = pd.concat([_dates(asset), _dates(bench)], axis=1, join="inner").dropna()
    r = j.pct_change().dropna().iloc[-lookback:]
    if len(r) < min_obs:
        return None, len(r)
    var = float(r.iloc[:, 1].var(ddof=1))
    if var <= 0:
        return None, len(r)
    return float(r.iloc[:, 0].cov(r.iloc[:, 1]) / var), len(r)
