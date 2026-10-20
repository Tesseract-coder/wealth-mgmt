import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from app.analysis.patterns import LIBRARY, detect
from app.core import db
from app.core.profiles import get_profiles
from app.data import store


def walk(start: float, *legs: tuple[int, float]) -> list[float]:
    """Closes moving in straight lines: each leg is (bars to get there, price)."""
    out = [start]
    for bars, price in legs:
        a = out[-1]
        out += [a + (price - a) * (i + 1) / bars for i in range(bars)]
    return out


def frame(closes: list[float], volume: list[float] | None = None) -> pd.DataFrame:
    c = pd.Series(closes, dtype="float64")
    idx = pd.bdate_range("2025-01-01", periods=len(c))
    return pd.DataFrame(
        {
            "open": c.shift(1).fillna(c).to_numpy(),
            "high": (c * 1.004).to_numpy(),
            "low": (c * 0.996).to_numpy(),
            "close": c.to_numpy(),
            "volume": volume if volume is not None else [1000.0] * len(c),
        },
        index=idx,
    )


def mirror(closes: list[float]) -> list[float]:
    return [200 - v for v in closes]


def found(closes: list[float], volume: list[float] | None = None) -> dict:  # type: ignore[type-arg]
    cfg = get_profiles().technical.patterns
    return {m.key: m for m in detect(frame(closes, volume), cfg)}


HS = walk(80, (20, 100), (8, 92), (10, 108), (10, 93), (8, 100.5), (8, 86))
DOUBLE_TOP = walk(80, (25, 100), (12, 90), (12, 100.5), (8, 87))
ASC_TRIANGLE = walk(85, (10, 100), (8, 90), (8, 100), (8, 93), (8, 100), (8, 96), (7, 98.5))
SYM_TRIANGLE = walk(85, (10, 110), (8, 90), (8, 106), (8, 94), (8, 102.5), (8, 97), (7, 99.5))
RISING_WEDGE = walk(80, (10, 100), (8, 92), (8, 106), (8, 101), (8, 110), (8, 108), (7, 109))


def test_library_covers_every_family() -> None:
    families = {p.family for p in LIBRARY.values()}
    assert families == {
        "head_and_shoulders",
        "double_top",
        "double_bottom",
        "rounding_bottom",
        "cup_and_handle",
        "wedges",
        "flags_pennants",
        "ascending_triangle",
        "descending_triangle",
        "symmetrical_triangle",
    }
    for p in LIBRARY.values():
        assert p.verdict and p.meaning and p.trade and p.fails
        assert (p.bias == "bullish") == (p.action == "buy")


def test_head_and_shoulders_confirmed_below_the_neckline() -> None:
    m = found(HS)["head_and_shoulders"]
    assert (m.direction, m.status) == ("bearish", "confirmed")
    assert [p.label for p in m.points] == ["Left shoulder", "Head", "Right shoulder"]
    assert m.breakout is not None and m.target is not None and m.target < m.breakout
    assert m.invalidation == pytest.approx(100.5 * 1.004, abs=0.01)  # the right shoulder's high
    assert "Confirmed: closed below" in m.text


def test_inverse_head_and_shoulders_is_the_mirror() -> None:
    m = found(mirror(HS))["inverse_head_and_shoulders"]
    assert (m.direction, m.status) == ("bullish", "confirmed")
    assert m.target is not None and m.breakout is not None and m.target > m.breakout


def test_double_top_confirmed_and_target_is_the_measured_move() -> None:
    m = found(DOUBLE_TOP)["double_top"]
    assert (m.direction, m.status) == ("bearish", "confirmed")
    neck = 90 * 0.996
    top = 100.5 * 1.004
    assert m.breakout == pytest.approx(neck, abs=0.01)
    assert m.target == pytest.approx(neck - (top - neck), abs=0.02)
    assert m.bars_since_breakout is not None and m.bars_since_breakout <= 3


def test_double_bottom_forming_until_the_middle_peak_breaks() -> None:
    closes = walk(130, (25, 100), (12, 110), (12, 99.5), (7, 104))
    m = found(closes)["double_bottom"]
    assert (m.direction, m.status) == ("bullish", "forming")
    assert m.bars_since_breakout is None
    assert "would confirm it" in m.text


def test_second_leg_must_start_before_a_double_bottom_shows() -> None:
    # Price is still sitting on the second low: not a W yet.
    closes = walk(130, (25, 100), (12, 110), (12, 99.5), (7, 99.8))
    assert "double_bottom" not in found(closes)


def test_old_breakouts_are_not_in_play() -> None:
    closes = DOUBLE_TOP + walk(DOUBLE_TOP[-1], (30, 70))[1:]
    assert "double_top" not in found(closes)


def test_ascending_and_descending_triangles() -> None:
    m = found(ASC_TRIANGLE)["ascending_triangle"]
    assert (m.direction, m.status) == ("bullish", "forming")
    assert m.breakout == pytest.approx(100 * 1.004, rel=0.003)  # the flat top
    d = found(mirror(ASC_TRIANGLE))["descending_triangle"]
    assert d.direction == "bearish"


def test_symmetrical_triangle_waits_for_the_break() -> None:
    m = found(SYM_TRIANGLE)["symmetrical_triangle"]
    assert (m.direction, m.status) == ("neutral", "forming")
    assert "would break it the other way" in m.text
    up = found(SYM_TRIANGLE + walk(SYM_TRIANGLE[-1], (3, 106))[1:])["symmetrical_triangle"]
    assert (up.direction, up.status) == ("bullish", "confirmed")


def test_wedges() -> None:
    assert found(RISING_WEDGE)["rising_wedge"].direction == "bearish"
    assert found(mirror(RISING_WEDGE))["falling_wedge"].direction == "bullish"


def test_bull_flag_breaks_out_on_volume() -> None:
    rng = np.random.default_rng(1)
    base = list(100 + rng.normal(0, 0.2, 40))
    closes = base + walk(base[-1], (6, 115), (8, 111), (2, 116))[1:]
    volume = [1000.0] * 40 + [3000.0] * 6 + [600.0] * 8 + [4000.0] * 2
    m = found(closes, volume)["bull_flag"]
    assert (m.direction, m.status) == ("bullish", "confirmed")
    assert m.volume_confirmed is True
    assert m.target is not None and m.breakout is not None
    assert m.target - m.breakout == pytest.approx(115 * 1.004 - min(base[-15:]) * 0.996, rel=0.1)


def test_bear_flag_is_the_mirror() -> None:
    rng = np.random.default_rng(2)
    base = list(100 + rng.normal(0, 0.2, 40))
    closes = base + walk(base[-1], (6, 85), (8, 89), (2, 84))[1:]
    assert found(closes)["bear_flag"].direction == "bearish"


def cup(rim: float, depth: float, bars: int) -> list[float]:
    x = np.linspace(0, 2 * np.pi, bars)
    return list(rim - depth * (1 - np.cos(x)) / 2)


def test_cup_and_handle_forming_and_it_outranks_the_saucer() -> None:
    lead = walk(85, (15, 100))
    closes = lead + cup(100, 20, 41)[1:] + walk(100, (4, 96), (5, 97.5))[1:]
    got = found(closes)
    m = got["cup_and_handle"]
    assert (m.direction, m.status) == ("bullish", "forming")
    assert [p.label for p in m.points] == ["Left rim", "Cup bottom", "Right rim", "Handle"]
    assert "rounding_bottom" not in got


def test_rounding_bottom_forming() -> None:
    x = np.linspace(0, np.pi * 0.92, 150)
    closes = list(120 - 20 * np.sin(x))
    m = found(closes)["rounding_bottom"]
    assert (m.direction, m.status) == ("bullish", "forming")
    assert m.target is not None and m.breakout is not None and m.target > m.breakout


def test_a_plain_trend_has_no_patterns() -> None:
    assert found(walk(100, (200, 150))) == {}


def test_too_little_history() -> None:
    assert found(walk(100, (20, 110))) == {}


def test_positions_refer_to_the_full_frame() -> None:
    closes = walk(60, (400, 80)) + DOUBLE_TOP[1:]
    m = found(closes)["double_top"]
    assert m.start > 400 and m.end == len(closes) - 1 - (m.bars_since_breakout or 0)


def test_patterns_api(client: TestClient) -> None:
    with Session(db.get_engine()) as s:
        df = frame(DOUBLE_TOP)
        df.index = df.index.date
        store.upsert_daily(s, "TEST.NS", df)
        s.commit()
    r = client.get("/analysis/technical/TEST.NS/patterns", params={"fetch": False})
    assert r.status_code == 200, r.text
    body = r.json()
    p = next(p for p in body["patterns"] if p["key"] == "double_top")
    assert p["name"] == "Double top" and p["family"] == "double_top"
    assert p["strength"] in ("strong", "moderate", "weak")
    assert p["target_pct"] < 0 < p["invalidation_pct"]
    assert p["points"][0]["t"] >= body["window"]["t"][0]
    assert len(body["window"]["t"]) == len(body["window"]["close"])
    lib = client.get("/analysis/patterns/library").json()
    assert {x["key"] for x in lib} == set(LIBRARY)
    assert client.get("/analysis/patterns/holdings").json() == []
