"""The tables behind every export (CSV and Google Sheets), built once so both carry the same
columns. Numbers stay plain (no ₹ or grouping) so spreadsheets can compute with them."""

from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date, datetime

from fastapi import HTTPException
from sqlmodel import Session

from app.api.funds import mf_holdings, portfolio_actions, portfolio_summary
from app.api.screener import screen_scan
from app.api.signals import holdings_signals
from app.core.formatting import format_freshness, now_ist
from app.core.profiles import get_profiles
from app.models.schemas import (
    ActionsOut,
    HoldingSignalsOut,
    MFHoldingsAnalysisOut,
    PortfolioSummaryOut,
    ScreenIn,
    ScreenResultOut,
)

Value = str | float | int | bool | date | datetime | None


@dataclass
class Table:
    slug: str  # file-name stem, e.g. "stock-signals"
    title: str
    context: str  # profile / scan the numbers were computed under
    header: list[str]
    rows: list[list[Value]]
    inr_columns: list[int] = field(default_factory=list)  # 0-based, whole column
    inr_rows: list[int] = field(default_factory=list)  # 0-based data rows whose column 1 is ₹
    empty_note: str | None = None  # shown instead of rows when there are none
    heading: list[int] = field(default_factory=lambda: [0])  # columns that title a PDF card
    signals: list[str] = field(default_factory=list)  # per row: signal key, for PDF colours


def _pct(w: float | None) -> float | None:
    return None if w is None else round(w * 100, 2)


def _cols(header: Sequence[str], names: Sequence[str]) -> list[int]:
    return [header.index(n) for n in names]


# ------------------------------------------------------------------------------- stocks

STOCK_HEADER = [
    "Ticker", "Name", "Sector", "Quantity", "Avg price", "Last price", "Invested", "Value",
    "P&L", "P&L %", "Weight %", "Signal", "Composite", "Technical", "Fundamental",
    "Confidence", "Trailing stop", "Stop breached", "Suggested action", "Rule",
    "Red flags", "Top bullish", "Top bearish", "Price data",
]  # fmt: skip


def stocks_table(d: HoldingSignalsOut) -> Table:
    """Your stock holdings with signal, scores, confidence, stop and suggested action."""
    rows: list[list[Value]] = [
        [
            h.ticker,
            h.label,
            h.sector,
            h.quantity,
            h.avg_price,
            h.price,
            h.invested,
            h.value,
            h.pnl,
            h.pnl_pct,
            _pct(h.weight),
            h.signal_label,
            h.composite,
            h.technical,
            h.fundamental,
            h.confidence,
            h.stop,
            "yes" if h.stop_breached else "no",
            h.rebalance.text,
            h.rule,
            "; ".join(f.text for f in h.flags),
            "; ".join(h.top_bullish[:3]),
            "; ".join(h.top_bearish[:3]),
            h.price_freshness.reason,
        ]
        for h in d.holdings
    ]
    inr = ["Avg price", "Last price", "Invested", "Value", "P&L", "Trailing stop"]
    return Table(
        "stock-signals",
        "Stock signals",
        f"{d.style_label} · {d.risk_label} risk",
        STOCK_HEADER,
        rows,
        inr_columns=_cols(STOCK_HEADER, inr),
        empty_note="No stock holdings imported yet.",
        heading=[0, 1],
        signals=[h.signal for h in d.holdings],
    )


# --------------------------------------------------------------------------------- funds

FUND_HEADER = [
    "AMFI code", "Scheme", "Category", "Plan", "Units", "Invested", "Value", "P&L",
    "XIRR %", "XIRR basis", "1y %", "3y %", "5y %", "Benchmark", "Benchmark 3y %",
    "Expense ratio %", "Direct plan gap (pp/yr)", "Signal", "Rule", "Positives", "Concerns",
    "Notes",
]  # fmt: skip


def funds_table(d: MFHoldingsAnalysisOut) -> Table:
    """Your mutual funds with signal, returns vs benchmark, cost and reasons."""
    rows: list[list[Value]] = []
    for f in d.funds:
        ret = {r.years: r for r in f.returns}
        h = f.holding
        rows.append(
            [
                f.code,
                f.name,
                f.category,
                f.plan,
                h.units if h else None,
                h.invested if h else None,
                h.value if h else None,
                h.pnl if h else None,
                h.xirr if h else None,
                h.xirr_basis if h else None,
                *(ret[y].fund if y in ret else None for y in (1, 3, 5)),
                f.benchmark.label if f.benchmark else None,
                ret[3].benchmark if 3 in ret else None,
                f.expense_ratio_pct,
                f.direct_gap_pp,
                f.signal_label,
                f.rule,
                *(
                    "; ".join(r.text for r in f.reasons if r.direction == d) or None
                    for d in ("bullish", "bearish", "neutral")
                ),
            ]
        )
    return Table(
        "fund-signals",
        "Mutual fund signals",
        "Mutual funds",
        FUND_HEADER,
        rows,
        inr_columns=_cols(FUND_HEADER, ["Invested", "Value", "P&L"]),
        empty_note="No mutual fund holdings imported yet.",
        heading=[1],
        signals=[f.signal for f in d.funds],
    )


# ------------------------------------------------------------------------------ screener

SCREENER_HEADER = [
    "Rank", "Ticker", "Name", "Sector", "Signal", "Composite", "Technical", "Fundamental",
    "Confidence", "Last close", "Entry low", "Entry high", "Stop", "Stop %", "Target 1",
    "Target 2", "Target 3", "Levels timeframe", "Filters met", "Rule", "Red flags",
    "Top bullish", "Top bearish", "Price as of",
]  # fmt: skip


def screener_table(d: ScreenResultOut) -> Table:
    """The candidates of one screen on a stored scan. Shared with others, so nothing about
    your portfolio (whether you hold it, what it would do to your sectors) goes in."""
    rows: list[list[Value]] = []
    for c in d.candidates:
        lv = c.levels
        tg = [f"{t.label} {t.price}" for t in lv.targets] if lv else []
        rows.append(
            [
                c.rank, c.ticker, c.label, c.sector, c.signal_label, c.composite, c.technical,
                c.fundamental, c.confidence,
                lv.close if lv else None, lv.entry_low if lv else None,
                lv.entry_high if lv else None, lv.stop if lv else None,
                lv.stop_pct if lv else None, *(tg + [None, None, None])[:3],
                lv.interval if lv else None, "; ".join(c.passed), c.rule,
                "; ".join(f.text for f in c.flags), "; ".join(c.bullish), "; ".join(c.bearish),
                c.price_as_of,
            ]
        )  # fmt: skip
    ctx = (
        f"{d.title} · {d.scan.universe_label} · {d.scan.style_label} · {d.scan.risk_label} risk"
        f" · scan {format_freshness(d.scan.created_at)}"
    )
    return Table(
        "screener",
        f"Screener: {d.title}",
        ctx,
        SCREENER_HEADER,
        rows,
        inr_columns=_cols(SCREENER_HEADER, ["Last close", "Entry low", "Entry high", "Stop"]),
        empty_note="No stock passed this screen." + (f" {d.stale_note}" if d.stale_note else ""),
        heading=[0, 1, 2],
        signals=[c.signal for c in d.candidates],
    )


def screener_table_or_none(session: Session, body: ScreenIn) -> Table:
    """The screen's table, or an empty one explaining that there is no scan yet."""
    try:
        return screener_table(screen_scan(body, session))
    except HTTPException as e:
        return Table(
            "screener",
            "Screener",
            "No scan",
            SCREENER_HEADER,
            [],
            empty_note=f"{e.detail} Open the Screener page to run one.",
        )


# ------------------------------------------------------------------------------- summary


def _counts(labels: Sequence[str]) -> str:
    if not labels:
        return "none"
    return " · ".join(f"{k} {n}" for k, n in Counter(labels).most_common())


def summary_table(
    s: PortfolioSummaryOut,
    stocks: HoldingSignalsOut,
    funds: MFHoldingsAnalysisOut,
    actions: ActionsOut,
    screener: Table | None = None,
) -> Table:
    """One row per figure: value, P&L, XIRR, signal counts, stops and the top actions."""
    rows: list[list[Value]] = []
    inr: list[int] = []

    def add(item: str, value: Value, note: str | None = None, money: bool = False) -> None:
        if money:
            inr.append(len(rows))
        rows.append([item, value, note])

    add("Updated", format_freshness(now_ist()))
    add("Profile", f"{stocks.style_label} · {stocks.risk_label} risk")
    add("Portfolio value", s.total_value, f"prices as of {s.as_of}" if s.as_of else None, True)
    add("Stocks value", s.stock_value, None, True)
    add("Mutual funds value", s.fund_value, None, True)
    add("Invested", s.invested, s.invested_note, True)
    add("Unrealised P&L", s.pnl, None, True)
    add("Unrealised P&L %", s.pnl_pct)
    add("Day change", s.day_change, s.day_change_note, True)
    add("XIRR %", s.xirr, s.xirr_basis)
    add("Stock signals", _counts([h.signal_label for h in stocks.holdings]))
    add("Fund signals", _counts([f.signal_label for f in funds.funds]))
    breached = [h.label for h in stocks.holdings if h.stop_breached]
    add("Stops breached", len(breached), ", ".join(breached) or None)
    flagged = [h.label for h in stocks.holdings if h.flags]
    add("Stocks with red flags", len(flagged), ", ".join(flagged) or None)
    stale = [h.label for h in stocks.holdings if h.price_freshness.status != "fresh"]
    add("Stocks with stale or missing prices", len(stale), ", ".join(stale) or None)
    for i, a in enumerate(actions.actions[: get_profiles().sheets.summary_actions], start=1):
        add(f"Action {i} ({a.severity})", f"{a.subject}: {a.title}", a.detail)
    if screener is not None:
        add("Screener", f"{len(screener.rows)} idea(s)", f"{screener.title} · {screener.context}")
    for w in s.warnings:
        add("Note", w)
    return Table(
        "summary",
        "Portfolio summary",
        f"{stocks.style_label} · {stocks.risk_label} risk",
        ["Item", "Value", "Note"],
        rows,
        inr_rows=inr,
    )


@dataclass
class ExportTables:
    stocks: Table
    funds: Table
    screener: Table
    summary: Table


def build_all(session: Session, screen: ScreenIn) -> ExportTables:
    """Every table, computing each signal set once (cached data only, no downloads)."""
    stocks = holdings_signals(None, None, session)
    funds = mf_holdings(session)
    scr = screener_table_or_none(session, screen)
    summary = summary_table(
        portfolio_summary(session), stocks, funds, portfolio_actions(session), scr
    )
    return ExportTables(stocks_table(stocks), funds_table(funds), scr, summary)
