"""Resolve a holding to an NSE symbol: manual override → ISIN → explicit symbol → company name."""

import re
from dataclasses import dataclass, field

from rapidfuzz import fuzz, process

from app.core.profiles import ImportConfig
from app.data.nse import Security

_NOISE = re.compile(r"\b(limited|ltd|the|inc|plc|co)\b")


def normalise_company(name: str) -> str:
    n = name.lower().replace("&", " and ")
    n = re.sub(r"[^a-z0-9 ]", " ", n)
    n = _NOISE.sub(" ", n)
    return " ".join(n.split())


@dataclass
class Suggestion:
    symbol: str
    name: str
    score: float


@dataclass
class Resolution:
    symbol: str | None
    exchange: str | None
    method: str  # "override" | "isin" | "symbol" | "name" | "unresolved"
    score: float | None = None
    suggestions: list[Suggestion] = field(default_factory=list)


def override_keys(name: str, isin: str | None) -> list[str]:
    keys = [f"isin:{isin.upper()}"] if isin else []
    return [*keys, f"name:{normalise_company(name)}"]


class TickerResolver:
    def __init__(
        self,
        securities: tuple[Security, ...],
        cfg: ImportConfig,
    ) -> None:
        self.cfg = cfg
        # Prefer the EQ series when several symbols share an ISIN.
        self.by_isin: dict[str, Security] = {}
        for s in sorted(securities, key=lambda s: s.series != "EQ"):
            self.by_isin.setdefault(s.isin, s)
        self.by_symbol = {s.symbol: s for s in securities}
        self._names = {i: normalise_company(s.name) for i, s in enumerate(securities)}
        self._securities = securities

    def search(self, query: str, limit: int) -> list[Suggestion]:
        q = query.strip()
        if not q:
            return []
        out: dict[str, Suggestion] = {}
        sym = q.upper()
        if exact := self.by_symbol.get(sym):
            out[exact.symbol] = Suggestion(exact.symbol, exact.name, 100.0)
        # token_set_ratio ranks "bajaj fin" → BAJFINANCE; WRatio's partial matching prefers ETFs.
        for _, score, idx in process.extract(
            normalise_company(q), self._names, scorer=fuzz.token_set_ratio, limit=limit
        ):
            s = self._securities[idx]
            out.setdefault(s.symbol, Suggestion(s.symbol, s.name, round(float(score), 1)))
        if len(sym) >= 3:
            for s in self._securities:
                if s.symbol.startswith(sym) and s.symbol not in out:
                    out[s.symbol] = Suggestion(s.symbol, s.name, 90.0)
        return sorted(out.values(), key=lambda x: -x.score)[:limit]

    def resolve(
        self,
        name: str,
        isin: str | None,
        symbol_hint: str | None = None,
        overrides: dict[str, tuple[str, str]] | None = None,
    ) -> Resolution:
        """overrides: key -> (symbol, exchange), from the TickerOverride table."""
        for key in override_keys(name, isin):
            if overrides and key in overrides:
                sym, exch = overrides[key]
                return Resolution(sym, exch, "override", 100.0)

        if isin and (sec := self.by_isin.get(isin.strip().upper())):
            return Resolution(sec.symbol, "NSE", "isin", 100.0)

        if symbol_hint:
            hint = symbol_hint.strip().upper().removesuffix(".NS")
            if hint in self.by_symbol:
                return Resolution(hint, "NSE", "symbol", 100.0)

        norm = normalise_company(name)
        if not norm:
            return Resolution(None, None, "unresolved")
        limit = self.cfg.max_suggestions
        strict = process.extract(norm, self._names, scorer=fuzz.token_sort_ratio, limit=limit)
        if strict and strict[0][1] >= self.cfg.ticker_name_auto_accept:
            runner_up = strict[1][1] if len(strict) > 1 else 0.0
            if strict[0][1] - runner_up >= 3 or strict[0][1] == 100:
                best = self._securities[strict[0][2]]
                score = round(float(strict[0][1]), 1)
                return Resolution(best.symbol, "NSE", "name", score, self._suggest(strict))
        # Short or partial names ("HDFC") score low on token_sort; token_set still surfaces them.
        loose = process.extract(norm, self._names, scorer=fuzz.token_set_ratio, limit=limit)
        return Resolution(None, None, "unresolved", None, self._suggest(strict, loose))

    def _suggest(self, *match_lists: list[tuple[str, float, int]]) -> list[Suggestion]:
        best: dict[int, float] = {}
        for matches in match_lists:
            for _, sc, i in matches:
                if sc >= self.cfg.ticker_name_suggest:
                    best[i] = max(best.get(i, 0.0), float(sc))
        ranked = sorted(best.items(), key=lambda kv: kv[1], reverse=True)
        return [
            Suggestion(self._securities[i].symbol, self._securities[i].name, round(sc, 1))
            for i, sc in ranked[: self.cfg.max_suggestions]
        ]
