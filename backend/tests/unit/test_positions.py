from datetime import date

import pytest

from app.analysis.positions import (
    Lot,
    Portfolio,
    Position,
    add_amount,
    suggest,
    tax_note,
    trim_amount,
)
from app.core.profiles import get_profiles

TODAY = date(2026, 10, 10)


def pos(
    qty: float = 100, price: float = 100.0, avg: float = 80.0, lots: list[Lot] | None = None
) -> Position:
    return Position(
        ticker="X.NS",
        label="X",
        quantity=qty,
        avg_price=avg,
        invested=qty * avg,
        price=price,
        price_source="test",
        value=qty * price,
        sector="Banks",
        lots=lots or [Lot(qty, avg, None)],
    )


def portfolio(p: Position | None, total: float) -> Portfolio:
    positions = {p.ticker: p} if p else {}
    return Portfolio(
        positions, total, total, 0.0, {"Banks": p.value or 0.0} if p else {}, "portfolio"
    )


def test_add_and_trim_amounts_hit_the_target() -> None:
    x = add_amount(5_000, 100_000, 0.09)
    assert (5_000 + x) / (100_000 + x) == pytest.approx(0.09)
    y = trim_amount(20_000, 100_000, 0.12)
    assert (20_000 - y) / (100_000 - y) == pytest.approx(0.12)
    assert add_amount(20_000, 100_000, 0.1) == 0 and trim_amount(5_000, 100_000, 0.1) == 0


def test_suggest_add_for_buy_and_strong_buy() -> None:
    p = get_profiles()
    risk, cfg = p.risk_levels["medium"], p.rebalance
    held = pos(qty=50)  # ₹5,000 of ₹1,00,000 = 5%
    pf = portfolio(held, 100_000)
    buy = suggest("buy", held, 100.0, pf, risk, cfg)
    target = risk.max_weight_per_stock * cfg.buy_target  # 9%
    assert buy.action == "add" and buy.quantity == int(add_amount(5_000, 100_000, target) // 100)
    assert buy.target_weight == pytest.approx(
        (5_000 + buy.quantity * 100) / (100_000 + buy.quantity * 100), abs=1e-4
    )
    strong = suggest("strong_buy", held, 100.0, pf, risk, cfg)
    assert strong.quantity > buy.quantity and "new money" in strong.text
    # Already at target
    big = pos(qty=100)
    assert suggest("buy", big, 100.0, portfolio(big, 100_000), risk, cfg).action == "none"


def test_suggest_add_is_capped_by_sector_limit() -> None:
    p = get_profiles()
    risk, cfg = p.risk_levels["medium"], p.rebalance
    held = pos(qty=50)
    pf = portfolio(held, 100_000)
    capped = suggest("strong_buy", held, 100.0, pf, risk, cfg, sector="Banks", sector_weight=0.29)
    room = add_amount(29_000, 100_000, risk.max_weight_per_sector)
    assert capped.quantity == int(room // 100) and "capped by your 30.0% limit" in capped.text
    full = suggest("buy", held, 100.0, pf, risk, cfg, sector="Banks", sector_weight=0.31)
    assert full.action == "none" and "No room" in full.text


def test_suggest_trim_and_exit() -> None:
    p = get_profiles()
    risk, cfg = p.risk_levels["medium"], p.rebalance
    held = pos(qty=200)  # ₹20,000 of ₹1,00,000 = 20% > 12%
    pf = portfolio(held, 100_000)
    trim = suggest("reduce", held, 100.0, pf, risk, cfg)
    assert trim.action == "trim"
    assert trim.quantity == -(-trim_amount(20_000, 100_000, 0.12) // 100)  # ceil
    assert trim.target_weight is not None and trim.target_weight <= 0.12
    small = pos(qty=50)
    weak = suggest("reduce", small, 100.0, portfolio(small, 100_000), risk, cfg, score_reduce=True)
    assert weak.quantity == 25 and "50%" in weak.text  # keep half on a weak score
    sell = suggest("sell", held, 100.0, pf, risk, cfg)
    assert (sell.action, sell.quantity, sell.target_weight) == ("exit", 200, 0.0)
    assert suggest("hold", held, 100.0, pf, risk, cfg).action == "none"


def test_suggest_edge_cases() -> None:
    p = get_profiles()
    risk, cfg = p.risk_levels["medium"], p.rebalance
    held = pos(qty=1)
    assert "No price" in suggest("buy", held, None, portfolio(held, 100), risk, cfg).text
    assert "Import" in suggest("buy", None, 100.0, None, risk, cfg).text
    assert suggest("sell", None, 100.0, portfolio(None, 1_00_000), risk, cfg).action == "none"
    # Below the minimum trade value
    tiny = pos(qty=1, price=10)
    r = suggest("reduce", tiny, 10.0, portfolio(tiny, 100), risk, cfg, score_reduce=True)
    assert r.action == "none" and "too small" in r.text
    # Not held, buy: sized from zero
    new = suggest("buy", None, 100.0, portfolio(None, 1_00_000), risk, cfg)
    assert new.action == "add" and new.quantity > 0


def test_tax_note_unknown_date() -> None:
    cfg = get_profiles().tax
    t = tax_note(pos(), 10, 100.0, cfg, TODAY)
    assert t is not None and t.term == "unknown" and "Purchase date unknown" in t.text[0]
    assert "Verify" in t.verify_note
    assert tax_note(None, 0, 100.0, cfg, TODAY) is None


def test_tax_note_short_and_long_term_fifo() -> None:
    cfg = get_profiles().tax
    lots = [Lot(10, 50.0, date(2024, 1, 15)), Lot(10, 90.0, date(2026, 6, 1))]
    p = pos(qty=20, avg=70.0, lots=lots)
    t = tax_note(p, 15, 100.0, cfg, TODAY)
    assert (
        t is not None and t.term == "mixed" and t.holding_days == (TODAY - date(2024, 1, 15)).days
    )
    assert t.long_term_from == date(2027, 6, 2)  # held more than 365 days
    text = " ".join(t.text)
    # FIFO: 10 long-term shares (gain 10 × 50) + 5 short-term (gain 5 × 10)
    assert "long-term (LTCG) gain of ₹500" in text and "short-term (STCG) gain of ₹50" in text
    assert f"{cfg.equity_ltcg_rate * 100:g}%" in text and "exemption" in text

    short = tax_note(pos(qty=10, lots=[Lot(10, 120.0, date(2026, 3, 1))]), 10, 100.0, cfg, TODAY)
    assert short is not None and short.term == "short" and "turns long-term on" in short.text[0]
    assert "loss of ₹200" in " ".join(short.text) and "set off" in " ".join(short.text)

    longt = tax_note(pos(qty=10, lots=[Lot(10, 50.0, date(2020, 1, 1))]), 0, 100.0, cfg, TODAY)
    assert longt is not None and longt.term == "long" and len(longt.text) == 1


def test_tax_note_partly_undated() -> None:
    cfg = get_profiles().tax
    p = pos(qty=20, lots=[Lot(10, 50.0, date(2020, 1, 1)), Lot(10, 50.0, None)])
    t = tax_note(p, 0, 100.0, cfg, TODAY)
    assert t is not None and "10 share(s) have no purchase date" in t.text[0]
