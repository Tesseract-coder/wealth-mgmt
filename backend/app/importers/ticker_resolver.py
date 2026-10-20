"""Resolve a holding to a symbol: manual override → ISIN → explicit symbol → company name.

NSE first; shares listed only on BSE resolve to their BSE symbol on exchange "BSE"."""

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
    exchange: str = "NSE"


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
        bse_only: tuple[Security, ...] = (),
        bse_isin: dict[str, str] | None = None,
    ) -> None:
        """securities: NSE's list; bse_only: shares listed only on BSE; bse_isin: every BSE code
        and BSE symbol → ISIN (so a BSE code for a share also on NSE resolves to NSE)."""
        self.cfg = cfg
        # Prefer NSE, then the EQ series, when several symbols share an ISIN.
        self.by_isin: dict[str, Security] = {}
        for s in sorted(securities, key=lambda s: s.series != "EQ"):
            self.by_isin.setdefault(s.isin, s)
        for s in bse_only:
            self.by_isin.setdefault(s.isin, s)
        self.by_symbol = {s.symbol: s for s in securities}  # NSE symbols
        self.bse_by_symbol = {s.symbol: s for s in bse_only}
        self.bse_isin = bse_isin or {}
        everything = securities + bse_only
        self._names = {i: normalise_company(s.name) for i, s in enumerate(everything)}
        self._securities = everything

    def lookup(self, ticker: str) -> Security | None:
        """The security behind a Yahoo-style ticker: "TCS.NS", "TCS", "ANDHRAPET.BO" or "500012"."""
        t = ticker.strip().upper()
        if t.endswith(".BO") or t.isdigit():
            isin = self.bse_isin.get(t.removesuffix(".BO"))
            return self.by_isin.get(isin) if isin else self.bse_by_symbol.get(t.removesuffix(".BO"))
        return self.by_symbol.get(t.removesuffix(".NS"))

    def search(self, query: str, limit: int) -> list[Suggestion]:
        q = query.strip()
        if not q:
            return []
        out: dict[str, Suggestion] = {}
        sym = q.upper()
        if exact := self.by_symbol.get(sym) or self.bse_by_symbol.get(sym) or self.lookup(sym):
            out[exact.symbol] = Suggestion(exact.symbol, exact.name, 100.0, exact.exchange)
        # token_set_ratio ranks "bajaj fin" → BAJFINANCE; WRatio's partial matching prefers ETFs.
        for _, score, idx in process.extract(
            normalise_company(q), self._names, scorer=fuzz.token_set_ratio, limit=limit
        ):
            s = self._securities[idx]
            out.setdefault(
                s.symbol, Suggestion(s.symbol, s.name, round(float(score), 1), s.exchange)
            )
        if len(sym) >= 3:
            for s in self._securities:
                if s.symbol.startswith(sym) and s.symbol not in out:
                    out[s.symbol] = Suggestion(s.symbol, s.name, 90.0, s.exchange)
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
            return Resolution(sec.symbol, sec.exchange, "isin", 100.0)

        if symbol_hint and (sec := self.lookup(symbol_hint)):
            return Resolution(sec.symbol, sec.exchange, "symbol", 100.0)

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
                return Resolution(best.symbol, best.exchange, "name", score, self._suggest(strict))
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
            Suggestion(
                self._securities[i].symbol,
                self._securities[i].name,
                round(sc, 1),
                self._securities[i].exchange,
            )
            for i, sc in ranked[: self.cfg.max_suggestions]
        ]
