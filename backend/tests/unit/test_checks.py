"""Score Shape checks: config validation, the rules, the axis maths, fair value and P/E history."""

from datetime import date
from pathlib import Path

import pandas as pd
import pytest
import yaml

from app.analysis.check_rules import STOCK_RULES, Limits, StockContext
from app.analysis.checks import (
    CheckDef,
    HoldingFacts,
    SectionDef,
    SectionResult,
    ShapeResult,
    _result,
    _run,
    _section,
    fmt,
    get_checks,
    load_checks,
    portfolio_notes,
    portfolio_shape,
)
from app.analysis.fundamental import FundamentalReport, Metric
from app.analysis.statements import Statements
from app.analysis.valuation import close_on, fair_value, pe_history, pe_history_median
from app.core.profiles import ConfigError, get_profiles
from app.core.settings import get_settings
from app.data.freshness import Freshness
from app.screener.fields import FIELD_BY_KEY

YEARS = [date(2023, 3, 31), date(2024, 3, 31), date(2025, 3, 31), date(2026, 3, 31)]


def metric(key: str, value: float, median: float | None = None, basis: str = "test") -> Metric:
    return Metric(key, key, value, "x", basis, sector_median=median, peers=10 if median else 0)


def annual(**cols: list[float]) -> pd.DataFrame:
    return pd.DataFrame(cols, index=YEARS[-len(next(iter(cols.values()))) :], dtype="float64")


def report(
    metrics: dict[str, Metric] | None = None,
    frame: pd.DataFrame | None = None,
    *,
    financial: bool = False,
    unavailable: list[str] | None = None,
    currency: str = "INR",
) -> FundamentalReport:
    st = Statements("yahoo", frame, pd.DataFrame()) if frame is not None else None
    return FundamentalReport(
        ticker="TEST.NS",
        label="Test Ltd",
        sector="Industrials",
        sector_key="industrials",
        is_financial=financial,
        source="yahoo",
        latest_year=None,
        freshness=Freshness("fresh", ""),
        metrics=metrics or {},
        fscore=None,
        observations=[],
        unavailable=unavailable or [],
        statements=st,
        currency=currency,
    )


def ctx(
    rep: FundamentalReport, daily: dict | None = None, market: dict | None = None
) -> StockContext:  # type: ignore[type-arg]
    a = rep.statements.annual if rep.statements is not None else pd.DataFrame()
    return StockContext(rep, a, daily or {}, market or {}, "Medium", None, "needs peers", [])


def run(
    rule: str,
    c: StockContext,
    threshold: float | None = None,
    upper: float | None = None,
    ratio: float | None = None,
):  # type: ignore[no-untyped-def]
    return _run(STOCK_RULES[rule], c, Limits(threshold, upper, ratio))


# ---------------------------------------------------------------------------- config


def test_config_loads_and_covers_every_rule() -> None:
    cfg = get_checks()
    assert list(cfg.stock) == ["valuation", "growth", "past", "health", "momentum", "dividends"]
    assert list(cfg.fund) == ["returns", "consistency", "risk", "risk_adjusted", "cost"]
    for s in cfg.stock.values():
        for company in ("non_financial", "financial"):
            assert sum(c.applies in ("all", company) for c in s.checks) <= cfg.axis.max
    # Non-financial companies get exactly 6 checks in every section.
    for s in cfg.stock.values():
        assert sum(c.applies in ("all", "non_financial") for c in s.checks) == 6


def test_screener_axis_fields_match_the_sections() -> None:
    for key in get_checks().stock:
        assert f"axis_{key}" in FIELD_BY_KEY
    assert "axis_total" in FIELD_BY_KEY


def _write(tmp_path: Path, mutate) -> Path:  # type: ignore[no-untyped-def]
    raw = yaml.safe_load(get_settings().checks_path.read_text(encoding="utf-8"))
    mutate(raw)
    p = tmp_path / "checks.yaml"
    p.write_text(yaml.safe_dump(raw, allow_unicode=True), encoding="utf-8")
    return p


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda r: r["stock"]["valuation"]["checks"][0].update(id="nope"), "no rule for check ids"),
        (
            lambda r: r["stock"]["past"]["checks"][0].update(threshold={"ref": "fundamental.nope"}),
            "doesn't resolve",
        ),
        (
            lambda r: r["stock"]["valuation"]["checks"].append(
                {**r["stock"]["valuation"]["checks"][0], "id": "peg"}
            ),
            "duplicate check ids",
        ),
        (lambda r: r["axis"].update(score_steps=[0.5, 0.2, 0.6, 0.8]), "ascending"),
        (lambda r: r["stock"]["growth"]["checks"][0].pop("fail"), "fail"),
    ],
)
def test_bad_config_fails_with_a_readable_error(tmp_path: Path, mutate, message: str) -> None:  # type: ignore[no-untyped-def]
    with pytest.raises(ConfigError, match=message):
        load_checks(_write(tmp_path, mutate), get_profiles())


def test_too_many_checks_in_a_section(tmp_path: Path) -> None:
    def mutate(r):  # type: ignore[no-untyped-def]
        r["stock"]["momentum"]["checks"].append(
            {**r["stock"]["valuation"]["checks"][1], "applies": "all"}
        )
        r["stock"]["valuation"]["checks"].pop(1)

    with pytest.raises(ConfigError, match="at most axis.max"):
        load_checks(_write(tmp_path, mutate), get_profiles())


def test_refs_follow_profiles_and_risk_level() -> None:
    cfg = get_checks()
    from app.analysis.checks import resolve

    p = get_profiles()
    de = next(c for c in cfg.stock["health"].checks if c.id == "debt_equity")
    assert resolve(de.threshold, p, p.risk_levels["low"]) == 0.5
    assert resolve(de.threshold, p, p.risk_levels["high"]) == 2.0
    rsi = next(c for c in cfg.stock["momentum"].checks if c.id == "rsi_healthy")
    assert resolve(rsi.threshold, p, p.risk_levels["medium"]) == 45  # rsi_neutral_band.0
    assert resolve(rsi.upper, p, p.risk_levels["medium"]) == 70


# ---------------------------------------------------------------------------- axis maths


def _results(statuses: list[str]) -> list:  # type: ignore[type-arg]
    c = CheckDef.model_validate({"id": "x", "label": "X", "unit": "x", "pass": "ok", "fail": "no"})
    from app.analysis.check_rules import Outcome

    return [_result("s", c, Outcome(s), Limits(None, None, None)) for s in statuses]  # type: ignore[arg-type]


SD = SectionDef(
    label="S",
    question="?",
    checks=[
        CheckDef.model_validate({"id": "x", "label": "X", "unit": "x", "pass": "ok", "fail": "no"})
    ],
)


@pytest.mark.parametrize(
    ("statuses", "score"),
    [
        (["pass"] * 4 + ["fail"] * 2, 4),  # all 6 have data: the raw count
        (["pass"] * 3 + ["fail"] + ["no_data"] * 2, 5),  # 3 of 4 → 4.5 → rounds up
        (["pass"] + ["fail"] * 3 + ["no_data"] * 2, 2),  # 1 of 4 → 1.5 → 2
        (["pass", "pass", "fail", "no_data", "no_data", "no_data"], 4),
        (["pass", "pass", "no_data", "no_data", "no_data", "no_data"], None),  # 2 < 3 with data
    ],
)
def test_axis_score_counts_only_checks_with_data(statuses: list[str], score: int | None) -> None:
    sec = _section("s", SD, _results(statuses), get_checks(), "stock")
    assert sec.score == score
    assert sec.with_data == sum(s != "no_data" for s in statuses)
    assert (sec.note == "Not enough data") == (score is None)


def test_formatting() -> None:
    assert fmt(19.61, "x") == "19.6×" and fmt(0.44, "x") == "0.44×"
    assert fmt(-22.4, "pct") == "−22.4%"
    assert fmt(4.5, "pp") == "+4.5 pp" and fmt(4.5, "pp", signed=False) == "4.5 pp"
    assert fmt(-0.14, "pp") == "−0.1 pp"
    assert (
        fmt(69197, "inr_cr") == "₹69,197 Cr" and fmt(101, "inr_cr", currency="USD") == "USD 101 Cr"
    )
    assert fmt(None, "pct") == "—"


# ---------------------------------------------------------------------------- rules


def test_vs_sector_median_and_missing_peers() -> None:
    c = ctx(report({"pe": metric("pe", 19.6, 13.3)}))
    o = run("pe_vs_sector", c)
    assert o.status == "fail" and o.value == 19.6 and o.threshold == 13.3
    assert run("pe_vs_sector", ctx(report({"pe": metric("pe", 10, 13.3)}))).status == "pass"
    o = run("pe_vs_sector", ctx(report({"pe": metric("pe", 10)})))
    assert o.status == "no_data" and "peers" in (o.reason or "")


def test_missing_metric_uses_the_engines_reason() -> None:
    rep = report(unavailable=["P/E (loss-making: not meaningful)"])
    assert run("pe_vs_sector", ctx(rep)).reason == "loss-making: not meaningful"
    usd = report(unavailable=["Valuation ratios (statements are in USD, price in INR)"])
    assert run("peg", ctx(usd)).reason == "statements are in USD, price in INR"


def test_threshold_cleared_in_settings_is_no_data_not_a_crash() -> None:
    o = run("roe_good", ctx(report({"roe": metric("roe", 20)})), threshold=None)
    assert o.status == "no_data" and "no threshold" in (o.reason or "")


def test_debt_trend_compares_debt_to_equity() -> None:
    # Debt up in rupees but down relative to a faster-growing equity: passes.
    c = ctx(report(frame=annual(total_debt=[300, 350], equity=[600, 1000])))
    o = run("debt_trend", c)
    assert o.status == "pass" and "fell from 0.50× to 0.35× equity" in o.vars["trend_text"]
    o = run("debt_trend", ctx(report(frame=annual(total_debt=[0, 0], equity=[600, 1000]))))
    assert o.status == "pass" and "Debt-free" in (o.text or "")
    o = run("debt_trend", ctx(report(frame=annual(total_debt=[100, 200]))))
    assert o.status == "fail" and "rose" in o.vars["trend_text"]


def test_interest_coverage_with_no_interest_passes() -> None:
    c = ctx(report(frame=annual(interest_expense=[5, 0])))
    o = run("interest_coverage", c, threshold=3)
    assert o.status == "pass" and o.text == "No interest to pay."


def test_non_payers_fail_every_dividend_check_in_plain_words() -> None:
    c = ctx(
        report(
            {"dividend_yield": metric("dividend_yield", 0)},
            annual(dividends_paid=[0, 0], net_income=[10, 12]),
        )
    )
    assert run("pays_dividend", c).status == "fail"
    for rule in ("yield_high", "dividend_consistent", "dividend_growing", "payout_sustainable"):
        o = run(rule, c, threshold=3)
        assert o.status == "fail" and o.text == "Pays no dividend.", rule


def test_dividend_rules() -> None:
    frame = annual(
        dividends_paid=[30, 35, 40, 45],
        net_income=[100, 115, 130, 150],
        free_cash_flow=[80, 90, 90, 110],
    )
    c = ctx(report({"dividend_yield": metric("dividend_yield", 1.5)}, frame))
    assert run("dividend_consistent", c).status == "pass"
    o = run("dividend_growing", c)
    assert o.status == "pass" and o.vars["first"] == "₹30 Cr" and o.vars["years"] == "3"
    o = run("payout_sustainable", c, threshold=75)
    assert o.status == "pass" and o.value == pytest.approx(30.0)
    assert run("fcf_covers_dividend", c).status == "pass"
    loss = ctx(
        report(
            {"dividend_yield": metric("dividend_yield", 1)},
            annual(dividends_paid=[5], net_income=[-2]),
        )
    )
    assert run("payout_sustainable", loss, threshold=75).status == "fail"


def test_momentum_rules() -> None:
    c = ctx(
        report(),
        daily={
            "close": 110,
            "sma50": 100,
            "sma200": 120,
            "rsi14": 75,
            "macd_hist": 0.3,
            "obv_slope": 0.01,
        },
        market={"rs_6m": -2.0},
    )
    assert run("above_sma50", c).status == "pass"
    assert run("above_sma200", c).status == "fail"
    o = run("rsi_healthy", c, threshold=45, upper=70)
    assert o.status == "fail" and o.vars["zone"] == "overheated"
    assert run("macd_positive", c).status == "pass"
    assert run("beats_nifty_6m", c).status == "fail"
    assert run("obv_rising", c, threshold=0.02).status == "fail"
    assert run("above_sma200", ctx(report())).status == "no_data"


def test_lender_checks() -> None:
    frame = annual(equity=[100, 130], total_assets=[1000, 1100], net_income=[11, 14])
    c = ctx(report(frame=frame, financial=True))
    assert run("capital_cushion", c, threshold=8).status == "pass"
    assert run("roa", c, threshold=1).status == "pass"
    assert run("book_growth", c).status == "pass"


def test_margin_trend_and_profit_history() -> None:
    m = {"op_margin_change": Metric("op_margin_change", "x", -2.5, "pp", "FY2023→FY2026")}
    o = run("margin_trend", ctx(report(m)), threshold=1.0)
    assert o.status == "fail" and o.vars == {"margin": "Operating margin", "years": "3"}
    assert (
        run("profitable_every_year", ctx(report(frame=annual(net_income=[5, -1, 3])))).status
        == "fail"
    )


# ---------------------------------------------------------------------------- valuation


def test_fair_value_averages_the_methods() -> None:
    m = {
        "market_cap": metric("market_cap", 1000),
        "pe": metric("pe", 20, 10),  # twice the sector P/E → half the price
        "ev_ebitda": metric("ev_ebitda", 10, 10),  # at the median: EV-based value = today
    }
    fv, why = fair_value(m, annual(total_debt=[0], cash=[0]), 100.0, financial=False)
    assert fv is not None and why == ""
    assert [x.name for x in fv.methods] == ["Earnings", "Cash profit"]
    assert fv.methods[0].value == pytest.approx(50.0)
    assert fv.methods[1].value == pytest.approx(100.0)
    assert fv.value == pytest.approx(75.0) and fv.gap_pct == pytest.approx(33.3, abs=0.1)
    assert "Estimate" in fv.caveat


def test_fair_value_for_lenders_uses_book_value() -> None:
    m = {
        "market_cap": metric("market_cap", 1000),
        "pe": metric("pe", 10, 20),
        "pb": metric("pb", 1, 2),
    }
    fv, _ = fair_value(m, None, 100.0, financial=True)
    assert fv is not None and [x.name for x in fv.methods] == ["Earnings", "Book value"]
    assert fv.value == pytest.approx(200.0) and fv.gap_pct < 0


def test_nil_fair_value_reads_far_above_not_inf() -> None:
    from app.analysis.valuation import describe

    m = {"market_cap": metric("market_cap", 1000), "ev_ebitda": metric("ev_ebitda", 250, 10)}
    # Debt of 900 dwarfs EBITDA of 4 at 10x: nothing left for shareholders.
    fv, _ = fair_value(m, annual(total_debt=[900], cash=[0]), 40.0, financial=False)
    assert fv is not None and fv.value == 0 and fv.gap_pct == float("inf")
    text = describe(fv)
    assert "inf" not in text and "far above" in text and "worth less than its debt" in text


def test_fair_value_needs_peers() -> None:
    fv, why = fair_value(
        {"market_cap": metric("market_cap", 1000), "pe": metric("pe", 20)}, None, 100.0, False
    )
    assert fv is None and "sector median" in why


def test_pe_history_at_year_ends() -> None:
    closes = pd.Series(
        [100.0, 110.0, 90.0, 120.0],
        index=[date(2023, 3, 31), date(2024, 3, 28), date(2025, 3, 31), date(2026, 3, 31)],
    )
    frame = annual(net_income=[10.0, 11.0, -3.0, 12.0], shares=[1e7, 1e7, 1e7, 1e7])
    pts = pe_history(frame, closes, {"market_cap": metric("market_cap", 12)}, 120.0)
    # 2024: the year-end fell on a holiday, so the last close before it is used.
    assert [p.fy for p in pts] == ["FY2023", "FY2024", "FY2026"]  # FY2025 was a loss
    assert [p.pe for p in pts] == [10.0, 10.0, 10.0]
    assert pe_history_median(pts) == 10.0
    assert pe_history_median(pts[:2]) is None
    assert close_on(closes, date(2022, 3, 31)) is None


# ---------------------------------------------------------------------------- portfolio


def _shape(axes: dict[str, int | None]) -> ShapeResult:
    secs = [SectionResult(k, k.title(), "?", None, [], 0, 6, v, None) for k, v in axes.items()]
    return ShapeResult("stock", secs, 0, 0, 6, None, 0, 0, "high", "", [], [], "")


def test_portfolio_shape_is_value_weighted() -> None:
    keys = list(get_checks().stock)
    a = _shape(dict.fromkeys(keys, 6))
    b = _shape({**dict.fromkeys(keys, 0), "dividends": None})
    shape = portfolio_shape([(300.0, a), (100.0, b)])
    by = {x.key: x for x in shape.axes}
    assert by["health"].score == 4.5 and by["health"].coverage == 1.0
    assert by["dividends"].score == 6.0 and by["dividends"].coverage == 0.75
    assert shape.total == pytest.approx(4.5 * 5 + 6) and shape.max_total == 36


def test_portfolio_notes() -> None:
    keys = list(get_checks().stock)
    strong = HoldingFacts("A", 800, _shape(dict.fromkeys(keys, 6)), "buy", "Buy", 0.2, 0.12)
    weak = HoldingFacts("B", 200, _shape(dict.fromkeys(keys, 1)), "sell", "Sell", 0.05, 0.12)
    rewards, risks = portfolio_notes([strong, weak], [("Banks", 0.38, 0.30), ("IT", 0.1, 0.3)])
    assert "Over-exposed to Banks: 38% vs your 30% limit." in risks
    assert any("A is 20.0% of the portfolio" in r for r in risks)
    assert any(r == "1 holding with a Sell or Reduce signal: B." for r in risks)
    assert any(
        "20% of your stock value is in companies with weak Financial Health" in r for r in risks
    )
    assert any(
        "80% of your stock value is in companies with strong Financial Health" in r for r in rewards
    )


def test_portfolio_notes_name_three_sells_then_count_the_rest() -> None:
    keys = list(get_checks().stock)
    sells = [
        HoldingFacts(n, 100, _shape(dict.fromkeys(keys, 3)), "sell", "Sell", 0.01, 0.12)
        for n in "ABCDE"
    ]
    _, risks = portfolio_notes(sells, [])
    assert "5 holdings with a Sell or Reduce signal: A, B, C and 2 more." in risks
