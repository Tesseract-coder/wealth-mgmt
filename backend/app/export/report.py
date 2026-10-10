"""The portfolio report: one self-contained HTML page (no external files, no network) that
prints cleanly to PDF from any browser. Every value is HTML-escaped; numbers come from the
same cached analysis as the dashboard, and anything missing is shown as "—" with its reason."""

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from html import escape

from fastapi import HTTPException
from sqlmodel import Session

from app.api.funds import mf_holdings, portfolio_actions, portfolio_summary
from app.api.screener import screen_scan
from app.api.signals import holdings_signals
from app.core.formatting import format_freshness, format_inr, now_ist
from app.core.profiles import get_profiles
from app.models.schemas import (
    ActionsOut,
    HoldingSignalsOut,
    MFHoldingsAnalysisOut,
    PortfolioSummaryOut,
    ScreenIn,
    ScreenResultOut,
    SliceOut,
)

# Signal → pill tone. The pill always carries the signal's words too (never colour alone).
TONE = {
    "strong_buy": "good",
    "buy": "good",
    "continue": "good",
    "hold": "neutral",
    "review": "warn",
    "reduce": "warn",
    "switch": "bad",
    "sell": "bad",
    "no_signal": "muted",
    "insufficient_data": "muted",
}
SEVERITY = {"high": "bad", "medium": "warn", "low": "neutral"}


@dataclass
class ReportData:
    summary: PortfolioSummaryOut
    stocks: HoldingSignalsOut
    funds: MFHoldingsAnalysisOut
    actions: ActionsOut
    screener: ScreenResultOut | None
    screener_note: str | None


def gather(session: Session, screen: ScreenIn) -> ReportData:
    """Everything the report shows, from cached data only (no downloads)."""
    scr: ScreenResultOut | None = None
    note: str | None = None
    try:
        scr = screen_scan(screen, session)
    except HTTPException as e:
        note = f"{e.detail} Open the Screener page to run one."
    return ReportData(
        portfolio_summary(session),
        holdings_signals(None, None, session),
        mf_holdings(session),
        portfolio_actions(session),
        scr,
        note,
    )


# ------------------------------------------------------------------------------ helpers


def e(v: object) -> str:
    return "—" if v is None or v == "" else escape(str(v))


def inr(v: float | None, decimals: int = 0) -> str:
    return escape(format_inr(v, decimals))


def pct(v: float | None, digits: int = 1, sign: bool = True) -> str:
    """v is already in percent (12.3 → '+12.3%')."""
    if v is None:
        return "—"
    s = "+" if sign and v > 0 else ""
    return f"{s}{v:.{digits}f}%".replace("-", "−")


def frac(v: float | None, digits: int = 1) -> str:
    """v is a fraction (0.123 → '12.3%')."""
    return "—" if v is None else f"{v * 100:.{digits}f}%"


def num(v: float | None, digits: int = 0) -> str:
    return "—" if v is None else f"{v:,.{digits}f}"


def updown(v: float | None) -> str:
    return "" if v is None or v == 0 else ("up" if v > 0 else "down")


def pill(key: str, label: str) -> str:
    return f'<span class="pill {TONE.get(key, "muted")}">{e(label)}</span>'


def table(head: Sequence[str], rows: Iterable[str], numeric: Sequence[int] = ()) -> str:
    ths = "".join(
        f'<th{" class=num" if i in numeric else ""} scope="col">{e(h)}</th>'
        for i, h in enumerate(head)
    )
    body = "".join(rows)
    return f'<div class="scroll"><table><thead><tr>{ths}</tr></thead><tbody>{body}</tbody></table></div>'


def ul(items: Iterable[str], cls: str = "") -> str:
    lis = "".join(f"<li>{e(i)}</li>" for i in items)
    return f'<ul class="{cls}">{lis}</ul>' if lis else ""


def bars(slices: Sequence[SliceOut], limit: float | None = None) -> str:
    out = []
    for s in slices:
        over = limit is not None and s.limited and s.weight > limit
        mark = " · above your limit" if over else ""
        out.append(
            f'<div class="bar"><span class="bl">{e(s.label)}</span>'
            f'<span class="bt"><span class="bf{" over" if over else ""}" '
            f'style="width:{min(max(s.weight, 0), 1) * 100:.1f}%"></span></span>'
            f'<span class="bv">{frac(s.weight)} · {inr(s.value)}{mark}</span></div>'
        )
    return "".join(out) or '<p class="muted">No holdings.</p>'


# ------------------------------------------------------------------------------ sections


def _kpis(s: PortfolioSummaryOut) -> str:
    def k(label: str, value: str, sub: str = "", tone: str = "") -> str:
        return (
            f'<div class="kpi"><div class="kl">{e(label)}</div>'
            f'<div class="kv {tone}">{value}</div><div class="ks">{sub}</div></div>'
        )

    return (
        '<div class="kpis">'
        + k("Value", inr(s.total_value), f"Stocks {inr(s.stock_value)} · Funds {inr(s.fund_value)}")
        + k("Invested", inr(s.invested), e(s.invested_note) if s.invested_note else "")
        + k("Unrealised P&L", inr(s.pnl), pct(s.pnl_pct), updown(s.pnl))
        + k("Day change", inr(s.day_change), pct(s.day_change_pct, 2), updown(s.day_change))
        + k("XIRR", pct(s.xirr), e(s.xirr_basis))
        + k("Beta vs Nifty 50", num(s.beta, 2), e(s.beta_basis))
        + "</div>"
    )


def _actions(a: ActionsOut, n: int) -> str:
    if not a.actions:
        return '<p class="muted">Nothing needs attention under your rules.</p>'
    rows = [
        f"<tr><td>{pill_sev(x.severity)}</td><td><b>{e(x.subject)}</b></td>"
        f"<td>{e(x.title)}<div class='why'>{e(x.detail)}</div></td></tr>"
        for x in a.actions[:n]
    ]
    more = len(a.actions) - n
    tail = f'<p class="muted">… and {more} more in the app.</p>' if more > 0 else ""
    return table(["Severity", "Holding", "What and why"], rows) + tail


def pill_sev(sev: str) -> str:
    return f'<span class="pill {SEVERITY.get(sev, "neutral")}">{e(sev.capitalize())}</span>'


def _stocks(d: HoldingSignalsOut, n_reasons: int) -> str:
    if not d.holdings:
        return '<p class="muted">No stock holdings imported yet.</p>'
    rows = []
    for h in sorted(d.holdings, key=lambda h: -(h.value or 0)):
        over = h.weight is not None and h.weight > h.max_weight
        reasons = [f"▲ {r}" for r in h.top_bullish[:n_reasons]] + [
            f"▼ {r}" for r in h.top_bearish[:n_reasons]
        ]
        flags = [f"⚑ {f.text}" for f in h.flags if f.text not in h.rule]
        stop = inr(h.stop, 2) + (' <b class="down">breached</b>' if h.stop_breached else "")
        fresh = (
            ""
            if h.price_freshness.status == "fresh"
            else f"<div class='why warn-t'>Price {e(h.price_freshness.status)}: "
            f"{e(h.price_freshness.reason)}</div>"
        )
        conf = h.confidence.capitalize() if h.confidence else None
        action = h.rebalance.text if h.rebalance.action != "none" else ""
        rows.append(
            "<tr>"
            f"<td><b>{e(h.label)}</b><div class='why'>{e(h.ticker)} · {e(h.sector)}</div>{fresh}</td>"
            f"<td class=num>{num(h.quantity, 0)}</td>"
            f"<td class=num>{inr(h.avg_price, 2)}<div class='why'>LTP {inr(h.price, 2)}</div></td>"
            f"<td class=num>{inr(h.value)}</td>"
            f"<td class='num {updown(h.pnl)}'>{inr(h.pnl)}<div class='why'>{pct(h.pnl_pct)}</div></td>"
            f"<td class='num{' warn-t' if over else ''}'>{frac(h.weight)}"
            f"<div class='why'>max {frac(h.max_weight, 0)}</div></td>"
            f"<td>{pill(h.signal, h.signal_label)}<div class='why'>Confidence {e(conf)}</div></td>"
            f"<td class=num>{num(h.composite)}<div class='why'>T {num(h.technical)} · "
            f"F {num(h.fundamental)}</div></td>"
            f"<td class=num>{stop}</td>"
            f"<td><div>{e(h.rule)}</div>{ul(reasons + flags, 'why')}"
            f"{f'<div><b>Suggested:</b> {e(action)}</div>' if action else ''}</td>"
            "</tr>"
        )
    head = ["Stock", "Qty", "Avg price", "Value", "P&L", "Weight", "Signal", "Score", "Stop", "Why"]
    note = (
        f'<p class="muted">{e(d.style_label)} style (technical '
        f"{d.technical_weight * 100:.0f}%) · {e(d.risk_label)} risk. Score = composite 0–100 "
        "(T technical, F fundamental). Stop = ATR trailing stop.</p>"
    )
    return note + table(head, rows, numeric=[1, 2, 3, 4, 5, 7, 8]) + ul(d.notes, "notes")


def _funds(d: MFHoldingsAnalysisOut) -> str:
    if not d.funds:
        return '<p class="muted">No mutual fund holdings imported yet.</p>'
    rows = []
    for f in d.funds:
        h = f.holding
        ret = {r.years: r for r in f.returns}
        r3 = ret.get(3)
        bench = (
            f"<div class='why'>{e(f.benchmark.label)} 3y {pct(r3.benchmark if r3 else None)}</div>"
            if f.benchmark
            else ""
        )
        fresh = (
            ""
            if f.nav_freshness.status == "fresh"
            else f"<div class='why warn-t'>NAV {e(f.nav_freshness.status)}: "
            f"{e(f.nav_freshness.reason)}</div>"
        )
        rows.append(
            "<tr>"
            f"<td><b>{e(f.name)}</b><div class='why'>{e(f.category)} · {e(f.plan)}</div>{fresh}</td>"
            f"<td class=num>{inr(h.value if h else None)}</td>"
            f"<td class='num {updown(h.pnl if h else None)}'>{inr(h.pnl if h else None)}</td>"
            f"<td class=num>{pct(h.xirr if h else None)}</td>"
            f"<td class=num>{pct(ret[1].fund if 1 in ret else None)} / "
            f"{pct(r3.fund if r3 else None)} / {pct(ret[5].fund if 5 in ret else None)}{bench}</td>"
            f"<td class=num>{pct(f.expense_ratio_pct, 2, sign=False)}</td>"
            f"<td>{pill(f.signal, f.signal_label)}</td>"
            f"<td><div>{e(f.rule)}</div>{ul([r.text for r in f.reasons], 'why')}</td>"
            "</tr>"
        )
    head = ["Fund", "Value", "P&L", "XIRR", "1y / 3y / 5y", "Expense", "Signal", "Why"]
    return table(head, rows, numeric=[1, 2, 3, 4, 5]) + ul(d.warnings, "notes")


def _screener(d: ScreenResultOut | None, note: str | None, n: int) -> str:
    if d is None:
        return f'<p class="muted">{e(note)}</p>'
    if not d.candidates:
        return f'<p class="muted">{e(d.title)}: no stock passed the filters on this scan.</p>'
    rows = []
    for c in d.candidates[:n]:
        lv = c.levels
        entry = f"{inr(lv.entry_low, 2)} – {inr(lv.entry_high, 2)}" if lv else "—"
        stop = f"{inr(lv.stop, 2)}<div class='why'>{pct(-abs(lv.stop_pct))}</div>" if lv else "—"
        targets = " · ".join(f"{inr(t.price, 2)}" for t in lv.targets) if lv else "—"
        rows.append(
            "<tr>"
            f"<td class=num>{c.rank}</td>"
            f"<td><b>{e(c.label)}</b><div class='why'>{e(c.symbol)} · {e(c.sector)}</div></td>"
            f"<td>{pill(c.signal, c.signal_label)}</td>"
            f"<td class=num>{num(c.composite)}</td>"
            f"<td class=num>{entry}</td><td class=num>{stop}</td><td class=num>{targets}</td>"
            f"<td>{ul(c.bullish[:2] + [c.impact.text], 'why')}</td>"
            "</tr>"
        )
    head = ["#", "Stock", "Signal", "Score", "Entry zone", "Stop", "Targets", "Why"]
    ctx = (
        f'<p class="muted">{e(d.title)} on the {e(d.scan.universe_label)} scan of '
        f"{e(format_freshness(d.scan.created_at))} ({e(d.scan.style_label)} · "
        f"{e(d.scan.risk_label)} risk). Ideas to research, not recommendations.</p>"
    )
    stale = f'<p class="warn-t">{e(d.stale_note)}</p>' if d.stale_note else ""
    return ctx + stale + table(head, rows, numeric=[0, 3, 4, 5, 6])


def _data_notes(d: ReportData) -> str:
    stale = [
        f"{h.label}: {h.price_freshness.reason}"
        for h in d.stocks.holdings
        if h.price_freshness.status != "fresh"
    ] + [
        f"{f.name}: {f.nav_freshness.reason}"
        for f in d.funds.funds
        if f.nav_freshness.status != "fresh"
    ]
    items = [
        f"Prices as of {d.summary.as_of:%d %b %Y}." if d.summary.as_of else "No price date yet.",
        *d.summary.notes,
        *d.summary.warnings,
    ]
    out = ul(items)
    if stale:
        out += "<p><b>Stale or missing data</b> (shown as-is, never estimated):</p>" + ul(stale)
    out += (
        "<p>How every score and signal is calculated: <code>docs/SCORING_METHOD.md</code>. "
        f"Tax notes: {e(get_profiles().tax.verify_note)}</p>"
    )
    return out


CSS = """
:root{--bg:#fff;--fg:#0f172a;--mut:#64748b;--line:#e2e8f0;--card:#f8fafc;
--good:#047857;--goodbg:#d1fae5;--bad:#b91c1c;--badbg:#fee2e2;--warn:#92400e;--warnbg:#fef3c7;
--neu:#334155;--neubg:#e2e8f0;--bar:#475569}
@media screen and (prefers-color-scheme:dark){:root{--bg:#0f172a;--fg:#e2e8f0;--mut:#94a3b8;
--line:#1e293b;--card:#111c33;--good:#6ee7b7;--goodbg:#064e3b;--bad:#fca5a5;--badbg:#7f1d1d;
--warn:#fcd34d;--warnbg:#78350f;--neu:#cbd5e1;--neubg:#334155;--bar:#94a3b8}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);font:14px/1.45 system-ui,-apple-system,
"Segoe UI",Roboto,"Noto Sans",sans-serif}
main{max-width:1100px;margin:0 auto;padding:16px}
h1{font-size:22px;margin:0}h2{font-size:17px;margin:28px 0 8px;padding-bottom:4px;
border-bottom:1px solid var(--line)}
.meta{color:var(--mut);margin:4px 0 12px}
.disc{border:1px solid var(--warn);background:var(--warnbg);color:var(--fg);padding:8px 12px;
border-radius:6px;font-size:13px}
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:8px}
.kpi{background:var(--card);border:1px solid var(--line);border-radius:6px;padding:8px 10px}
.kl{color:var(--mut);font-size:12px}.kv{font-size:18px;font-weight:600}.ks{color:var(--mut);font-size:11px}
.up{color:var(--good)}.down{color:var(--bad)}.warn-t{color:var(--warn)}
.muted,.why,.notes{color:var(--mut)}.why{font-size:12px;margin:2px 0;padding-left:0;list-style:none}
.notes{font-size:12px}
.scroll{overflow-x:auto}
table{border-collapse:collapse;width:100%;font-size:13px}
th,td{text-align:left;vertical-align:top;padding:6px;border-bottom:1px solid var(--line)}
th{font-size:12px;color:var(--mut);font-weight:600}
.num{text-align:right;white-space:nowrap;font-variant-numeric:tabular-nums}
.pill{display:inline-block;border-radius:999px;padding:1px 8px;font-size:12px;font-weight:600;
white-space:nowrap;border:1px solid currentColor}
.pill.good{color:var(--good);background:var(--goodbg)}.pill.bad{color:var(--bad);background:var(--badbg)}
.pill.warn{color:var(--warn);background:var(--warnbg)}.pill.neutral{color:var(--neu);background:var(--neubg)}
.pill.muted{color:var(--mut);background:transparent}
.cols{display:grid;grid-template-columns:1fr 1fr;gap:16px}
.bar{display:grid;grid-template-columns:150px 1fr 200px;gap:8px;align-items:center;font-size:13px;margin:3px 0}
.bt{height:10px;background:var(--line);border-radius:5px;overflow:hidden}
.bf{display:block;height:100%;background:var(--bar)}.bf.over{background:var(--warn)}
.bl{overflow-wrap:anywhere}.bv{color:var(--mut);font-size:12px;white-space:nowrap}
.tools{float:right}.tools button{font:inherit;padding:4px 10px;border-radius:6px;
border:1px solid var(--line);background:var(--card);color:var(--fg);cursor:pointer}
footer{color:var(--mut);font-size:12px;border-top:1px solid var(--line);margin-top:24px;padding:8px 16px;
text-align:center}
@media (max-width:640px){.cols{grid-template-columns:1fr}.bar{grid-template-columns:100px 1fr}
.bv{grid-column:2}.tools{float:none;margin-bottom:8px}}
@page{size:A4 landscape;margin:12mm 10mm 16mm}
@media print{.tools{display:none}main{max-width:none;padding:0}body{font-size:11px}
table{font-size:10.5px}th,td{padding:3px 4px}tr,.kpi,.bar{break-inside:avoid}
h2{break-after:avoid}.scroll{overflow:visible}
.pill{-webkit-print-color-adjust:exact;print-color-adjust:exact}
.bf,.bt,.disc{-webkit-print-color-adjust:exact;print-color-adjust:exact}
footer{position:fixed;bottom:0;left:0;right:0;margin:0;padding:3px;background:#fff;font-size:9px}
main{padding-bottom:28px}}
"""


def render(d: ReportData, generated: str) -> str:
    p = get_profiles()
    rc = p.report
    disc = e(p.disclaimer)
    st = d.stocks
    sector_limit = p.risk_levels[st.risk].max_weight_per_sector
    title = f"Portfolio report · {now_ist():%d %b %Y}"
    return f"""<!doctype html>
<html lang="en-IN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'">
<title>{e(title)}</title><style>{CSS}</style></head>
<body><main>
<div class="tools"><button type="button" onclick="window.print()">Print / Save as PDF</button></div>
<h1>{e(title)}</h1>
<p class="meta">Generated {e(generated)} · {e(st.style_label)} style · {e(st.risk_label)} risk
· prices as of {e(f"{d.summary.as_of:%d %b %Y}" if d.summary.as_of else None)}</p>
<p class="disc"><b>Disclaimer:</b> {disc}</p>

<h2>Summary</h2>
{_kpis(d.summary)}

<h2>Action needed</h2>
{_actions(d.actions, rc.actions)}

<h2>Allocation</h2>
<div class="cols"><div><h3>By sector</h3>{bars(d.summary.by_sector, sector_limit)}
<p class="muted">Your sector limit: {frac(sector_limit, 0)} ({e(st.risk_label)} risk).</p></div>
<div><h3>By asset class</h3>{bars(d.summary.by_asset_class)}
<h3>By market cap</h3>{bars(d.summary.by_mcap)}</div></div>

<h2>Stocks</h2>
{_stocks(st, rc.top_reasons)}

<h2>Mutual funds</h2>
{_funds(d.funds)}

<h2>Screener ideas</h2>
{_screener(d.screener, d.screener_note, rc.screener_ideas)}

<h2>Data and method</h2>
{_data_notes(d)}
</main>
<footer>Portfolio Analyzer · {e(generated)} · {disc}</footer>
</body></html>"""


def build_report(session: Session, screen: ScreenIn) -> str:
    return render(gather(session, screen), format_freshness(now_ist()))
