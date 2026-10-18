"""Find the real header row in a messy export and map its columns to canonical fields.

Brokers (Groww, Zerodha Kite, ...) name columns differently and rename them from time to time, so
each field has several known aliases and headers are matched fuzzily. If the required fields can't
all be found, the caller asks the user to map them by hand; that mapping is remembered by the header
row's signature.
"""

import hashlib
import re
from dataclasses import dataclass, field

from rapidfuzz import fuzz

from app.core.profiles import ImportConfig
from app.importers.tabular import Grid, cell_text


@dataclass(frozen=True)
class FieldSpec:
    key: str
    label: str
    aliases: tuple[str, ...]
    required: bool = False
    # A required field also counts as present when this field is mapped (Kite has no name column,
    # only the trading symbol).
    fallback: str | None = None


STOCK_FIELDS: tuple[FieldSpec, ...] = (
    FieldSpec(
        "name",
        "Stock name",
        (
            "stock name",
            "company name",
            "company",
            "name",
            "security name",
            "scrip name",
            "instrument",
            "stock",
        ),
        True,
        fallback="symbol",
    ),
    FieldSpec("isin", "ISIN", ("isin", "isin code", "isin number")),
    FieldSpec(
        "symbol",
        "Symbol / ticker",
        ("symbol", "ticker", "nse symbol", "trading symbol", "tradingsymbol", "scrip code"),
    ),
    FieldSpec(
        "quantity",
        "Quantity",
        (
            "quantity",
            "qty",
            "shares",
            "no of shares",
            "quantity available",
            "holding quantity",
            "total quantity",
            "net qty",
        ),
        True,
    ),
    FieldSpec(
        "avg_price",
        "Average buy price",
        (
            "average buy price",
            "avg buy price",
            "average price",
            "avg price",
            "avg cost",
            "average cost",
            "buy avg",
            "buy price",
            "avg cost price",
        ),
        True,
    ),
    FieldSpec(
        "invested",
        "Buy value",
        (
            "buy value",
            "invested value",
            "invested amount",
            "investment value",
            "invested",
            "cost value",
        ),
    ),
    FieldSpec(
        "close_price",
        "Closing price / LTP",
        (
            "closing price",
            "close price",
            "previous closing price",
            "prev close",
            "ltp",
            "last traded price",
            "last price",
            "current price",
            "market price",
        ),
    ),
    FieldSpec(
        "current_value",
        "Closing value",
        ("closing value", "current value", "market value", "present value", "value"),
    ),
    FieldSpec(
        "unrealised_pnl",
        "Unrealised P&L",
        (
            "unrealised p&l",
            "unrealized p&l",
            "unrealised pnl",
            "p&l",
            "pnl",
            "profit/loss",
            "gain/loss",
            "returns",
        ),
    ),
    FieldSpec(
        "purchase_date",
        "Purchase date",
        ("purchase date", "buy date", "date of purchase", "acquisition date"),
    ),
)

MF_FIELDS: tuple[FieldSpec, ...] = (
    FieldSpec(
        "scheme_name",
        "Scheme name",
        # Kite puts the scheme name in its "Symbol" column.
        ("scheme name", "fund name", "scheme", "fund", "mutual fund", "name", "symbol"),
        True,
    ),
    FieldSpec("amc", "AMC", ("amc", "amc name", "fund house")),
    FieldSpec(
        "category", "Category", ("category", "sub-category", "sub category", "scheme category")
    ),
    FieldSpec("folio", "Folio number", ("folio no", "folio number", "folio")),
    FieldSpec("isin", "ISIN", ("isin", "isin code")),
    FieldSpec("amfi_code", "AMFI scheme code", ("amfi code", "scheme code", "amfi")),
    FieldSpec(
        "units",
        "Units",
        (
            "units",
            "balance units",
            "unit balance",
            "closing units",
            "quantity available",
            "quantity",
        ),
        True,
    ),
    FieldSpec(
        "avg_nav",
        "Average buy NAV",
        ("average nav", "avg nav", "average price", "avg price", "average cost", "avg cost"),
    ),
    FieldSpec(
        "invested",
        "Invested value",
        (
            "invested value",
            "invested amount",
            "investment",
            "cost value",
            "amount invested",
            "invested",
            "purchase value",
        ),
    ),
    FieldSpec(
        "current_value",
        "Current value",
        ("current value", "market value", "valuation", "present value", "value"),
    ),
    FieldSpec(
        "nav",
        "NAV",
        ("nav", "current nav", "latest nav", "previous closing price", "closing price", "ltp"),
    ),
    FieldSpec(
        "purchase_date",
        "First purchase date",
        ("purchase date", "first purchase date", "investment date", "start date"),
    ),
)

# Screener.in screen exports: the user picks the columns, so everything but the name is optional.
# Values keep Screener's units (₹ crore, percent).
SCREENER_FIELDS: tuple[FieldSpec, ...] = (
    FieldSpec("name", "Company name", ("name", "company", "company name"), True),
    FieldSpec("nse_code", "NSE code", ("nse code", "nse symbol", "symbol")),
    FieldSpec("bse_code", "BSE code", ("bse code",)),
    FieldSpec("cmp", "Current price", ("cmp rs", "cmp", "current price")),
    FieldSpec("pe", "P/E", ("p/e", "pe", "price to earning", "stock p/e")),
    FieldSpec(
        "market_cap_cr",
        "Market cap (₹ Cr)",
        ("mar cap rs cr", "market cap", "market capitalization", "mar cap"),
    ),
    FieldSpec("div_yield_pct", "Dividend yield %", ("div yld %", "dividend yield", "div yld")),
    FieldSpec("roce_pct", "ROCE %", ("roce %", "roce", "return on capital employed")),
    FieldSpec("roe_pct", "ROE %", ("roe %", "roe", "return on equity")),
    FieldSpec("debt_to_equity", "Debt / equity", ("debt / eq", "debt to equity", "debt/eq", "d/e")),
    FieldSpec(
        "promoter_pct",
        "Promoter holding %",
        ("prom hold %", "promoter holding", "promoter holding %", "prom hold"),
    ),
    FieldSpec(
        "promoter_change_pct",
        "Change in promoter holding",
        (
            "chg in prom hold %",
            "change in promoter holding",
            "chg in promoter holding",
            "prom hold chg",
        ),
    ),
    FieldSpec(
        "pledge_pct", "Pledged %", ("pledged %", "pledged percentage", "pledge %", "pledged")
    ),
    FieldSpec("fii_pct", "FII holding %", ("fii hold %", "fii holding", "fii hold")),
    FieldSpec(
        "fii_change_pct",
        "Change in FII holding",
        ("chg in fii hold %", "change in fii holding", "fii hold chg"),
    ),
    FieldSpec("dii_pct", "DII holding %", ("dii hold %", "dii holding", "dii hold")),
    FieldSpec(
        "dii_change_pct",
        "Change in DII holding",
        ("chg in dii hold %", "change in dii holding", "dii hold chg"),
    ),
    FieldSpec(
        "sales_growth_3y_pct",
        "Sales growth 3y %",
        ("sales var 3yrs %", "sales growth 3years", "sales growth 3y"),
    ),
    FieldSpec(
        "profit_growth_3y_pct",
        "Profit growth 3y %",
        ("profit var 3yrs %", "profit growth 3years", "profit growth 3y"),
    ),
    FieldSpec(
        "sales_growth_5y_pct",
        "Sales growth 5y %",
        ("sales var 5yrs %", "sales growth 5years", "sales growth 5y"),
    ),
    FieldSpec(
        "profit_growth_5y_pct",
        "Profit growth 5y %",
        ("profit var 5yrs %", "profit growth 5years", "profit growth 5y"),
    ),
    FieldSpec(
        "qtr_sales_var_pct",
        "Quarterly sales growth %",
        ("qtr sales var %", "yoy quarterly sales growth"),
    ),
    FieldSpec(
        "qtr_profit_var_pct",
        "Quarterly profit growth %",
        ("qtr profit var %", "yoy quarterly profit growth"),
    ),
    FieldSpec("opm_pct", "Operating margin %", ("opm %", "opm", "operating profit margin")),
    FieldSpec(
        "interest_coverage",
        "Interest coverage",
        ("int coverage", "interest coverage ratio", "interest coverage"),
    ),
    FieldSpec("current_ratio", "Current ratio", ("current ratio",)),
)

FUND_PORTFOLIO_FIELDS: tuple[FieldSpec, ...] = (
    FieldSpec(
        "name",
        "Company / instrument",
        (
            "name of the instrument",
            "name of instrument",
            "company name",
            "company",
            "issuer",
            "security name",
            "instrument",
            "stock name",
            "holding",
            "name",
        ),
        True,
    ),
    FieldSpec("isin", "ISIN", ("isin", "isin code")),
    FieldSpec(
        "weight_pct",
        "% of net assets",
        (
            "% to net assets",
            "% to nav",
            "% of net assets",
            "% to aum",
            "% of aum",
            "weight",
            "weightage",
            "holding %",
            "% holding",
            "allocation",
            "% allocation",
        ),
        True,
    ),
)

FIELDS = {
    "stocks": STOCK_FIELDS,
    "mf": MF_FIELDS,
    "screener": SCREENER_FIELDS,
    "fund_portfolio": FUND_PORTFOLIO_FIELDS,
}


def normalise_header(text: str) -> str:
    t = text.lower().replace("₹", "").replace("(rs)", "").replace("(inr)", "")
    t = re.sub(r"[()\[\]._:*]", " ", t)
    return " ".join(t.split())


@dataclass
class MappingResult:
    header_row: int  # 0-based index into the grid
    headers: list[str]
    mapping: dict[str, int]  # field key → column index
    scores: dict[str, float] = field(default_factory=dict)
    missing_required: list[str] = field(default_factory=list)

    @property
    def complete(self) -> bool:
        return not self.missing_required


def header_signature(kind: str, headers: list[str]) -> str:
    joined = "|".join(normalise_header(h) for h in headers if h)
    return hashlib.sha1(f"{kind}:{joined}".encode()).hexdigest()


def _match_row(
    headers: list[str], specs: tuple[FieldSpec, ...], min_score: float
) -> tuple[dict[str, int], dict[str, float]]:
    """Greedy assignment of columns to fields, best scores first, each column used once."""
    candidates: list[tuple[float, int, str]] = []
    for col, h in enumerate(headers):
        nh = normalise_header(h)
        if not nh:
            continue
        for spec in specs:
            score = max(
                100.0 if nh == alias else float(fuzz.ratio(nh, alias)) for alias in spec.aliases
            )
            if score >= min_score:
                # Earlier specs win ties (e.g. "name" before generic aliases).
                candidates.append((score, col, spec.key))
    order = {s.key: i for i, s in enumerate(specs)}
    candidates.sort(key=lambda c: (-c[0], order[c[2]], c[1]))
    mapping: dict[str, int] = {}
    scores: dict[str, float] = {}
    used: set[int] = set()
    for score, col, key in candidates:
        if key in mapping or col in used:
            continue
        mapping[key], scores[key] = col, round(score, 1)
        used.add(col)
    return mapping, scores


def _missing(kind: str, mapping: dict[str, int]) -> list[str]:
    return [
        s.key
        for s in FIELDS[kind]
        if s.required and s.key not in mapping and not (s.fallback and s.fallback in mapping)
    ]


def detect(grid: Grid, kind: str, cfg: ImportConfig) -> MappingResult:
    """Scan the top of the file for the row that looks most like the holdings header."""
    specs = FIELDS[kind]
    required = [s.key for s in specs if s.required]
    best: MappingResult | None = None
    best_rank = (-1, -1)
    for idx, row in enumerate(grid[: cfg.header_scan_rows]):
        headers = [cell_text(c) for c in row]
        if sum(1 for h in headers if h) < 2:
            continue
        mapping, scores = _match_row(headers, specs, cfg.column_match_min_score)
        rank = (len(required) - len(_missing(kind, mapping)), len(mapping))
        if rank > best_rank:
            best_rank = rank
            best = MappingResult(idx, headers, mapping, scores)
    if best is None or len(best.mapping) < cfg.min_header_matches:
        # No convincing header: guess the first row with several text cells and ask the user.
        guess = next(
            (
                i
                for i, r in enumerate(grid[: cfg.header_scan_rows])
                if sum(1 for c in r if isinstance(c, str) and c.strip()) >= 3
            ),
            0,
        )
        headers = [cell_text(c) for c in grid[guess]] if grid else []
        mapping = best.mapping if best and best.header_row == guess else {}
        best = MappingResult(guess, headers, mapping, best.scores if best else {})
    best.missing_required = _missing(kind, best.mapping)
    return best


# Sheet titles that hint at what a multi-sheet workbook (e.g. Kite: Equity / Mutual Funds /
# Combined) keeps on each sheet.
_SHEET_HINTS = {
    "stocks": ("equity", "stock", "share"),
    "mf": ("mutual", "fund", "mf"),
}
_MIXED_SHEETS = ("combined", "summary")


def _sheet_hint(kind: str, title: str) -> int:
    t = title.lower()
    if any(w in t for w in _MIXED_SHEETS):
        return -1
    if any(w in t for w in _SHEET_HINTS.get(kind, ())):
        return 1
    if any(w in t for k, words in _SHEET_HINTS.items() if k != kind for w in words):
        return -2
    return 0


def pick_sheet(sheets: list[tuple[str, Grid]], kind: str, cfg: ImportConfig) -> Grid:
    """The sheet whose header best fits `kind`; ties go to the sheet named for it, then size."""
    if len(sheets) == 1:
        return sheets[0][1]

    def rank(sheet: tuple[str, Grid]) -> tuple[int, int, int, int]:
        title, grid = sheet
        m = detect(grid, kind, cfg)
        found = len(FIELDS[kind]) - len(m.missing_required)
        return (found, _sheet_hint(kind, title), len(m.mapping), len(grid))

    return max(sheets, key=rank, default=("", []))[1]


def manual(grid: Grid, kind: str, header_row: int, mapping: dict[str, int]) -> MappingResult:
    """Build a MappingResult from a user-supplied mapping, validating it."""
    if not 0 <= header_row < len(grid):
        raise ValueError(f"Header row {header_row + 1} is outside the file")
    headers = [cell_text(c) for c in grid[header_row]]
    keys = {s.key for s in FIELDS[kind]}
    unknown = set(mapping) - keys
    if unknown:
        raise ValueError(f"Unknown fields: {sorted(unknown)}")
    for k, col in mapping.items():
        if not 0 <= col < len(headers):
            raise ValueError(f"Column {col} for '{k}' is outside the header row")
    if len(set(mapping.values())) != len(mapping):
        raise ValueError("The same column is mapped to two fields")
    result = MappingResult(header_row, headers, dict(mapping))
    result.missing_required = _missing(kind, mapping)
    return result
