from datetime import date

import pytest

from app.analysis import fundamental as fa
from app.analysis import technical as ta
from app.analysis.scoring import (
    Reading,
    composite,
    confidence_of,
    reading_weight,
    score_fundamental,
    score_technical,
    sub_score,
    timeframe_weights,
    top_reasons,
)
from app.core.profiles import get_profiles
from app.data.freshness import Freshness

FRESH = Freshness("fresh", "ok")


def tobs(key: str, cat: str, d: str, minor: bool = False) -> ta.Observation:
    return ta.Observation(key, cat, d, f"{key} text", None, minor)  # type: ignore[arg-type]


def fobs(key: str, cat: str, d: str) -> fa.Observation:
    return fa.Observation(key, cat, d, f"{key} text")  # type: ignore[arg-type]


def tech_report(
    frames: dict[str, list[ta.Observation]],
    context: list[ta.Observation] | None = None,
    freshness: Freshness = FRESH,
) -> ta.TechnicalReport:
    tfs = [
        ta.TimeframeReport(
            interval=iv,  # type: ignore[arg-type]
            bars=300,
            as_of="2026-10-09",
            last_close=100.0,
            last_complete=True,
            freshness=freshness,
            analysis=ta.FrameAnalysis({}, obs, [], []),
        )
        for iv, obs in frames.items()
    ]
    return ta.TechnicalReport(
        "X.NS", "X", "swing", tfs, ta.FrameAnalysis({}, context or [], [], []), [], []
    )


def fund_report(
    obs: list[fa.Observation],
    *,
    financial: bool = False,
    applicable: bool = True,
    freshness: Freshness = FRESH,
) -> fa.FundamentalReport:
    return fa.FundamentalReport(
        ticker="X.NS",
        label="X",
        sector="Industrials",
        sector_key="nse:Industrials",
        is_financial=financial,
        source="yahoo",
        latest_year=date(2026, 3, 31),
        freshness=freshness,
        metrics={},
        fscore=None,
        observations=obs,
        unavailable=[],
        applicable=applicable,
    )


def r(direction: str, w: float = 1.0, cat: str = "trend") -> Reading:
    return Reading("technical", "k", cat, direction, "t", False, w)  # type: ignore[arg-type]


def test_sub_score_formula() -> None:
    assert sub_score([r("bullish"), r("bullish")]) == 100
    assert sub_score([r("bearish")]) == 0
    assert sub_score([r("bullish"), r("bearish")]) == 50
    assert sub_score([r("neutral", 0.5)]) == 50
    # 50 + 50 × (2 − 1) / (2 + 1 + 0.5)
    assert sub_score([r("bullish", 2), r("bearish"), r("neutral", 0.5)]) == pytest.approx(
        50 + 50 * 1 / 3.5
    )
    assert sub_score([]) is None
    assert sub_score([r("bullish", 0)]) is None  # info-only readings don't count


def test_reading_weight_rules() -> None:
    cfg = get_profiles().scoring
    assert reading_weight(tobs("atr", "volatility", "neutral"), cfg) == 0  # info only
    assert reading_weight(tobs("golden_cross", "trend", "bullish"), cfg) == 2.0
    assert reading_weight(tobs("rsi_positive", "momentum", "bullish"), cfg) == 1.0
    assert reading_weight(tobs("candle_hammer", "pattern", "bullish", True), cfg) == 0.5
    assert reading_weight(tobs("adx_no_trend", "trend", "neutral"), cfg) == 0.5


def test_timeframe_weights() -> None:
    assert timeframe_weights(["1d"], 0.6) == [1.0]
    assert timeframe_weights(["1d", "1wk"], 0.6) == pytest.approx([0.6, 0.4])
    assert timeframe_weights(["15m", "1h", "1d"], 0.6) == pytest.approx([0.6, 0.2, 0.2])


def test_technical_score_weights_categories_and_coverage() -> None:
    cfg = get_profiles().scoring
    rep = tech_report(
        {
            "1d": [
                tobs("price_vs_sma200", "trend", "bullish"),
                tobs("rsi_weak", "momentum", "bearish"),
                tobs("atr", "volatility", "neutral"),
            ]
        }
    )
    s = score_technical(rep, cfg).side
    w = cfg.technical_weights
    # trend 100 (w .30), momentum 0 (w .20): re-weighted over the categories with data
    assert s.score == pytest.approx(round(100 * w["trend"] / (w["trend"] + w["momentum"]), 1))
    assert s.coverage == pytest.approx(
        (w["trend"] + w["momentum"]) / sum(v for v in w.values() if v > 0), abs=1e-3
    )
    subs = {x.category: x for x in s.subscores}
    assert subs["volume"].score is None and subs["trend"].bullish == 1
    assert "volatility" not in subs  # weight 0: not scored


def test_context_readings_merge_across_timeframes() -> None:
    cfg = get_profiles().scoring
    ctx = [tobs("rs_3m", "relative_strength", "bullish")]
    rep = tech_report(
        {
            "1d": [tobs("price_vs_sma200", "trend", "bullish")],
            "1wk": [tobs("price_vs_sma200", "trend", "bearish")],
        },
        ctx,
    )
    sc = score_technical(rep, cfg)
    rs = [x for x in sc.readings if x.key == "rs_3m"]
    assert len(rs) == 1 and rs[0].timeframes == ["1d", "1wk"]
    tf = {t.interval: t for t in sc.side.timeframes}
    assert tf["1d"].weight == pytest.approx(0.6) and tf["1d"].score > tf["1wk"].score  # type: ignore[operator]


def test_financials_exempt_categories_keep_coverage() -> None:
    cfg = get_profiles().scoring
    obs = [
        fobs("pe_cheap", "valuation", "bullish"),
        fobs("roe_good", "profitability", "bullish"),
        fobs("revenue_cagr_3y_strong", "growth", "bullish"),
    ]
    bank = score_fundamental(fund_report(obs, financial=True), cfg).side
    other = score_fundamental(fund_report(obs), cfg).side
    assert bank.score == other.score == 100
    assert bank.coverage > other.coverage  # health and quality aren't expected for a bank


def test_composite_points_add_up_to_the_score() -> None:
    p = get_profiles()
    tech = tech_report(
        {
            "1d": [
                tobs("golden_cross", "trend", "bullish"),
                tobs("rsi_overbought", "momentum", "bearish"),
                tobs("volume_surge_up", "volume", "bullish"),
                tobs("near_52w_high", "structure", "bullish"),
                tobs("adx_developing", "trend", "neutral"),
            ],
            "1wk": [tobs("macd_bearish", "momentum", "bearish")],
        },
        [tobs("rs_6m", "relative_strength", "bearish")],
    )
    fund = fund_report(
        [
            fobs("pe_rich", "valuation", "bearish"),
            fobs("roe_good", "profitability", "bullish"),
            fobs("debt_above_limit", "health", "bearish"),
            fobs("fscore_strong", "quality", "bullish"),
        ]
    )
    c = composite(tech, fund, 0.5, p.scoring, p.confidence)
    assert c.score is not None
    assert c.score == pytest.approx(
        0.5 * c.technical.score + 0.5 * c.fundamental.score,  # type: ignore[operator]
        abs=0.1,
    )
    # Every point is accounted for: composite − 50 = Σ reading points.
    assert sum(x.points for x in c.readings) == pytest.approx(c.score - 50, abs=0.1)
    bull, bear = top_reasons(c.readings)
    assert bull[0].points >= bull[-1].points > 0 and bear[0].points <= bear[-1].points < 0
    assert {x.key for x in bear} & {"debt_above_limit", "pe_rich"}


def test_composite_style_weights_and_missing_sides() -> None:
    p = get_profiles()
    tech = tech_report({"1d": [tobs("price_vs_sma200", "trend", "bullish")]})
    fund = fund_report([fobs("pe_rich", "valuation", "bearish")])
    assert composite(tech, fund, 0.9, p.scoring, p.confidence).score == pytest.approx(90)
    assert composite(tech, fund, 0.2, p.scoring, p.confidence).score == pytest.approx(20)

    no_fund = composite(tech, fund_report([]), 0.5, p.scoring, p.confidence)
    assert no_fund.score == 100 and no_fund.fundamental_weight == 0
    assert any("technicals alone" in n for n in no_fund.notes)
    assert no_fund.coverage < 0.5 * 1 + 0.01  # the missing half lowers coverage

    etf = composite(tech, fund_report([], applicable=False), 0.5, p.scoring, p.confidence)
    assert etf.score == 100 and etf.coverage == etf.technical.coverage
    assert any("don't apply" in n for n in etf.notes)

    nothing = composite(tech_report({"1d": []}), fund_report([]), 0.5, p.scoring, p.confidence)
    assert nothing.score is None and nothing.confidence is None


def test_confidence_levels_and_stale_cap() -> None:
    cfg = get_profiles().confidence
    assert confidence_of(0.9, False, cfg)[0] == "high"
    assert confidence_of(0.6, False, cfg)[0] == "medium"
    assert confidence_of(0.2, False, cfg)[0] == "low"
    level, reason = confidence_of(0.95, True, cfg)
    assert level == "medium" and "stale" in reason
    assert confidence_of(0.2, True, cfg)[0] == "low"


def test_stale_prices_cap_composite_confidence() -> None:
    p = get_profiles()
    obs = [
        tobs("price_vs_sma200", "trend", "bullish"),
        tobs("rsi_positive", "momentum", "bullish"),
        tobs("volume_surge_up", "volume", "bullish"),
        tobs("near_52w_high", "structure", "bullish"),
    ]
    ctx = [tobs("rs_3m", "relative_strength", "bullish")]
    fresh = composite(tech_report({"1d": obs}, ctx), fund_report([]), 1.0, p.scoring, p.confidence)
    stale = composite(
        tech_report({"1d": obs}, ctx, Freshness("stale", "3 sessions old")),
        fund_report([]),
        1.0,
        p.scoring,
        p.confidence,
    )
    assert fresh.confidence == "high" and stale.confidence == "medium"
    assert any("3 sessions old" in n for n in stale.technical.notes)
