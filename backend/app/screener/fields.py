"""The fields a screen can filter on. Metadata only (labels and units); thresholds live in
profiles.yaml (presets) or in your saved screens.

Technical fields come from daily bars, whatever your style, so a screen means the same thing
under every style. Scores use your style.
"""

from dataclasses import dataclass
from typing import Literal

Group = Literal["Technical", "Fundamental", "Score"]
Op = Literal["gt", "gte", "lt", "lte", "between"]
OPS: dict[str, str] = {"gt": ">", "gte": "≥", "lt": "<", "lte": "≤", "between": "between"}


@dataclass(frozen=True)
class Field:
    key: str
    label: str
    group: Group
    unit: str  # "%", "x", "₹", "₹ Cr", "pp", ""
    help: str
    financial_exempt: bool = False  # doesn't apply to lenders/insurers: they pass the filter


FIELDS: tuple[Field, ...] = (
    # Technical (daily bars)
    Field("close", "Price", "Technical", "₹", "Last daily close"),
    Field(
        "price_vs_sma50_pct",
        "Price vs 50-DMA",
        "Technical",
        "%",
        "% above (+) or below (−) the 50-day average",
    ),
    Field(
        "price_vs_sma200_pct",
        "Price vs 200-DMA",
        "Technical",
        "%",
        "% above (+) or below (−) the 200-day average",
    ),
    Field(
        "sma50_vs_sma200_pct",
        "50-DMA vs 200-DMA",
        "Technical",
        "%",
        "Positive = 50-DMA above the 200-DMA (golden-cross side)",
    ),
    Field("rsi", "RSI (14)", "Technical", "", "Relative Strength Index, 0–100"),
    Field("adx", "ADX (14)", "Technical", "", "Trend strength; above 25 is a trend"),
    Field("roc", "Rate of change (20 days)", "Technical", "%", "Price change over 20 sessions"),
    Field(
        "volume_ratio",
        "Volume vs 20-day average",
        "Technical",
        "x",
        "Latest volume ÷ 20-session average",
    ),
    Field("pct_below_52w_high", "Below 52-week high", "Technical", "%", "0 = at the high"),
    Field("pct_above_52w_low", "Above 52-week low", "Technical", "%", "0 = at the low"),
    Field(
        "rs_3m",
        "Relative strength vs Nifty 50 (3m)",
        "Technical",
        "pp",
        "Return minus Nifty 50's, 3 months",
    ),
    Field(
        "rs_6m",
        "Relative strength vs Nifty 50 (6m)",
        "Technical",
        "pp",
        "Return minus Nifty 50's, 6 months",
    ),
    Field("hist_vol", "Historical volatility", "Technical", "%", "Annualised, 20 sessions"),
    Field(
        "delivery_pct", "Delivery %", "Technical", "%", "Share of traded quantity delivered (NSE)"
    ),
    Field(
        "avg_traded_value_cr",
        "Avg daily traded value",
        "Technical",
        "₹ Cr",
        "Average close × volume",
    ),
    Field("beta", "Beta vs Nifty 50", "Technical", "", "From a year of daily returns"),
    # Fundamental
    Field("market_cap", "Market cap", "Fundamental", "₹ Cr", "Yahoo Finance"),
    Field("pe", "P/E", "Fundamental", "x", "Market cap ÷ trailing net profit"),
    Field(
        "pe_vs_sector",
        "P/E vs sector median",
        "Fundamental",
        "x",
        "1.0 = at the median; below 1 = cheaper than peers",
    ),
    Field("pb", "P/B", "Fundamental", "x", "Market cap ÷ equity"),
    Field("ev_ebitda", "EV/EBITDA", "Fundamental", "x", "Not used for financials", True),
    Field("peg", "PEG", "Fundamental", "x", "P/E ÷ profit growth"),
    Field("dividend_yield", "Dividend yield", "Fundamental", "%", "Trailing"),
    Field("roe", "ROE", "Fundamental", "%", "Return on equity"),
    Field(
        "roce",
        "ROCE",
        "Fundamental",
        "%",
        "Return on capital employed; not used for financials",
        True,
    ),
    Field("op_margin", "Operating margin", "Fundamental", "%", "Not used for financials", True),
    Field(
        "op_margin_change",
        "Operating margin change (3y)",
        "Fundamental",
        "pp",
        "Positive = improving",
        True,
    ),
    Field("net_margin", "Net margin", "Fundamental", "%", "Net profit ÷ revenue"),
    Field(
        "net_margin_change", "Net margin change (3y)", "Fundamental", "pp", "Positive = improving"
    ),
    Field("revenue_cagr_3y", "Revenue CAGR (3y)", "Fundamental", "%", "Annual statements"),
    Field("profit_cagr_3y", "Profit CAGR (3y)", "Fundamental", "%", "Annual statements"),
    Field(
        "revenue_qoq_yoy",
        "Latest quarter revenue YoY",
        "Fundamental",
        "%",
        "vs the same quarter last year",
    ),
    Field(
        "profit_qoq_yoy",
        "Latest quarter profit YoY",
        "Fundamental",
        "%",
        "vs the same quarter last year",
    ),
    Field("debt_equity", "Debt/equity", "Fundamental", "x", "Not used for financials", True),
    Field(
        "interest_coverage",
        "Interest coverage",
        "Fundamental",
        "x",
        "EBIT ÷ interest; not used for financials",
        True,
    ),
    Field("current_ratio", "Current ratio", "Fundamental", "x", "Not used for financials", True),
    Field(
        "fcf_positive_years",
        "Years of positive FCF (last 3)",
        "Fundamental",
        "",
        "0–3; not used for financials",
        True,
    ),
    Field("fscore", "Piotroski F-score", "Fundamental", "", "0–9, when all 9 tests are computable"),
    # Scores (your style)
    Field("composite", "Composite score", "Score", "", "0–100, your style's blend"),
    Field("technical_score", "Technical score", "Score", "", "0–100"),
    Field("fundamental_score", "Fundamental score", "Score", "", "0–100"),
)

FIELD_BY_KEY: dict[str, Field] = {f.key: f for f in FIELDS}
