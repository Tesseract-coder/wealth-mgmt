"""Resolve a mutual fund holding to its AMFI scheme code.

Order: manual override → AMFI code → ISIN → scheme name (fuzzy, constrained by plan and option).
"""

import re
from dataclasses import dataclass, field

from rapidfuzz import fuzz, process

from app.core.profiles import ImportConfig
from app.data.amfi import Scheme, detect_option, detect_plan

_NOISE = re.compile(
    r"\b(direct|regular|plan|option|growth|idcw|dividend|payout|reinvestment|reinvest|"
    r"cumulative|income distribution cum capital withdrawal|fund|scheme|the)\b"
)
_ALIASES = [
    (re.compile(r"\btax saver\b|\btax saving\b|\blong term equity\b"), "elss"),
    (re.compile(r"\bmid cap\b|\bmid-cap\b"), "midcap"),
    (re.compile(r"\bsmall cap\b|\bsmall-cap\b"), "smallcap"),
    (re.compile(r"\blarge cap\b|\blarge-cap\b"), "largecap"),
    (re.compile(r"\bflexi cap\b|\bflexi-cap\b"), "flexicap"),
    (re.compile(r"\bmulti cap\b|\bmulti-cap\b"), "multicap"),
]


def normalise_scheme(name: str) -> str:
    n = name.lower().replace("&", " and ")
    for pattern, repl in _ALIASES:
        n = pattern.sub(repl, n)
    n = re.sub(r"[^a-z0-9 ]", " ", n)
    n = _NOISE.sub(" ", n)
    words = n.split()
    # "elss elss" after alias substitution of "ELSS Tax Saver"
    deduped = [w for i, w in enumerate(words) if i == 0 or w != words[i - 1]]
    return " ".join(deduped)


@dataclass
class SchemeSuggestion:
    amfi_code: str
    name: str
    score: float


@dataclass
class SchemeResolution:
    scheme: Scheme | None
    method: str  # "override" | "amfi_code" | "isin" | "name" | "unresolved"
    score: float | None = None
    suggestions: list[SchemeSuggestion] = field(default_factory=list)


def scheme_override_key(name: str) -> str:
    plan = detect_plan(name) or "-"
    option = detect_option(name) or "-"
    return f"name:{normalise_scheme(name)}|{plan}|{option}"


class SchemeResolver:
    def __init__(
        self,
        schemes: tuple[Scheme, ...],
        cfg: ImportConfig,
    ) -> None:
        self.cfg = cfg
        self.schemes = schemes
        self.by_code = {s.code: s for s in schemes}
        self.by_isin: dict[str, Scheme] = {}
        for s in schemes:
            for i in (s.isin_growth, s.isin_reinvest):
                if i:
                    self.by_isin.setdefault(i, s)
        self._norm = [normalise_scheme(s.name) for s in schemes]

    def direct_twin(self, scheme: Scheme) -> Scheme | None:
        """The Direct plan of a Regular scheme: same AMC, same option, same normalised name."""
        if scheme.plan != "regular":
            return None
        target = normalise_scheme(scheme.name)
        for s, n in zip(self.schemes, self._norm, strict=True):
            if (
                n == target
                and s.plan == "direct"
                and s.option == scheme.option
                and (s.amc == scheme.amc or not s.amc or not scheme.amc)
                and s.code != scheme.code
            ):
                return s
        return None

    def _candidates(self, plan: str | None, option: str | None) -> dict[int, str]:
        """Indices of schemes compatible with the requested plan/option (unknown = compatible)."""
        return {
            i: self._norm[i]
            for i, s in enumerate(self.schemes)
            if (plan is None or s.plan in (plan, None))
            and (option is None or s.option in (option, None))
        }

    def search(self, query: str, limit: int) -> list[SchemeSuggestion]:
        q = query.strip()
        if not q:
            return []
        if q.isdigit() and q in self.by_code:
            s = self.by_code[q]
            return [SchemeSuggestion(s.code, s.name, 100.0)]
        cands = self._candidates(detect_plan(q), detect_option(q))
        return [
            SchemeSuggestion(self.schemes[i].code, self.schemes[i].name, round(float(sc), 1))
            for _, sc, i in process.extract(
                normalise_scheme(q), cands, scorer=fuzz.token_set_ratio, limit=limit
            )
        ]

    def resolve(
        self,
        name: str,
        isin: str | None = None,
        amfi_code: str | None = None,
        overrides: dict[str, str] | None = None,
    ) -> SchemeResolution:
        """overrides: key -> AMFI code, from the SchemeOverride table."""
        key = scheme_override_key(name)
        if overrides and key in overrides and (s := self.by_code.get(overrides[key])):
            return SchemeResolution(s, "override", 100.0)
        if amfi_code and (s := self.by_code.get(str(amfi_code).strip())):
            return SchemeResolution(s, "amfi_code", 100.0)
        if isin and (s := self.by_isin.get(isin.strip().upper())):
            return SchemeResolution(s, "isin", 100.0)

        norm = normalise_scheme(name)
        if not norm:
            return SchemeResolution(None, "unresolved")
        plan, option = detect_plan(name), detect_option(name)
        cands = self._candidates(plan, option)
        # token_sort penalises extra words ("Nifty 50" vs "Nifty Next 50"), unlike token_set.
        matches = process.extract(
            norm, cands, scorer=fuzz.token_sort_ratio, limit=self.cfg.max_suggestions * 3
        )

        def rank(m: tuple[str, float, int]) -> tuple[float, int]:
            s = self.schemes[m[2]]
            # Among equal scores prefer schemes whose plan/option are known and match.
            exact = int(s.plan == plan and plan is not None) + int(
                s.option == option and option is not None
            )
            return (m[1], exact)

        matches.sort(key=rank, reverse=True)
        best_sc = matches[0][1] if matches else 0.0
        if best_sc >= self.cfg.scheme_name_auto_accept and plan is not None and option is not None:
            # Without a known plan and option the name alone can't pick one variant safely.
            return SchemeResolution(
                self.schemes[matches[0][2]],
                "name",
                round(float(best_sc), 1),
                self._suggest(matches, []),
            )
        # Renamed schemes ("HDFC Mid-Cap Opportunities" → "HDFC Mid Cap Fund") score poorly on
        # token_sort; add token_set matches so the right fund still appears as a suggestion.
        loose = process.extract(
            norm, cands, scorer=fuzz.token_set_ratio, limit=self.cfg.max_suggestions
        )
        return SchemeResolution(None, "unresolved", None, self._suggest(matches, loose))

    def _suggest(self, *match_lists: list[tuple[str, float, int]]) -> list[SchemeSuggestion]:
        best: dict[int, float] = {}
        for matches in match_lists:
            for _, sc, i in matches:
                if sc >= self.cfg.scheme_name_suggest:
                    best[i] = max(best.get(i, 0.0), float(sc))
        ranked = sorted(best.items(), key=lambda kv: kv[1], reverse=True)
        return [
            SchemeSuggestion(self.schemes[i].code, self.schemes[i].name, round(sc, 1))
            for i, sc in ranked[: self.cfg.max_suggestions]
        ]
