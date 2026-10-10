"""CSV exports of your signals. Numbers stay plain (no ₹ or grouping) so spreadsheets can
use them; every file ends with the generation time and the disclaimer."""

import csv
import io
from collections.abc import Iterable, Sequence

from fastapi import APIRouter, Depends
from fastapi.responses import Response
from sqlmodel import Session

from app.api.funds import mf_holdings
from app.api.signals import holdings_signals
from app.core.db import get_session
from app.core.formatting import format_freshness, now_ist
from app.core.profiles import get_profiles

router = APIRouter(prefix="/export", tags=["export"])


def _csv(
    filename: str, header: Sequence[str], rows: Iterable[Sequence[object]], context: str
) -> Response:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(header)
    for r in rows:
        w.writerow(["" if v is None else v for v in r])
    w.writerow([])
    w.writerow(["Generated", format_freshness(now_ist())])
    w.writerow(["Profile", context])
    w.writerow(["Disclaimer", get_profiles().disclaimer])
    stamp = now_ist().strftime("%Y-%m-%d")
    return Response(
        content="\ufeff" + buf.getvalue(),  # BOM so Excel reads ₹ and accents as UTF-8
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}-{stamp}.csv"'},
    )


def _pct(w: float | None) -> float | None:
    return None if w is None else round(w * 100, 2)


@router.get("/stocks.csv")
def stocks_csv(session: Session = Depends(get_session)) -> Response:
    """Your stock holdings with signal, scores, confidence, stop and suggested action."""
    d = holdings_signals(None, None, session)
    header = [
        "Ticker", "Name", "Sector", "Quantity", "Avg price", "Last price", "Invested", "Value",
        "P&L", "P&L %", "Weight %", "Signal", "Composite", "Technical", "Fundamental",
        "Confidence", "Trailing stop", "Stop breached", "Suggested action", "Rule",
        "Red flags", "Top bullish", "Top bearish", "Price data",
    ]  # fmt: skip
    rows = [
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
    return _csv("stock-signals", header, rows, f"{d.style_label} · {d.risk_label} risk")


@router.get("/funds.csv")
def funds_csv(session: Session = Depends(get_session)) -> Response:
    """Your mutual funds with signal, returns vs benchmark, cost and reasons."""
    d = mf_holdings(session)
    header = [
        "AMFI code", "Scheme", "Category", "Plan", "Units", "Invested", "Value", "P&L",
        "XIRR %", "XIRR basis", "1y %", "3y %", "5y %", "Benchmark", "Benchmark 3y %",
        "Expense ratio %", "Direct plan gap (pp/yr)", "Signal", "Rule", "Reasons",
    ]  # fmt: skip
    rows = []
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
                "; ".join(r.text for r in f.reasons),
            ]
        )
    return _csv("fund-signals", header, rows, "Mutual funds")
