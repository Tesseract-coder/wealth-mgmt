"""Your positions: weights vs the risk profile's limits, suggested trade sizes, and tax notes.

Values use the latest cached close (else the price in your import). Weights are shares of the
whole portfolio — stocks plus mutual funds — unless `rebalance.weight_base` is "stocks".
Nothing here places or prepares orders; quantities are suggestions to review.
"""

import math
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Literal

from sqlmodel import Session, col, select

from app.analysis.fundamental import sector_of
from app.core.formatting import format_inr, now_ist
from app.core.profiles import RebalanceConfig, RiskLevel, TaxConfig
from app.data.navs import latest_nav
from app.data.provider import DataProvider
from app.data.yahoo import yahoo_ticker
from app.importers.reference import ticker_resolver
from app.importers.snapshots import latest_snapshot
from app.models.tables import DailyBar, MFHolding, StockHolding


@dataclass(frozen=True)
class Lot:
    quantity: float
    avg_price: float
    purchase_date: date | None


@dataclass
class Position:
    ticker: str
    label: str
    quantity: float
    avg_price: float
    invested: float
    price: float | None
    price_source: str  # "close on 09 Oct 2026" | "your import"
    value: float | None
    sector: str | None
    lots: list[Lot]

    @property
    def pnl(self) -> float | None:
        return None if self.value is None else self.value - self.invested


@dataclass
class Portfolio:
    positions: dict[str, Position]
    total: float  # the weight base
    stock_value: float
    fund_value: float
    sector_values: dict[str, float]
    base: Literal["portfolio", "stocks"]
    notes: list[str] = field(default_factory=list)

    def weight(self, ticker: str) -> float | None:
        p = self.positions.get(ticker)
        if p is None or p.value is None or self.total <= 0:
            return None
        return p.value / self.total

    def sector_weight(self, sector: str | None) -> float | None:
        if not sector or self.total <= 0:
            return None
        return self.sector_values.get(sector, 0.0) / self.total


def _latest_close(session: Session, ticker: str) -> tuple[float, date] | None:
    bar = session.exec(
        select(DailyBar)
        .where(DailyBar.ticker == ticker, col(DailyBar.close).is_not(None))
        .order_by(col(DailyBar.date).desc())
        .limit(1)
    ).first()
    return (float(bar.close), bar.date) if bar and bar.close is not None else None


def stock_sector(provider: DataProvider, ticker: str) -> str | None:
    """NSE industry (else Yahoo's sector). ETFs are diversified and have no sector."""
    symbol = ticker.removesuffix(".NS") if ticker.endswith(".NS") else None
    sec = ticker_resolver().by_symbol.get(symbol) if symbol else None
    if sec is not None and sec.kind == "etf":
        return None
    raw = provider.fundamentals(ticker)
    return sector_of(symbol, raw.info if raw else {})[0]


def load_portfolio(
    session: Session,
    provider: DataProvider,
    cfg: RebalanceConfig,
    now: datetime | None = None,
) -> Portfolio:
    now = now or now_ist()
    notes: list[str] = []
    rows: list[StockHolding] = []
    snap = latest_snapshot(session, "stocks")
    if snap is not None:
        rows = list(
            session.exec(select(StockHolding).where(StockHolding.snapshot_id == snap.id)).all()
        )
    grouped: dict[str, list[StockHolding]] = defaultdict(list)
    for h in rows:
        if h.symbol and h.quantity > 0:
            grouped[yahoo_ticker(h.symbol, h.exchange)].append(h)
    positions: dict[str, Position] = {}
    for ticker, hs in grouped.items():
        qty = sum(h.quantity for h in hs)
        invested = sum(h.invested for h in hs)
        latest = _latest_close(session, ticker)
        imported = next((h.close_price for h in hs if h.close_price), None)
        if latest:
            price: float | None = latest[0]
            src = f"close on {latest[1]:%d %b %Y}"
        elif imported:
            price, src = imported, "your import"
        else:
            price, src = None, "no price"
            notes.append(f"{hs[0].name}: no price yet, left out of the weights")
        positions[ticker] = Position(
            ticker=ticker,
            label=hs[0].name,
            quantity=qty,
            avg_price=invested / qty if qty else 0.0,
            invested=invested,
            price=price,
            price_source=src,
            value=None if price is None else price * qty,
            sector=stock_sector(provider, ticker),
            lots=[Lot(h.quantity, h.avg_price, h.purchase_date) for h in hs],
        )
    fund_value = 0.0
    msnap = latest_snapshot(session, "mf")
    if msnap is not None:
        for m in session.exec(select(MFHolding).where(MFHolding.snapshot_id == msnap.id)).all():
            nav = latest_nav(session, m.amfi_code, now).nav if m.amfi_code else None
            if nav is not None:
                fund_value += nav * m.units
            elif m.current_value is not None:
                fund_value += m.current_value
            else:
                notes.append(f"{m.scheme_name}: no NAV or value, left out of the weights")
    stock_value = sum(p.value or 0.0 for p in positions.values())
    sectors: dict[str, float] = defaultdict(float)
    for p in positions.values():
        if p.sector and p.value:
            sectors[p.sector] += p.value
    total = stock_value + (fund_value if cfg.weight_base == "portfolio" else 0.0)
    if cfg.weight_base == "portfolio" and fund_value > 0:
        notes.append(
            "Weights are shares of your whole portfolio (stocks + mutual funds). Funds' own "
            "sector exposure isn't counted in sector weights."
        )
    return Portfolio(
        positions, total, stock_value, fund_value, dict(sectors), cfg.weight_base, notes
    )


# ---------------------------------------------------------------------------- trade sizes

Action = Literal["add", "trim", "exit", "none"]


@dataclass(frozen=True)
class Rebalance:
    action: Action
    quantity: int
    value: float | None
    target_weight: float | None
    text: str


def _pct(w: float) -> str:
    return f"{w * 100:.1f}%"


def add_amount(value: float, total: float, target: float) -> float:
    """New money x so that (value + x) / (total + x) = target."""
    return max(0.0, (target * total - value) / (1 - target))


def trim_amount(value: float, total: float, target: float) -> float:
    """Money x taken out so that (value − x) / (total − x) = target."""
    return max(0.0, (value - target * total) / (1 - target))


def suggest(
    signal: str,
    position: Position | None,
    price: float | None,
    portfolio: Portfolio | None,
    risk: RiskLevel,
    cfg: RebalanceConfig,
    *,
    sector_weight: float | None = None,
    sector: str | None = None,
    score_reduce: bool = False,
) -> Rebalance:
    """Quantity to add or trim to reach the signal's target weight (whole shares)."""
    max_w = risk.max_weight_per_stock
    if price is None or price <= 0:
        return Rebalance("none", 0, None, None, "No price, so no quantity can be suggested.")
    if portfolio is None or portfolio.total <= 0:
        return Rebalance("none", 0, None, None, "Import your holdings to get position sizes.")
    total = portfolio.total
    value = (position.value or 0.0) if position else 0.0
    held = position.quantity if position else 0.0
    weight = value / total
    if signal == "sell":
        if held <= 0:
            return Rebalance("none", 0, None, 0.0, "Not held: avoid adding.")
        return Rebalance(
            "exit", int(math.ceil(held)), value, 0.0, f"Sell all {held:g} shares to exit."
        )
    if signal == "reduce":
        if held <= 0:
            return Rebalance("none", 0, None, None, "Not held: no action.")
        qty = 0
        why = []
        if weight > max_w:
            qty = math.ceil(trim_amount(value, total, max_w) / price)
            why.append(f"bring the weight from {_pct(weight)} to your {_pct(max_w)} limit")
        if score_reduce:
            q2 = math.ceil(held * (1 - cfg.reduce_keep))
            if q2 > qty:
                qty = q2
                why = [f"cut the position to {cfg.reduce_keep * 100:.0f}% on a weak score"]
        qty = min(qty, int(math.ceil(held)))
        if qty * price < cfg.min_trade_value_inr:
            return Rebalance("none", 0, None, None, "The suggested trim is too small to matter.")
        new_w = (value - qty * price) / (total - qty * price) if total > qty * price else 0.0
        return Rebalance(
            "trim",
            qty,
            round(qty * price, 2),
            round(new_w, 4),
            f"Trim {qty} share(s) (≈ {format_inr(qty * price, 0)}) to " + "; ".join(why) + ".",
        )
    if signal in ("buy", "strong_buy"):
        target = max_w * (cfg.strong_buy_target if signal == "strong_buy" else cfg.buy_target)
        if weight >= target:
            return Rebalance(
                "none",
                0,
                None,
                target,
                f"Already at {_pct(weight)}, at or above the {_pct(target)} target weight.",
            )
        x = add_amount(value, total, target)
        limit_txt = ""
        if sector and sector_weight is not None:
            ws = risk.max_weight_per_sector
            sv = sector_weight * total
            room = add_amount(sv, total, ws)
            if room < x:
                x = room
                limit_txt = f", capped by your {_pct(ws)} limit for {sector}"
        qty = int(math.floor(x / price))
        if qty <= 0 or qty * price < cfg.min_trade_value_inr:
            return Rebalance(
                "none", 0, None, target, "No room to add within your limits" + limit_txt + "."
            )
        new_w = (value + qty * price) / (total + qty * price)
        return Rebalance(
            "add",
            qty,
            round(qty * price, 2),
            round(new_w, 4),
            f"Add {qty} share(s) (≈ {format_inr(qty * price, 0)} of new money) to move from "
            f"{_pct(weight)} toward the {_pct(target)} target{limit_txt}.",
        )
    return Rebalance("none", 0, None, None, "No change suggested.")


# ---------------------------------------------------------------------------- tax


@dataclass(frozen=True)
class TaxNote:
    holding_days: int | None
    term: Literal["short", "long", "mixed", "unknown"]
    long_term_from: date | None  # when the earliest short-term lot turns long-term
    text: list[str]
    verify_note: str


def tax_note(
    position: Position | None,
    sell_qty: float,
    price: float | None,
    cfg: TaxConfig,
    today: date | None = None,
) -> TaxNote | None:
    """Holding period and whether selling `sell_qty` (first-in, first-out) is STCG or LTCG.

    Equity held more than `equity_ltcg_min_holding_days` days is long-term. Rates are from
    config and must be verified; the yearly LTCG exemption is shared across all your sales,
    so it isn't applied per stock."""
    if position is None:
        return None
    today = today or now_ist().date()
    min_days = cfg.equity_ltcg_min_holding_days
    dated = [lot for lot in position.lots if lot.purchase_date is not None]
    if not dated:
        return TaxNote(
            None,
            "unknown",
            None,
            [
                "Purchase date unknown: your import has no buy date, so we can't tell whether a "
                "sale would be short-term (STCG) or long-term (LTCG). Add the date with manual "
                "entry or a file that includes it."
            ],
            cfg.verify_note,
        )
    lots = sorted(dated, key=lambda lot: lot.purchase_date or date.min)
    first = lots[0].purchase_date or today
    days = (today - first).days
    lines: list[str] = []
    undated = sum(lot.quantity for lot in position.lots if lot.purchase_date is None)
    if undated:
        lines.append(f"{undated:g} share(s) have no purchase date; they're left out below.")

    def is_long(d: date) -> bool:
        return (today - d).days > min_days

    terms = {is_long(lot.purchase_date or today) for lot in lots}
    term: Literal["short", "long", "mixed", "unknown"] = (
        "mixed" if len(terms) > 1 else ("long" if terms == {True} else "short")
    )
    short_lots = [lot for lot in lots if not is_long(lot.purchase_date or today)]
    lt_from = (
        (short_lots[0].purchase_date or today) + timedelta(days=min_days + 1)
        if short_lots
        else None
    )
    lines.append(
        f"Held since {first:%d %b %Y} ({days} days)"
        + (f"; the newer lots turn long-term from {lt_from:%d %b %Y}" if term == "mixed" else "")
        + (f"; turns long-term on {lt_from:%d %b %Y}" if term == "short" and lt_from else "")
        + "."
    )
    if sell_qty > 0 and price is not None:
        remaining = sell_qty
        st_gain = lt_gain = 0.0
        for lot in lots:  # FIFO: the oldest shares are sold first
            q = min(remaining, lot.quantity)
            if q <= 0:
                break
            g = q * (price - lot.avg_price)
            if is_long(lot.purchase_date or today):
                lt_gain += g
            else:
                st_gain += g
            remaining -= q
        for kind, gain, rate in (
            ("short-term (STCG)", st_gain, cfg.equity_stcg_rate),
            ("long-term (LTCG)", lt_gain, cfg.equity_ltcg_rate),
        ):
            if gain > 0:
                extra = (
                    f" after the yearly {format_inr(cfg.equity_ltcg_exemption_inr, 0)} exemption"
                    " (shared across all your sales)"
                    if kind.startswith("long")
                    else ""
                )
                lines.append(
                    f"On selling {sell_qty:g} share(s): a {kind} gain of "
                    f"{format_inr(gain, 0)}, taxed at {rate * 100:g}%{extra}: about "
                    f"{format_inr(gain * rate, 0)} before cess."
                )
            elif gain < 0:
                lines.append(
                    f"On selling {sell_qty:g} share(s): a {kind} loss of "
                    f"{format_inr(-gain, 0)}, which can be set off against gains."
                )
    return TaxNote(days, term, lt_from, lines, cfg.verify_note)
