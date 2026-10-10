"""Scoring: the engines' readings → sub-scores → technical, fundamental and composite scores.

Each sub-score (trend, momentum, valuation, growth …) is

    50 + 50 × Σ(direction × weight) / Σ(weight)

over the readings in that category, where direction is +1 bullish, −1 bearish and 0 neutral.
All bullish gives 100, all bearish 0, a balanced or neutral picture 50. A category with no
readings is "no data": it's left out, the other categories are re-weighted, and the gap lowers
*confidence* rather than the score. Every reading also carries the points it adds to (or takes
from) the composite score, which is how the top reasons are ranked.

All weights come from `scoring:` in profiles.yaml; docs/SCORING_METHOD.md explains them.
"""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Literal, Protocol

from app.analysis.fundamental import FundamentalReport
from app.analysis.technical import TechnicalReport
from app.core.profiles import Confidence, ConfidenceLevel, ScoringConfig

Direction = Literal["bullish", "bearish", "neutral"]
SIGN: dict[str, int] = {"bullish": 1, "bearish": -1, "neutral": 0}
TF_LABEL = {"15m": "15-min", "1h": "Hourly", "1d": "Daily", "1wk": "Weekly", "1mo": "Monthly"}


class _Obs(Protocol):
    @property
    def key(self) -> str: ...
    @property
    def category(self) -> str: ...
    @property
    def direction(self) -> str: ...
    @property
    def text(self) -> str: ...
    @property
    def minor(self) -> bool: ...


@dataclass
class Reading:
    """One engine observation as it enters the score."""

    source: Literal["technical", "fundamental"]
    key: str
    category: str
    direction: Direction
    text: str
    minor: bool
    weight: float  # 0 = shown but not scored
    points: float = 0.0  # signed contribution to the composite score
    timeframes: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class SubScore:
    category: str
    score: float | None  # None = no scored readings
    weight: float  # configured weight
    bullish: int
    bearish: int
    neutral: int


@dataclass(frozen=True)
class TimeframeScore:
    interval: str
    score: float | None
    coverage: float
    weight: float  # share of the technical score
    subscores: list[SubScore]


@dataclass
class SideScore:
    """Technical or fundamental score with its coverage (share of weighted inputs present)."""

    score: float | None
    coverage: float
    subscores: list[SubScore]
    timeframes: list[TimeframeScore] = field(default_factory=list)
    applicable: bool = True
    notes: list[str] = field(default_factory=list)


@dataclass
class Composite:
    score: float | None
    technical: SideScore
    fundamental: SideScore
    technical_weight: float  # weights actually applied (after a side drops out)
    fundamental_weight: float
    coverage: float
    confidence: ConfidenceLevel | None
    confidence_reason: str
    readings: list[Reading]
    notes: list[str] = field(default_factory=list)


def reading_weight(o: _Obs, cfg: ScoringConfig) -> float:
    if o.key in cfg.info_only:
        return 0.0
    w = cfg.reading_weights.get(o.key, 1.0)
    if o.minor:
        w *= cfg.minor_weight
    if o.direction == "neutral":
        w *= cfg.neutral_weight
    return w


def sub_score(readings: Iterable[Reading]) -> float | None:
    """50 + 50 × Σ(sign × w) / Σ(w); None when nothing in the category is scored."""
    rs = [r for r in readings if r.weight > 0]
    total = sum(r.weight for r in rs)
    if total <= 0:
        return None
    net = sum(SIGN[r.direction] * r.weight for r in rs)
    return 50 + 50 * net / total


def _categories(
    readings: list[Reading], weights: Mapping[str, float], exempt: Iterable[str] = ()
) -> tuple[float | None, float, list[SubScore], dict[str, float]]:
    """(score, coverage, sub-scores, per-category share of the score) for one pool of readings.

    Categories in `exempt` don't count toward coverage when they have no data."""
    subs: list[SubScore] = []
    shares: dict[str, float] = {}
    have_w = 0.0
    expected_w = 0.0
    acc = 0.0
    for cat, w in weights.items():
        if w <= 0:
            continue
        pool = [r for r in readings if r.category == cat]
        s = sub_score(pool)
        scored = [r for r in pool if r.weight > 0]
        subs.append(
            SubScore(
                cat,
                None if s is None else round(s, 1),
                w,
                sum(r.direction == "bullish" for r in scored),
                sum(r.direction == "bearish" for r in scored),
                sum(r.direction == "neutral" for r in scored),
            )
        )
        if s is None and cat in exempt:
            continue
        expected_w += w
        if s is not None:
            have_w += w
            acc += w * s
            shares[cat] = w
    if have_w <= 0:
        return None, 0.0, subs, {}
    return acc / have_w, have_w / expected_w, subs, {k: v / have_w for k, v in shares.items()}


def _assign_points(
    readings: list[Reading], shares: Mapping[str, float], scale: float
) -> dict[int, float]:
    """Points each reading adds to a score worth `scale` composite points per score point."""
    out: dict[int, float] = {}
    for cat, share in shares.items():
        pool = [r for r in readings if r.category == cat and r.weight > 0]
        total = sum(r.weight for r in pool)
        for r in pool:
            out[id(r)] = scale * share * 50 * SIGN[r.direction] * r.weight / total
    return out


def timeframe_weights(intervals: list[str], primary: float) -> list[float]:
    if len(intervals) <= 1:
        return [1.0] * len(intervals)
    rest = (1 - primary) / (len(intervals) - 1)
    return [primary] + [rest] * (len(intervals) - 1)


@dataclass
class _Scored:
    side: SideScore
    readings: list[Reading]
    # per reading id: points per unit of side weight (multiplied by the side's weight later)
    points: dict[int, float]


def score_technical(rep: TechnicalReport, cfg: ScoringConfig) -> _Scored:
    weights: dict[str, float] = {str(k): v for k, v in cfg.technical_weights.items()}
    tfs = rep.timeframes
    tf_w = timeframe_weights([t.interval for t in tfs], cfg.primary_timeframe_weight)
    multi = len(tfs) > 1
    merged: dict[tuple[str, str], Reading] = {}
    tf_scores: list[TimeframeScore] = []
    per_tf: list[tuple[list[Reading], dict[str, float], float, float | None]] = []
    for tf, w in zip(tfs, tf_w, strict=True):
        pool: list[Reading] = []
        for o in tf.analysis.observations + rep.context.observations:
            r = Reading(
                "technical",
                o.key,
                o.category,
                o.direction,
                o.text,
                o.minor,
                reading_weight(o, cfg),
            )
            pool.append(r)
        score, cov, tf_subs, shares = _categories(pool, weights)
        tf_scores.append(
            TimeframeScore(tf.interval, None if score is None else round(score, 1), cov, w, tf_subs)
        )
        per_tf.append((pool, shares, w, score))

    have = sum(w for _, _, w, s in per_tf if s is not None)
    readings: list[Reading] = []
    points: dict[int, float] = {}
    for (pool, shares, w, s), tf in zip(per_tf, tfs, strict=True):
        pts = _assign_points(pool, shares, w / have) if s is not None and have > 0 else {}
        for r in pool:
            # The same daily-context reading appears in every timeframe's pool: merge it.
            k = (r.key, r.text)
            if k not in merged:
                merged[k] = r
                readings.append(r)
                points[id(r)] = 0.0
            m = merged[k]
            if multi and tf.interval not in m.timeframes:
                m.timeframes.append(tf.interval)
            points[id(m)] += pts.get(id(r), 0.0)
    score = sum(w * s for _, _, w, s in per_tf if s is not None) / have if have > 0 else None
    coverage = sum(t.coverage * t.weight for t in tf_scores)
    # Category view across timeframes (for display): weight-averaged sub-scores.
    subs: list[SubScore] = []
    for cat, cw in weights.items():
        if cw <= 0:
            continue
        vals = [
            (t.weight, s)
            for t in tf_scores
            for s in t.subscores
            if s.category == cat and s.score is not None
        ]
        tot = sum(w for w, _ in vals)
        avg = sum(w * s.score for w, s in vals if s.score is not None) / tot if tot else None
        first = [s for t in tf_scores for s in t.subscores if s.category == cat]
        subs.append(
            SubScore(
                cat,
                None if avg is None else round(avg, 1),
                cw,
                max((s.bullish for s in first), default=0),
                max((s.bearish for s in first), default=0),
                max((s.neutral for s in first), default=0),
            )
        )
    notes = []
    for t in rep.timeframes:
        if t.freshness.status != "fresh":
            notes.append(f"{TF_LABEL.get(t.interval, t.interval)} prices: {t.freshness.reason}")
    side = SideScore(
        None if score is None else round(score, 1), round(coverage, 3), subs, tf_scores, True, notes
    )
    return _Scored(side, readings, points)


def score_fundamental(rep: FundamentalReport, cfg: ScoringConfig) -> _Scored:
    applicable = rep.applicable
    readings = [
        Reading(
            "fundamental", o.key, o.category, o.direction, o.text, o.minor, reading_weight(o, cfg)
        )
        for o in rep.observations
    ]
    exempt = cfg.financial_exempt if rep.is_financial else []
    score, cov, subs, shares = _categories(
        readings, {str(k): v for k, v in cfg.fundamental_weights.items()}, exempt
    )
    pts = _assign_points(readings, shares, 1.0) if score is not None else {}
    notes = []
    if rep.freshness.status != "fresh":
        notes.append(f"Fundamentals: {rep.freshness.reason}")
    side = SideScore(
        None if score is None else round(score, 1),
        round(cov, 3),
        subs,
        applicable=applicable,
        notes=notes,
    )
    return _Scored(side, readings, {id(r): pts.get(id(r), 0.0) for r in readings})


def confidence_of(coverage: float, stale: bool, cfg: Confidence) -> tuple[ConfidenceLevel, str]:
    if coverage >= cfg.high_min_coverage:
        level: ConfidenceLevel = "high"
    elif coverage >= cfg.medium_min_coverage:
        level = "medium"
    else:
        level = "low"
    reason = f"{coverage * 100:.0f}% of the score's inputs had data"
    order: list[ConfidenceLevel] = ["low", "medium", "high"]
    if stale and order.index(level) > order.index(cfg.stale_caps_at):
        level = cfg.stale_caps_at
        reason += f"; capped at {level} because some data is stale"
    return level, reason


def composite(
    tech_rep: TechnicalReport,
    fund_rep: FundamentalReport,
    technical_weight: float,
    scoring: ScoringConfig,
    conf: Confidence,
) -> Composite:
    """Style-weighted blend. A side with no score drops out (its weight moves to the other) and
    lowers coverage; fundamentals that don't apply at all (ETFs, indices) don't lower it."""
    t = score_technical(tech_rep, scoring)
    f = score_fundamental(fund_rep, scoring)
    tw, fw = technical_weight, 1 - technical_weight
    ts, fs = t.side.score, f.side.score
    notes: list[str] = []
    if not f.side.applicable:
        coverage = t.side.coverage
        eff_t, eff_f = 1.0, 0.0
        if fw > 0:
            notes.append(
                "Fundamentals don't apply here, so the composite is the technical score alone."
            )
    else:
        coverage = tw * t.side.coverage + fw * f.side.coverage
        eff_t, eff_f = tw, fw
        if ts is None and fs is not None:
            eff_t, eff_f = 0.0, 1.0
            if tw > 0:
                notes.append("No technical score (no usable price history): fundamentals alone.")
        elif fs is None and ts is not None:
            eff_t, eff_f = 1.0, 0.0
            if fw > 0:
                notes.append("No fundamental score (no usable fundamentals): technicals alone.")
    if (eff_t > 0 and ts is None) or (eff_f > 0 and fs is None):
        score = None
    else:
        score = eff_t * (ts or 0.0) + eff_f * (fs or 0.0)
    readings: list[Reading] = []
    for scored, w in ((t, eff_t), (f, eff_f)):
        for r in scored.readings:
            r.points = round(scored.points.get(id(r), 0.0) * w, 2)
            readings.append(r)
    stale = bool(t.side.notes) or bool(f.side.notes and f.side.applicable)
    if score is None:
        level, reason = None, "No score: not enough data"
    else:
        level, reason = confidence_of(coverage, stale, conf)
    return Composite(
        None if score is None else round(score, 1),
        t.side,
        f.side,
        eff_t,
        eff_f,
        round(coverage, 3),
        level,
        reason,
        readings,
        notes,
    )


def top_reasons(readings: list[Reading], n: int = 3) -> tuple[list[Reading], list[Reading]]:
    """Top n bullish and bearish readings by the points they move the composite."""
    bull = sorted((r for r in readings if r.points > 0), key=lambda r: -r.points)[:n]
    bear = sorted((r for r in readings if r.points < 0), key=lambda r: r.points)[:n]
    return bull, bear
