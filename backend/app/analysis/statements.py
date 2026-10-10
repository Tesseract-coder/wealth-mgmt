"""Source-independent financial statements, in ₹ crore.

Yahoo Finance and Screener.in label line items differently and use different units; both are
converted into one table per period with the canonical columns below. Analysis code only ever
sees this shape. A missing line item is NaN, never zero.
"""

from dataclasses import dataclass, field
from datetime import date
from typing import Any

import numpy as np
import pandas as pd

CRORE = 1e7

# canonical field → description (used in docs and "not available" messages)
FIELDS: dict[str, str] = {
    "revenue": "Revenue",
    "gross_profit": "Gross profit",
    "operating_income": "Operating profit (EBIT before other income)",
    "ebit": "EBIT",
    "ebitda": "EBITDA",
    "interest_expense": "Interest expense",
    "pretax_income": "Profit before tax",
    "net_income": "Net profit",
    "depreciation": "Depreciation",
    "total_assets": "Total assets",
    "current_assets": "Current assets",
    "current_liabilities": "Current liabilities",
    "total_debt": "Total debt",
    "long_term_debt": "Long-term debt",
    "equity": "Shareholders' equity",
    "cash": "Cash and equivalents",
    "shares": "Shares outstanding",  # count, not ₹ crore
    "operating_cash_flow": "Cash from operations",
    "capex": "Capital expenditure",  # positive number = money spent
    "free_cash_flow": "Free cash flow",
    "dividends_paid": "Dividends paid",  # positive number = cash paid out
}

# Yahoo row names, in order of preference.
YAHOO_ROWS: dict[str, tuple[str, ...]] = {
    "revenue": ("Total Revenue", "Operating Revenue"),
    "gross_profit": ("Gross Profit",),
    "operating_income": ("Operating Income",),
    "ebit": ("EBIT",),
    "ebitda": ("EBITDA", "Normalized EBITDA"),
    "interest_expense": ("Interest Expense", "Interest Expense Non Operating"),
    "pretax_income": ("Pretax Income",),
    "net_income": (
        "Net Income Common Stockholders",
        "Net Income",
        "Net Income From Continuing Operation Net Minority Interest",
    ),
    "depreciation": ("Reconciled Depreciation", "Depreciation And Amortization"),
    "total_assets": ("Total Assets",),
    "current_assets": ("Current Assets",),
    "current_liabilities": ("Current Liabilities",),
    "total_debt": ("Total Debt",),
    "long_term_debt": ("Long Term Debt", "Long Term Debt And Capital Lease Obligation"),
    "equity": ("Stockholders Equity", "Common Stock Equity"),
    "cash": ("Cash And Cash Equivalents", "Cash Cash Equivalents And Short Term Investments"),
    "shares": ("Ordinary Shares Number", "Share Issued"),
    "operating_cash_flow": (
        "Operating Cash Flow",
        "Cash Flow From Continuing Operating Activities",
    ),
    "capex": ("Capital Expenditure", "Purchase Of PPE"),
    "free_cash_flow": ("Free Cash Flow",),
    "dividends_paid": ("Cash Dividends Paid", "Common Stock Dividend Paid"),
}
NOT_MONEY = {"shares"}
OUTFLOWS = {"capex", "dividends_paid"}  # Yahoo reports these as negative cash flows


@dataclass
class Statements:
    """annual / quarterly: index = period end date (ascending), columns ⊆ FIELDS."""

    source: str  # "yahoo" | "screener"
    annual: pd.DataFrame
    quarterly: pd.DataFrame
    notes: list[str] = field(default_factory=list)

    @property
    def years(self) -> int:
        return len(self.annual)

    def latest_year(self) -> date | None:
        return self.annual.index[-1] if len(self.annual) else None


def _empty() -> pd.DataFrame:
    return pd.DataFrame(columns=list(FIELDS), dtype="float64")


def _frame(sources: list[dict[str, Any]]) -> pd.DataFrame:
    """Build a canonical frame from Yahoo statement dicts ({row: {iso date: value}})."""
    merged: dict[str, dict[str, Any]] = {}
    for src in sources:
        for row, values in (src or {}).items():
            merged.setdefault(row, values)
    dates = sorted({d for values in merged.values() for d in values})
    if not dates:
        return _empty()
    out = pd.DataFrame(
        index=[date.fromisoformat(d[:10]) for d in dates], columns=list(FIELDS), dtype="float64"
    )
    for key, candidates in YAHOO_ROWS.items():
        for d_iso, d in zip(dates, out.index, strict=True):
            for row in candidates:
                v = merged.get(row, {}).get(d_iso)
                if v is not None and not (isinstance(v, float) and np.isnan(v)):
                    x = float(v)
                    if key not in NOT_MONEY:
                        x /= CRORE
                    if key in OUTFLOWS:
                        x = abs(x)
                    out.loc[d, key] = x
                    break
    # Derive what Yahoo leaves out, but only from figures it did report.
    if out["free_cash_flow"].isna().any():
        derived = out["operating_cash_flow"] - out["capex"]
        out["free_cash_flow"] = out["free_cash_flow"].fillna(derived)
    if out["ebit"].isna().any():
        out["ebit"] = out["ebit"].fillna(out["pretax_income"] + out["interest_expense"])
    # A period where Yahoo reported nothing that matters (only an empty date column) is dropped.
    core = ["revenue", "net_income", "total_assets", "operating_cash_flow"]
    return out[out[core].notna().any(axis=1)].sort_index()


def from_yahoo(raw: dict[str, Any]) -> Statements:
    """raw = {"income": {...}, "balance": {...}, "cashflow": {...}, "quarterly_income": {...}}."""
    annual = _frame([raw.get("income") or {}, raw.get("balance") or {}, raw.get("cashflow") or {}])
    quarterly = _frame([raw.get("quarterly_income") or {}])
    return Statements("yahoo", annual, quarterly)


def from_rows(
    source: str,
    annual: dict[str, dict[str, float]],
    quarterly: dict[str, dict[str, float]],
    notes: list[str] | None = None,
) -> Statements:
    """From stored canonical rows: {iso date: {field: value in ₹ crore}}."""

    def build(rows: dict[str, dict[str, float]]) -> pd.DataFrame:
        if not rows:
            return _empty()
        df = pd.DataFrame.from_dict(rows, orient="index").reindex(columns=list(FIELDS))
        df.index = [date.fromisoformat(d) for d in df.index]
        return df.astype("float64").sort_index()

    return Statements(source, build(annual), build(quarterly), notes or [])


def fill_missing(primary: Statements, secondary: Statements, tolerance_days: int = 10) -> list[str]:
    """Fill line items that `primary` lacks entirely from `secondary`, for the same periods.

    Only whole columns are filled (e.g. Screener.in has no current assets/liabilities or capex),
    never individual gaps, so each line item still comes from one source. Returns the labels
    filled."""
    filled: list[str] = []
    a, b = primary.annual, secondary.annual
    if a.empty or b.empty:
        return filled
    for fld in FIELDS:
        if fld in a and a[fld].notna().any():
            continue
        if fld not in b or b[fld].dropna().empty:
            continue
        src = b[fld].dropna()
        values = {}
        for d in a.index:
            near = [x for x in src.index if abs((x - d).days) <= tolerance_days]
            if near:
                values[d] = float(src.loc[near[0]])
        if values:
            a[fld] = pd.Series(values, dtype="float64").reindex(a.index)
            filled.append(FIELDS[fld])
    return filled


def to_rows(df: pd.DataFrame) -> dict[str, dict[str, float]]:
    return {
        d.isoformat(): {k: float(v) for k, v in row.items() if not pd.isna(v)}
        for d, row in df.iterrows()
    }
