"""A fake company in yfinance's shapes: statements as DataFrames (rows × period columns), ₹."""

from datetime import date

import pandas as pd

CR = 1e7
YEARS = [date(2023, 3, 31), date(2024, 3, 31), date(2025, 3, 31), date(2026, 3, 31)]
QUARTERS = [
    date(2025, 6, 30),
    date(2025, 9, 30),
    date(2025, 12, 31),
    date(2026, 3, 31),
    date(2026, 6, 30),
]


def _df(rows: dict[str, list[float | None]], cols: list[date]) -> pd.DataFrame:
    # yfinance puts the newest period first
    data = {
        name: [None if v is None else v * CR for v in vals][::-1] for name, vals in rows.items()
    }
    return pd.DataFrame(data, index=[pd.Timestamp(c) for c in cols][::-1]).T


INCOME = {
    "Total Revenue": [1000, 1100, 1210, 1331],  # 10% growth
    "Gross Profit": [400, 450, 500, 560],
    "Operating Income": [150, 170, 190, 220],
    "EBIT": [160, 180, 200, 230],
    "EBITDA": [200, 225, 250, 285],
    "Interest Expense": [20, 20, 20, 23],
    "Pretax Income": [140, 160, 180, 207],
    "Net Income Common Stockholders": [100, 115, 130, 150],
}
BALANCE = {
    "Total Assets": [1500, 1600, 1700, 1800],
    "Current Assets": [600, 650, 700, 760],
    "Current Liabilities": [400, 420, 440, 450],
    "Total Debt": [300, 280, 260, 250],
    "Long Term Debt": [200, 190, 180, 170],
    "Stockholders Equity": [800, 900, 1000, 1100],
    "Cash And Cash Equivalents": [100, 110, 120, 50],
}
CASHFLOW = {
    "Operating Cash Flow": [120, 140, 150, 180],
    "Capital Expenditure": [-40, -50, -60, -70],
    "Cash Dividends Paid": [-30, -35, -40, -45],
}
QUARTERLY = {
    "Total Revenue": [320, 330, 340, 341, 368],  # Jun 2026 vs Jun 2025: +15%
    "Net Income Common Stockholders": [35, 37, 38, 40, 42],
}


def statements_frames() -> dict[str, pd.DataFrame]:
    bal = _df(BALANCE, YEARS)
    bal.loc["Ordinary Shares Number"] = 1e8  # 10 crore shares: a count, not ₹
    return {
        "info": {
            "sector": "Industrials",
            "sharesOutstanding": 1e8,
            "marketCap": 3000 * CR,
            "financialCurrency": "INR",
            "longName": "Fake Industries Ltd",
            "trailingPE": 19.5,
            "priceToBook": 2.7,
        },
        "income_stmt": _df(INCOME, YEARS),
        "balance_sheet": bal,
        "cashflow": _df(CASHFLOW, YEARS),
        "quarterly_income_stmt": _df(QUARTERLY, QUARTERS),
    }


def fake_fund_download(frames: dict[str, object] | None = None):  # type: ignore[no-untyped-def]
    frames = frames or statements_frames()
    calls: list[str] = []

    def dl(ticker: str, what: str) -> object:
        calls.append(f"{ticker}:{what}")
        return frames[what]

    dl.calls = calls  # type: ignore[attr-defined]
    return dl
