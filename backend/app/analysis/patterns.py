"""Classic chart patterns read from swing points: head and shoulders, double tops and bottoms,
rounding bottoms, cup and handle, wedges, flags and pennants, and triangles.

A pattern is reported only while it is still in play: forming (price is inside it) or confirmed
by a close through its breakout line in the last few bars. Each match carries the line that
confirms it, the level that cancels it and the textbook measured-move target, plus the points
and lines to draw it. Patterns are informational: they don't feed the technical score.
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Literal

import numpy as np
import pandas as pd

from app.analysis import indicators as ind
from app.analysis.structure import pivots
from app.core.formatting import format_inr
from app.core.profiles import PatternSettings

Direction = Literal["bullish", "bearish", "neutral"]
Status = Literal["forming", "confirmed"]
Horizon = Literal["good", "ok", "poor"]


# --------------------------------------------------------------------------- the guide


@dataclass(frozen=True)
class PatternInfo:
    key: str
    family: str  # the ten families the guide groups by
    family_label: str
    name: str
    kind: Literal["reversal", "continuation", "either"]
    bias: Direction
    action: Literal["buy", "sell", "wait"]
    verdict: str  # one line: good or bad, and what to do
    meaning: str
    trade: str  # entry trigger
    confirm: str
    fails: str
    target_rule: str
    reliability: Literal["high", "medium", "low"]
    duration: str  # typical length on a daily chart
    intraday: Horizon
    swing: Horizon
    positional: Horizon


LIBRARY: dict[str, PatternInfo] = {
    p.key: p
    for p in [
        PatternInfo(
            "head_and_shoulders",
            "head_and_shoulders",
            "Head and shoulders",
            "Head and shoulders",
            "reversal",
            "bearish",
            "sell",
            "Bad for holders: an uptrend is likely ending. Sell or tighten the stop-loss.",
            "Three peaks: a higher one (the head) between two lower, similar ones (the shoulders). "
            "Buyers pushed to a new high and then failed to, so the uptrend is losing strength.",
            "Sell or exit when a close breaks below the neckline (the line joining the two dips).",
            "A close below the neckline, ideally on higher volume.",
            "A close back above the right shoulder cancels it.",
            "Neckline minus the height from the head to the neckline.",
            "high",
            "3 weeks to several months",
            "ok",
            "good",
            "good",
        ),
        PatternInfo(
            "inverse_head_and_shoulders",
            "head_and_shoulders",
            "Head and shoulders",
            "Inverse head and shoulders",
            "reversal",
            "bullish",
            "buy",
            "Good: a downtrend is likely ending. A buy once the neckline breaks.",
            "Three troughs: a deeper one (the head) between two shallower, similar ones. Sellers "
            "pushed to a new low and then couldn't, so the downtrend is running out of steam.",
            "Buy when a close breaks above the neckline (the line joining the two peaks).",
            "A close above the neckline on rising volume.",
            "A close back below the right shoulder cancels it.",
            "Neckline plus the depth from the neckline to the head.",
            "high",
            "3 weeks to several months",
            "ok",
            "good",
            "good",
        ),
        PatternInfo(
            "double_top",
            "double_top",
            "Double top",
            "Double top",
            "reversal",
            "bearish",
            "sell",
            "Bad for holders: price failed twice at the same high. Sell or tighten the stop.",
            "An 'M' shape: price hits a high, dips, rallies back to about the same high and fails "
            "again. Sellers are defending that level.",
            "Sell or exit when a close breaks below the dip between the two tops.",
            "A close below the dip (the neckline). Lower volume on the second top adds weight.",
            "A close above the higher top cancels it.",
            "Neckline minus the height from the tops to the neckline.",
            "medium",
            "2 weeks to a few months",
            "ok",
            "good",
            "good",
        ),
        PatternInfo(
            "double_bottom",
            "double_bottom",
            "Double bottom",
            "Double bottom",
            "reversal",
            "bullish",
            "buy",
            "Good: price held the same low twice. A buy once it clears the middle peak.",
            "A 'W' shape: price falls to a low, bounces, falls back to about the same low and "
            "holds. Buyers are defending that level.",
            "Buy when a close breaks above the peak between the two bottoms.",
            "A close above the middle peak (the neckline), ideally on higher volume.",
            "A close below the lower bottom cancels it.",
            "Neckline plus the depth from the neckline to the bottoms.",
            "medium",
            "2 weeks to a few months",
            "ok",
            "good",
            "good",
        ),
        PatternInfo(
            "rounding_bottom",
            "rounding_bottom",
            "Rounding bottom",
            "Rounding bottom",
            "reversal",
            "bullish",
            "buy",
            "Good for long-term buyers: a slow shift from selling to buying.",
            "A wide, gentle 'U' (a saucer). Selling dries up slowly, price drifts sideways at the "
            "bottom, then buyers gradually take over. It takes months, not days.",
            "Buy when a close clears the left rim (where the decline began); patient investors "
            "sometimes buy on the right side of the U.",
            "A close above the rim; volume often rises along the right side.",
            "A fall back to the bottom of the U cancels it.",
            "Rim plus the depth of the U.",
            "medium",
            "3 months to a year or more",
            "poor",
            "ok",
            "good",
        ),
        PatternInfo(
            "cup_and_handle",
            "cup_and_handle",
            "Cup and handle",
            "Cup and handle",
            "continuation",
            "bullish",
            "buy",
            "Good: an uptrend resting before its next leg. A buy on the breakout.",
            "A rounded 'U' (the cup) back up to the old high, then a short, shallow dip (the "
            "handle) that shakes out weak holders before the uptrend resumes.",
            "Buy when a close breaks above the rim at the top of the handle.",
            "A close above the rim on higher volume. A handle that stays in the cup's upper half "
            "is healthier.",
            "A close below the bottom of the handle cancels it.",
            "Rim plus the depth of the cup.",
            "high",
            "7 weeks to over a year",
            "poor",
            "good",
            "good",
        ),
        PatternInfo(
            "rising_wedge",
            "wedges",
            "Wedges",
            "Rising wedge",
            "reversal",
            "bearish",
            "sell",
            "Bad: the rise is losing steam. Sell or tighten the stop when it breaks down.",
            "Price climbs between two rising lines that squeeze together: each new high is a "
            "smaller gain. Buyers are tiring even though price is still rising.",
            "Sell or exit when a close breaks below the lower line.",
            "A close below the lower line, often with a pick-up in volume.",
            "A close above the upper line cancels it.",
            "Back to where the wedge began (its widest point), measured from the break.",
            "medium",
            "2 weeks to 3 months",
            "ok",
            "good",
            "ok",
        ),
        PatternInfo(
            "falling_wedge",
            "wedges",
            "Wedges",
            "Falling wedge",
            "reversal",
            "bullish",
            "buy",
            "Good: the fall is losing steam. A buy when it breaks up.",
            "Price drops between two falling lines that squeeze together: each new low is a "
            "smaller loss. Sellers are tiring.",
            "Buy when a close breaks above the upper line.",
            "A close above the upper line on rising volume.",
            "A close below the lower line cancels it.",
            "Back to where the wedge began (its widest point), measured from the break.",
            "medium",
            "2 weeks to 3 months",
            "ok",
            "good",
            "ok",
        ),
        PatternInfo(
            "bull_flag",
            "flags_pennants",
            "Flags and pennants",
            "Bull flag",
            "continuation",
            "bullish",
            "buy",
            "Good: a sharp rise taking a short breather. A buy when it breaks up.",
            "A steep rally (the pole) followed by a short, orderly drift down or sideways in a "
            "narrow channel (the flag). Buyers are resting, not leaving.",
            "Buy when a close breaks above the top of the flag.",
            "A close above the flag on rising volume; volume should be light inside the flag.",
            "A close below the bottom of the flag cancels it.",
            "Breakout point plus the height of the pole.",
            "high",
            "1 to 4 weeks",
            "good",
            "good",
            "ok",
        ),
        PatternInfo(
            "bear_flag",
            "flags_pennants",
            "Flags and pennants",
            "Bear flag",
            "continuation",
            "bearish",
            "sell",
            "Bad: a sharp fall pausing before it resumes. Sell or stay out.",
            "A steep drop (the pole) followed by a short, weak bounce in a narrow channel (the "
            "flag). Sellers are pausing, not done.",
            "Sell or exit when a close breaks below the bottom of the flag.",
            "A close below the flag, ideally on higher volume.",
            "A close above the top of the flag cancels it.",
            "Breakdown point minus the height of the pole.",
            "high",
            "1 to 4 weeks",
            "good",
            "good",
            "ok",
        ),
        PatternInfo(
            "bull_pennant",
            "flags_pennants",
            "Flags and pennants",
            "Bullish pennant",
            "continuation",
            "bullish",
            "buy",
            "Good: a sharp rise taking a short breather. A buy when it breaks up.",
            "A steep rally (the pole) followed by a small symmetrical triangle: price swings "
            "narrow as the market catches its breath.",
            "Buy when a close breaks above the pennant's upper line.",
            "A close above the pennant on rising volume.",
            "A close below the pennant's lower line cancels it.",
            "Breakout point plus the height of the pole.",
            "medium",
            "1 to 3 weeks",
            "good",
            "good",
            "ok",
        ),
        PatternInfo(
            "bear_pennant",
            "flags_pennants",
            "Flags and pennants",
            "Bearish pennant",
            "continuation",
            "bearish",
            "sell",
            "Bad: a sharp fall pausing before it resumes. Sell or stay out.",
            "A steep drop (the pole) followed by a small symmetrical triangle as the selling "
            "pauses.",
            "Sell or exit when a close breaks below the pennant's lower line.",
            "A close below the pennant, ideally on higher volume.",
            "A close above the pennant's upper line cancels it.",
            "Breakdown point minus the height of the pole.",
            "medium",
            "1 to 3 weeks",
            "good",
            "good",
            "ok",
        ),
        PatternInfo(
            "ascending_triangle",
            "ascending_triangle",
            "Ascending triangle",
            "Ascending triangle",
            "continuation",
            "bullish",
            "buy",
            "Good: buyers keep stepping in higher. A buy on the breakout above the flat top.",
            "A flat ceiling with rising lows. Sellers hold one price, but buyers pay a little more "
            "on every dip, so the ceiling usually gives way.",
            "Buy when a close breaks above the flat top.",
            "A close above the top on higher volume.",
            "A close below the rising lower line cancels it.",
            "Breakout point plus the height of the triangle at its widest.",
            "medium",
            "3 weeks to 3 months",
            "good",
            "good",
            "ok",
        ),
        PatternInfo(
            "descending_triangle",
            "descending_triangle",
            "Descending triangle",
            "Descending triangle",
            "continuation",
            "bearish",
            "sell",
            "Bad: sellers keep pressing lower. Sell or stay out if the flat floor breaks.",
            "A flat floor with falling highs. Buyers hold one price, but sellers accept a little "
            "less on every bounce, so the floor usually gives way.",
            "Sell or exit when a close breaks below the flat floor.",
            "A close below the floor, ideally on higher volume.",
            "A close above the falling upper line cancels it.",
            "Breakdown point minus the height of the triangle at its widest.",
            "medium",
            "3 weeks to 3 months",
            "good",
            "good",
            "ok",
        ),
        PatternInfo(
            "symmetrical_triangle",
            "symmetrical_triangle",
            "Symmetrical triangle",
            "Symmetrical triangle",
            "either",
            "neutral",
            "wait",
            "Neutral: wait for the break. It usually continues the trend that came before.",
            "Lower highs and higher lows squeeze price into a point. Buyers and sellers are evenly "
            "matched; the side that wins the break usually runs with it.",
            "Buy on a close above the upper line, or sell on a close below the lower line.",
            "A close outside either line, ideally on higher volume.",
            "A break that quickly reverses back inside the triangle is a false start.",
            "Breakout point plus or minus the height of the triangle at its widest.",
            "medium",
            "3 weeks to 3 months",
            "good",
            "good",
            "ok",
        ),
    ]
}


# --------------------------------------------------------------------------- matches


@dataclass(frozen=True)
class PatternPoint:
    i: int  # bar position in the frame passed to detect()
    price: float
    label: str


@dataclass(frozen=True)
class PatternLine:
    label: str
    kind: Literal["neckline", "trend", "rim", "curve"]
    points: list[tuple[int, float]]


@dataclass
class PatternMatch:
    key: str
    direction: Direction
    status: Status
    confidence: int  # 0–95: how cleanly the shape fits, plus confirmation and volume
    start: int
    end: int  # the breakout bar, or the latest bar while forming
    breakout: float | None  # the close beyond this confirms the pattern
    target: float | None  # textbook measured move
    invalidation: float | None  # a close beyond this cancels it
    bars_since_breakout: int | None
    volume_confirmed: bool | None
    text: str
    points: list[PatternPoint] = field(default_factory=list)
    lines: list[PatternLine] = field(default_factory=list)


@dataclass(frozen=True)
class _Swing:
    i: int
    price: float
    kind: Literal["H", "L"]


@dataclass
class _Ctx:
    h: np.ndarray
    lo: np.ndarray
    c: np.ndarray
    vol: np.ndarray | None
    vr: np.ndarray | None
    atr: np.ndarray
    cfg: PatternSettings
    surge: float
    unit: str
    px: Callable[[float], str]

    @property
    def n(self) -> int:
        return len(self.c)

    @property
    def buf(self) -> float:
        return self.cfg.breakout_buffer_pct / 100

    @property
    def tol(self) -> float:
        return self.cfg.peak_tolerance_pct / 100


def _swings(df: pd.DataFrame, k: int) -> list[_Swing]:
    """Alternating swing highs and lows; of two in a row of one kind, the more extreme stays."""
    ph, pl = pivots(df["high"], df["low"], k)
    pts = [
        _Swing(int(i), float(p), "H")
        for i, p in zip(df.index.get_indexer(ph.index), ph, strict=True)
    ]
    pts += [
        _Swing(int(i), float(p), "L")
        for i, p in zip(df.index.get_indexer(pl.index), pl, strict=True)
    ]
    out: list[_Swing] = []
    for s in sorted(pts, key=lambda s: (s.i, s.kind)):
        if out and out[-1].kind == s.kind:
            if (s.kind == "H") == (s.price > out[-1].price):
                out[-1] = s
            continue
        out.append(s)
    return out


def _conf(quality: float, confirmed: bool, volume: bool | None) -> int:
    q = min(max(quality, 0.0), 1.0)
    return round(min(95.0, 40 + 35 * q + (12 if confirmed else 0) + (8 if volume else 0)))


def _vol_ok(x: _Ctx, j: int) -> bool | None:
    if x.vr is None or np.isnan(x.vr[j]):
        return None
    return bool(x.vr[j] >= x.surge)


def _level(v: float) -> Callable[[int], float]:
    """A horizontal line, as a function of bar position."""
    return lambda _i: v


def _break(x: _Ctx, start: int, line: Callable[[int], float], up: bool) -> int | None:
    """First bar from `start` whose close clears `line` by the buffer, upwards or downwards."""
    for j in range(max(start, 0), x.n):
        lv = line(j)
        if (up and x.c[j] > lv * (1 + x.buf)) or (not up and x.c[j] < lv * (1 - x.buf)):
            return j
    return None


def _status_text(
    x: _Ctx,
    direction: Direction,
    j: int | None,
    breakout: float,
    target: float,
    invalidation: float,
) -> str:
    up = direction == "bullish"
    if j is None:
        side = "above" if up else "below"
        cancel = "below" if up else "above"
        return (
            f"Not confirmed yet: a close {side} {x.px(breakout)} would confirm it "
            f"(textbook target {x.px(target)}). A close {cancel} {x.px(invalidation)} cancels it."
        )
    ago = x.n - 1 - j
    when = "on the latest bar" if ago == 0 else f"{ago} {x.unit}{'s' if ago != 1 else ''} ago"
    vol = _vol_ok(x, j)
    vol_txt = (
        f" on {x.vr[j]:.1f}× volume"  # type: ignore[index]
        if vol
        else " without a volume surge (less reliable)"
        if vol is False
        else ""
    )
    side = "above" if up else "below"
    cancel = "below" if up else "above"
    return (
        f"Confirmed: closed {side} {x.px(breakout)} {when}{vol_txt}. "
        f"Textbook target {x.px(target)}; a close {cancel} {x.px(invalidation)} cancels it."
    )


def _make(
    x: _Ctx,
    key: str,
    direction: Direction,
    quality: float,
    start: int,
    j: int | None,
    breakout: float,
    target: float,
    invalidation: float,
    summary: str,
    points: list[PatternPoint],
    lines: list[PatternLine],
) -> PatternMatch | None:
    if j is not None and x.n - 1 - j > x.cfg.recent_breakout_bars:
        return None  # confirmed long ago: no longer in play
    vol = _vol_ok(x, j) if j is not None else None
    return PatternMatch(
        key=key,
        direction=direction,
        status="confirmed" if j is not None else "forming",
        confidence=_conf(quality, j is not None, vol),
        start=start,
        end=j if j is not None else x.n - 1,
        breakout=round(breakout, 2),
        target=round(target, 2) if target > 0 else None,
        invalidation=round(invalidation, 2),
        bars_since_breakout=None if j is None else x.n - 1 - j,
        volume_confirmed=vol,
        text=f"{summary} {_status_text(x, direction, j, breakout, target, invalidation)}",
        points=points,
        lines=lines,
    )


# --------------------------------------------------------------------------- detectors


def _double(x: _Ctx, sw: list[_Swing], k: int, top: bool) -> list[PatternMatch]:
    kind = "H" if top else "L"
    ext = [s for s in sw if s.kind == kind]
    out: list[PatternMatch] = []
    for bi in range(len(ext) - 1, max(len(ext) - 3, 0), -1):
        b = ext[bi]
        for a in ext[max(0, bi - 3) : bi][::-1]:
            span = b.i - a.i
            if span < max(10, 3 * k):
                continue
            extreme = max(a.price, b.price) if top else min(a.price, b.price)
            if abs(a.price - b.price) / extreme > x.tol:
                continue
            mid = slice(a.i + 1, b.i)
            if top:
                if x.h[mid].max() > extreme:
                    continue
                t_i = a.i + 1 + int(np.argmin(x.lo[mid]))
                neck = float(x.lo[t_i])
                depth = (min(a.price, b.price) - neck) / min(a.price, b.price)
                came_from = x.lo[max(0, a.i - span) : a.i]
                trend_ok = len(came_from) > 0 and came_from.min() < neck
            else:
                if x.lo[mid].min() < extreme:
                    continue
                t_i = a.i + 1 + int(np.argmax(x.h[mid]))
                neck = float(x.h[t_i])
                depth = (neck - max(a.price, b.price)) / neck
                came_from = x.h[max(0, a.i - span) : a.i]
                trend_ok = len(came_from) > 0 and came_from.max() > neck
            if depth * 100 < x.cfg.min_depth_pct or not trend_ok:
                continue
            after = x.c[b.i + 1 :]
            if top and after.size and after.max() > extreme * (1 + x.buf):
                continue
            if not top and after.size and after.min() < extreme * (1 - x.buf):
                continue
            j = _break(x, b.i + 1, _level(neck), up=not top)
            height = abs(extreme - neck)
            if j is None and (x.n - 1 - b.i > span or abs(x.c[-1] - b.price) < 0.3 * height):
                continue  # stale, or the second leg of the M / W hasn't started yet
            target = neck - height if top else neck + height
            sim = 1 - abs(a.price - b.price) / extreme / x.tol
            depth_q = min(1.0, depth * 100 / (3 * x.cfg.min_depth_pct))
            vol_q = 0.5
            if x.vol is not None and x.vol[a.i] > 0:
                vol_q = 1.0 if x.vol[b.i] < x.vol[a.i] else 0.3
            word = "top" if top else "bottom"
            summary = (
                f"Two {word}s at {x.px(a.price)} and {x.px(b.price)} with a "
                f"{'dip' if top else 'peak'} to {x.px(neck)} between."
            )
            m = _make(
                x,
                "double_top" if top else "double_bottom",
                "bearish" if top else "bullish",
                0.5 * sim + 0.3 * depth_q + 0.2 * vol_q,
                a.i,
                j,
                neck,
                target,
                extreme,
                summary,
                [
                    PatternPoint(a.i, a.price, f"{word.title()} 1"),
                    PatternPoint(t_i, neck, "Neckline"),
                    PatternPoint(b.i, b.price, f"{word.title()} 2"),
                ],
                [
                    PatternLine(
                        "Neckline",
                        "neckline",
                        [(a.i, neck), (j if j is not None else x.n - 1, neck)],
                    )
                ],
            )
            if m:
                out.append(m)
                break
    return out


def _head_shoulders(x: _Ctx, sw: list[_Swing], top: bool) -> list[PatternMatch]:
    kind = "H" if top else "L"
    out: list[PatternMatch] = []
    # Five alternating swings: shoulder, dip, head, dip, shoulder. Only the latest few windows.
    starts = [q for q in range(len(sw) - 5, -1, -1) if sw[q].kind == kind][:3]
    for q in starts:
        ls, d1, hd, d2, rs = sw[q : q + 5]
        sgn = 1 if top else -1
        shoulder = max(ls.price, rs.price) if top else min(ls.price, rs.price)
        if sgn * (hd.price - shoulder) / shoulder * 100 < x.cfg.head_min_pct:
            continue
        if abs(ls.price - rs.price) / shoulder > 2 * x.tol:
            continue
        neck_avg = (d1.price + d2.price) / 2
        if abs(d1.price - d2.price) / neck_avg > 2 * x.tol:
            continue
        head_h = abs(hd.price - neck_avg)
        if min(abs(ls.price - neck_avg), abs(rs.price - neck_avg)) < 0.3 * head_h:
            continue
        left, right = hd.i - ls.i, rs.i - hd.i
        if not 1 / 3 <= left / right <= 3:
            continue
        before = x.lo[max(0, ls.i - left) : ls.i] if top else x.h[max(0, ls.i - left) : ls.i]
        if not before.size or (
            before.min() >= min(d1.price, d2.price)
            if top
            else before.max() <= max(d1.price, d2.price)
        ):
            continue  # no trend into the pattern to reverse

        def neck(i: int, d1: _Swing = d1, d2: _Swing = d2) -> float:
            return d1.price + (d2.price - d1.price) * (i - d1.i) / (d2.i - d1.i)

        after = x.c[rs.i + 1 :]
        if after.size and (after.max() > hd.price if top else after.min() < hd.price):
            continue
        j = _break(x, rs.i + 1, neck, up=not top)
        if j is None and x.n - 1 - rs.i > 1.5 * right:
            continue
        at = neck(j if j is not None else x.n - 1)
        depth = abs(hd.price - neck(hd.i))
        target = at - depth if top else at + depth
        sym = 1 - abs(ls.price - rs.price) / shoulder / (2 * x.tol)
        time_sym = min(left, right) / max(left, right)
        flat = 1 - abs(d1.price - d2.price) / neck_avg / (2 * x.tol)
        end = j if j is not None else x.n - 1
        name = "head and shoulders" if top else "inverse head and shoulders"
        summary = (
            f"A {name}: shoulders at {x.px(ls.price)} and {x.px(rs.price)}, head at "
            f"{x.px(hd.price)}, neckline near {x.px(at)}."
        )
        m = _make(
            x,
            "head_and_shoulders" if top else "inverse_head_and_shoulders",
            "bearish" if top else "bullish",
            0.4 * sym + 0.3 * time_sym + 0.3 * flat,
            ls.i,
            j,
            at,
            target,
            rs.price,
            summary,
            [
                PatternPoint(ls.i, ls.price, "Left shoulder"),
                PatternPoint(hd.i, hd.price, "Head"),
                PatternPoint(rs.i, rs.price, "Right shoulder"),
            ],
            [PatternLine("Neckline", "neckline", [(d1.i, d1.price), (end, round(neck(end), 2))])],
        )
        if m:
            out.append(m)
            break
    return out


def _fit(xs: np.ndarray, ys: np.ndarray) -> tuple[float, float]:
    slope, icept = np.polyfit(xs.astype("float64"), ys.astype("float64"), 1)
    return float(slope), float(icept)


def _trendlines(x: _Ctx, sw: list[_Swing], k: int) -> list[PatternMatch]:
    """Triangles and wedges: lines through the latest swing highs and swing lows."""
    highs = [s for s in sw if s.kind == "H"]
    lows = [s for s in sw if s.kind == "L"]
    flat = x.cfg.flat_slope_pct / 100
    best: tuple[float, PatternMatch] | None = None
    for nh in (4, 3, 2):
        for nl in (4, 3, 2):
            if nh + nl < 5 or len(highs) < nh or len(lows) < nl:
                continue
            hs, ls_ = highs[-nh:], lows[-nl:]
            start = min(hs[0].i, ls_[0].i)
            last = max(hs[-1].i, ls_[-1].i)
            length = last - start
            if length < max(20, 5 * k):
                continue
            su, bu = _fit(np.array([s.i for s in hs]), np.array([s.price for s in hs]))
            sl, bl = _fit(np.array([s.i for s in ls_]), np.array([s.price for s in ls_]))

            def upper(i: int, su: float = su, bu: float = bu) -> float:
                return su * i + bu

            def lower(i: int, sl: float = sl, bl: float = bl) -> float:
                return sl * i + bl

            res = max(
                max(abs(s.price - upper(s.i)) / s.price for s in hs),
                max(abs(s.price - lower(s.i)) / s.price for s in ls_),
            )
            if res > 0.7 * x.tol:
                continue
            idx = np.arange(start, last + 1)
            band = x.tol / 2
            if (x.c[idx] > (su * idx + bu) * (1 + band)).any() or (
                x.c[idx] < (sl * idx + bl) * (1 - band)
            ).any():
                continue
            mean = float(np.mean([s.price for s in hs + ls_]))
            pu, pl = su / mean, sl / mean
            w0, wn = upper(start) - lower(start), upper(x.n - 1) - lower(x.n - 1)
            if w0 <= 0:
                continue
            converging = upper(last) - lower(last) < 0.75 * w0
            if abs(pu) <= flat and pl > flat:
                key, bias = "ascending_triangle", "bullish"
            elif abs(pl) <= flat and pu < -flat:
                key, bias = "descending_triangle", "bearish"
            elif pu < -flat and pl > flat and converging:
                key, bias = "symmetrical_triangle", "neutral"
            elif pu > flat and pl > flat and pl > pu and converging:
                key, bias = "rising_wedge", "bearish"
            elif pu < -flat and pl < -flat and pu < pl and converging:
                key, bias = "falling_wedge", "bullish"
            else:
                continue
            apex = (bl - bu) / (su - sl) if su != sl else float("inf")
            up_j = _break(x, last + 1, upper, up=True)
            dn_j = _break(x, last + 1, lower, up=False)
            j: int | None
            if up_j is not None and (dn_j is None or up_j < dn_j):
                j, broke = up_j, "bullish"
            elif dn_j is not None:
                j, broke = dn_j, "bearish"
            else:
                j, broke = None, None
            if broke is not None and bias != "neutral" and broke != bias:
                continue  # broke the wrong way: the pattern failed
            if j is None and (apex <= x.n - 1 or wn <= 0 or x.n - 1 - last > length):
                continue  # lines already met, or the pattern went stale
            direction: Direction = broke if broke is not None else bias  # type: ignore[assignment]
            end = j if j is not None else x.n - 1
            if direction == "bearish":
                trig, cancel, target = lower(end), upper(end), lower(end) - w0
            else:
                trig, cancel, target = upper(end), lower(end), upper(end) + w0
            touches = min(1.0, (nh + nl - 4) / 4)
            quality = 0.4 * touches + 0.4 * (1 - res / (0.7 * x.tol)) + 0.2 * min(1.0, 1 - wn / w0)
            info = LIBRARY[key]
            summary = (
                f"A {info.name.lower()} over {length} {x.unit}s: {nh} touches of the upper line "
                f"and {nl} of the lower."
            )
            if key == "symmetrical_triangle" and j is None:
                summary += (
                    f" A close below {x.px(lower(end))} would break it the other way "
                    f"(target {x.px(lower(end) - w0)})."
                )
            m = _make(
                x,
                key,
                direction,
                quality,
                start,
                j,
                trig,
                target,
                cancel,
                summary,
                [PatternPoint(s.i, s.price, "") for s in sorted(hs + ls_, key=lambda s: s.i)],
                [
                    PatternLine(
                        "Upper line",
                        "trend",
                        [(start, round(upper(start), 2)), (end, round(upper(end), 2))],
                    ),
                    PatternLine(
                        "Lower line",
                        "trend",
                        [(start, round(lower(start), 2)), (end, round(lower(end), 2))],
                    ),
                ],
            )
            if m and (best is None or quality > best[0]):
                best = (quality, m)
    return [best[1]] if best else []


def _flags(x: _Ctx) -> list[PatternMatch]:
    """A sharp pole, then a short flag (parallel channel) or pennant (converging lines)."""
    fmin, fmax = x.cfg.flag_bars
    flat = x.cfg.flat_slope_pct / 100
    pmax = x.cfg.pole_max_bars
    best: tuple[float, PatternMatch] | None = None
    lo_s = max(pmax, x.n - 1 - fmax - x.cfg.recent_breakout_bars)
    for bull in (True, False):
        for s in range(x.n - 1 - fmin, lo_s - 1, -1):
            seg = slice(s - pmax, s + 1)
            if bull:
                if x.h[s] < x.h[seg].max():
                    continue
                p0 = s - pmax + int(np.argmin(x.lo[seg]))
                pole = x.h[s] - x.lo[p0]
                top = x.h[s]
            else:
                if x.lo[s] > x.lo[seg].min():
                    continue
                p0 = s - pmax + int(np.argmax(x.h[seg]))
                pole = x.h[p0] - x.lo[s]
                top = x.lo[s]
            atr = x.atr[s]
            if s - p0 < 2 or np.isnan(atr) or atr <= 0 or pole < x.cfg.pole_atr * atr:
                continue
            found: tuple[int, int | None] | None = None  # (last flag bar, breakout bar)
            for e in range(s + 1, min(s + fmax, x.n - 1) + 1):
                body = slice(s + 1, e + 1)
                if bull and (
                    x.lo[body].min() < top - 0.5 * pole or x.h[body].max() > top * (1 + x.buf)
                ):
                    break
                if not bull and (
                    x.h[body].max() > top + 0.5 * pole or x.lo[body].min() < top * (1 - x.buf)
                ):
                    break
                if e - s < fmin or e - s > max(fmin, 4 * (s - p0)):
                    continue
                if e == x.n - 1:
                    found = (e, None)
                    break
                idx = np.arange(s, e + 1)
                su, bu = _fit(idx, x.h[s : e + 1])
                sl, bl = _fit(idx, x.lo[s : e + 1])
                nxt = e + 1
                if (bull and x.c[nxt] > (su * nxt + bu) * (1 + x.buf)) or (
                    not bull and x.c[nxt] < (sl * nxt + bl) * (1 - x.buf)
                ):
                    found = (e, nxt)
                    break
            if not found:
                continue
            e, j = found
            idx = np.arange(s, e + 1)
            su, bu = _fit(idx, x.h[s : e + 1])
            sl, bl = _fit(idx, x.lo[s : e + 1])
            pu, pl = su / top, sl / top
            w0, we = (su * s + bu) - (sl * s + bl), (su * e + bu) - (sl * e + bl)
            if pu < -flat / 2 and pl > flat / 2 and we < 0.7 * w0:
                key = "bull_pennant" if bull else "bear_pennant"
            elif abs(pu - pl) <= 1.5 * flat and (
                (bull and (pu + pl) / 2 <= flat / 2) or (not bull and (pu + pl) / 2 >= -flat / 2)
            ):
                key = "bull_flag" if bull else "bear_flag"
            else:
                continue
            end = j if j is not None else x.n - 1
            flag_lo, flag_hi = float(x.lo[s + 1 : e + 1].min()), float(x.h[s + 1 : e + 1].max())
            if bull:
                trig, cancel = su * end + bu, flag_lo
                target = trig + pole
            else:
                trig, cancel = sl * end + bl, flag_hi
                target = trig - pole
            strength = min(1.0, pole / atr / (2 * x.cfg.pole_atr))
            tight = 1 - min(1.0, (flag_hi - flag_lo) / pole)
            vol_q = 0.5
            if x.vol is not None:
                pv, fv = x.vol[p0 : s + 1].mean(), x.vol[s + 1 : e + 1].mean()
                if pv > 0:
                    vol_q = 1.0 if fv < pv else 0.2
            quality = 0.4 * strength + 0.35 * tight + 0.25 * vol_q
            move = (pole / x.lo[p0] if bull else pole / x.h[p0]) * 100
            rest = "pause" if key.endswith("flag") else "narrowing swings"
            summary = (
                f"A {'rise' if bull else 'drop'} of {move:.0f}% in {s - p0} {x.unit}s (the pole), "
                f"then {e - s} {x.unit}s of {rest}."
            )
            m = _make(
                x,
                key,
                "bullish" if bull else "bearish",
                quality,
                p0,
                j,
                trig,
                target,
                cancel,
                summary,
                [
                    PatternPoint(p0, float(x.lo[p0] if bull else x.h[p0]), "Pole start"),
                    PatternPoint(s, float(top), "Pole top" if bull else "Pole bottom"),
                ],
                [
                    PatternLine(
                        "Pole",
                        "trend",
                        [(p0, float(x.lo[p0] if bull else x.h[p0])), (s, float(top))],
                    ),
                    PatternLine(
                        "Upper line",
                        "trend",
                        [(s, round(su * s + bu, 2)), (end, round(su * end + bu, 2))],
                    ),
                    PatternLine(
                        "Lower line",
                        "trend",
                        [(s, round(sl * s + bl, 2)), (end, round(sl * end + bl, 2))],
                    ),
                ],
            )
            if m and (best is None or quality > best[0]):
                best = (quality, m)
            break  # the latest valid pole for this direction
    return [best[1]] if best else []


def _u_fit(c: np.ndarray) -> tuple[float, float, np.ndarray] | None:
    """Quadratic fit of a U: (R², vertex position 0–1, fitted values), or None if not a U."""
    xs = np.linspace(0, 1, len(c))
    a, b, k = np.polyfit(xs, c, 2)
    if a <= 0:
        return None
    fitted = a * xs**2 + b * xs + k
    ss = float(((c - c.mean()) ** 2).sum())
    r2 = 1 - float(((c - fitted) ** 2).sum()) / ss if ss > 0 else 0.0
    return r2, float(-b / (2 * a)), fitted


def _curve(start: int, fitted: np.ndarray, n: int = 16) -> list[tuple[int, float]]:
    pos = np.linspace(0, len(fitted) - 1, min(n, len(fitted))).round().astype(int)
    return [(start + int(p), round(float(fitted[p]), 2)) for p in pos]


def _rounding_bottom(x: _Ctx) -> list[PatternMatch]:
    best: tuple[float, PatternMatch] | None = None
    for w in sorted({min(x.n, w) for w in (60, 100, 150, 250)}):
        if w < 40:
            continue
        s = x.n - w
        seg = x.c[s:]
        fit = _u_fit(seg)
        if not fit:
            continue
        r2, vx, fitted = fit
        if r2 < 0.75 or not 0.3 <= vx <= 0.7:
            continue
        rim_i = s + int(np.argmax(seg[: max(3, w * 15 // 100)]))
        rim = float(x.c[rim_i])
        b_i = s + int(np.argmin(x.lo[s:]))
        bottom = float(x.lo[b_i])
        depth = rim - bottom
        if depth / rim * 100 < x.cfg.rounding_min_depth_pct or not 0.25 <= (b_i - s) / w <= 0.75:
            continue
        if seg[0] < bottom + 0.8 * depth or x.c[-1] < bottom + 0.6 * depth:
            continue
        if (seg <= bottom + depth / 3).mean() < 0.2:
            continue  # a V, not a saucer
        j = _break(x, b_i, _level(rim), up=True)
        cancel = float(x.lo[-max(5, w // 8) :].min())
        m = _make(
            x,
            "rounding_bottom",
            "bullish",
            0.6 * (r2 - 0.75) / 0.25
            + 0.4 * min(1.0, depth / rim * 100 / (3 * x.cfg.rounding_min_depth_pct)),
            s,
            j,
            rim,
            rim + depth,
            cancel,
            f"A {w}-{x.unit} saucer from {x.px(rim)} down to {x.px(bottom)} and back up.",
            [PatternPoint(rim_i, rim, "Left rim"), PatternPoint(b_i, bottom, "Bottom")],
            [
                PatternLine("Curve", "curve", _curve(s, fitted)),
                PatternLine("Rim", "rim", [(rim_i, rim), (j if j is not None else x.n - 1, rim)]),
            ],
        )
        if m and (best is None or r2 > best[0]):
            best = (r2, m)
    return [best[1]] if best else []


def _cup_handle(x: _Ctx, sw: list[_Swing]) -> list[PatternMatch]:
    highs = [s for s in sw if s.kind == "H"]
    lo_d, hi_d = x.cfg.cup_depth_pct
    for ri in range(len(highs) - 1, max(len(highs) - 3, 0), -1):
        r = highs[ri]
        for left in highs[:ri][::-1]:
            cup = r.i - left.i
            if cup < 20:
                continue
            rim = max(left.price, r.price)
            if abs(left.price - r.price) / rim > 1.5 * x.tol or x.h[left.i + 1 : r.i].max() > rim:
                continue
            b_i = left.i + 1 + int(np.argmin(x.lo[left.i + 1 : r.i]))
            bottom = float(x.lo[b_i])
            depth = rim - bottom
            if not lo_d <= depth / rim * 100 <= hi_d:
                continue
            fit = _u_fit(x.c[left.i : r.i + 1])
            if not fit or fit[0] < 0.6 or not 0.25 <= fit[1] <= 0.75:
                continue
            j = _break(x, r.i + 1, _level(rim), up=True)
            handle_end = (j - 1) if j is not None else x.n - 1
            if handle_end - r.i < 3 or handle_end - r.i > cup / 2:
                continue
            h_lo_i = r.i + 1 + int(np.argmin(x.lo[r.i + 1 : handle_end + 1]))
            h_lo = float(x.lo[h_lo_i])
            retrace = (rim - h_lo) / depth
            if retrace > 0.5 or retrace <= 0:
                continue
            quality = (
                0.5 * (fit[0] - 0.6) / 0.4
                + 0.3 * (1 - retrace / 0.5)
                + 0.2 * (1 - abs(left.price - r.price) / rim / (1.5 * x.tol))
            )
            m = _make(
                x,
                "cup_and_handle",
                "bullish",
                quality,
                left.i,
                j,
                rim,
                rim + depth,
                h_lo,
                f"A {cup}-{x.unit} cup {depth / rim * 100:.0f}% deep with its rim at {x.px(rim)}, "
                f"then a {handle_end - r.i}-{x.unit} handle that dipped to {x.px(h_lo)}.",
                [
                    PatternPoint(left.i, left.price, "Left rim"),
                    PatternPoint(b_i, bottom, "Cup bottom"),
                    PatternPoint(r.i, r.price, "Right rim"),
                    PatternPoint(h_lo_i, h_lo, "Handle"),
                ],
                [
                    PatternLine("Cup", "curve", _curve(left.i, fit[2])),
                    PatternLine(
                        "Rim", "rim", [(left.i, rim), (j if j is not None else x.n - 1, rim)]
                    ),
                ],
            )
            if m:
                return [m]
    return []


def detect(
    df: pd.DataFrame,
    cfg: PatternSettings,
    *,
    volume_surge: float = 1.5,
    unit: str = "day",
    px: Callable[[float], str] = format_inr,
    limit: int = 6,
) -> list[PatternMatch]:
    """Patterns in play on an OHLCV frame (oldest first). Positions refer to `df`."""
    n_all = len(df)
    if n_all < 30:
        return []
    off = max(0, n_all - cfg.lookback_bars)
    w = df.iloc[off:]
    c = w["close"].to_numpy(dtype="float64")
    h = w["high"].fillna(w["close"]).to_numpy(dtype="float64")
    lo = w["low"].fillna(w["close"]).to_numpy(dtype="float64")
    has_vol = "volume" in w and w["volume"].fillna(0).gt(0).sum() > 20
    vol = w["volume"].fillna(0).to_numpy(dtype="float64") if has_vol else None
    vr = ind.volume_ratio(w["volume"], 20).to_numpy(dtype="float64") if has_vol else None
    atr = ind.atr(
        w["high"].fillna(w["close"]), w["low"].fillna(w["close"]), w["close"], 14
    ).to_numpy(dtype="float64")
    x = _Ctx(h, lo, c, vol, vr, atr, cfg, volume_surge, unit, px)

    found: list[PatternMatch] = []
    for k in cfg.pivot_windows:
        sw = _swings(w, k)
        for top in (True, False):
            found += _head_shoulders(x, sw, top)
            found += _double(x, sw, k, top)
        found += _trendlines(x, sw, k)
        found += _cup_handle(x, sw)
    found += _flags(x)
    found += _rounding_bottom(x)

    # One match per pattern (the cleanest across swing scales); a cup outranks its saucer.
    by_key: dict[str, PatternMatch] = {}
    for m in found:
        if m.key not in by_key or m.confidence > by_key[m.key].confidence:
            by_key[m.key] = m
    if "cup_and_handle" in by_key:
        by_key.pop("rounding_bottom", None)
    keep = [m for m in by_key.values() if m.confidence >= cfg.min_confidence]
    out = sorted(keep, key=lambda m: (m.status != "confirmed", -m.confidence))[:limit]
    for m in out:
        m.start += off
        m.end += off
        m.points = [PatternPoint(p.i + off, round(p.price, 2), p.label) for p in m.points]
        m.lines = [
            PatternLine(ln.label, ln.kind, [(i + off, round(v, 2)) for i, v in ln.points])
            for ln in m.lines
        ]
    return out
